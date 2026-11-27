// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the texture cache lock (gpu/shadps4/video_core/texture_cache/sotc_tc_mutex.h) with and
// without SOTC_TC_MEMBARRIER: mutual exclusion between its biased owner and other threads, then
// what each side costs. The owner stands for the draw thread (thousands of holds per frame, with
// stores pending: ordinary ones and non-temporal ones, like the write-combined staging copies);
// the others for guest write faults (a few per frame). Each mode runs in a child process, since
// the mode is fixed when the process starts.
//     ninja -C out/gpu tc-mutex-test && out/gpu/tc-mutex-test
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <thread>
#include <vector>
#include <immintrin.h>
#include <sys/wait.h>
#include <unistd.h>
#include "video_core/texture_cache/sotc_tc_mutex.h"

using VideoCore::ReentrantMutex;
using Clock = std::chrono::steady_clock;

namespace {

// The critical section's data: plain loads and stores, so a lost update shows two holders at once
// (an atomic read-modify-write here would add the very fence the lock leaves out).
alignas(64) std::atomic<unsigned long long> counter{0};
alignas(64) std::atomic<int> holders{0};
std::atomic<bool> overlap{false};

void Critical(int work) {
    const int h = holders.load(std::memory_order_relaxed) + 1;
    holders.store(h, std::memory_order_relaxed);
    if (h != 1) {
        overlap.store(true, std::memory_order_relaxed);
    }
    for (int i = 0; i < work; ++i) {
        counter.store(counter.load(std::memory_order_relaxed) + 1, std::memory_order_relaxed);
    }
    holders.store(holders.load(std::memory_order_relaxed) - 1, std::memory_order_relaxed);
}

/// The owner and `others` threads taking the lock in turns; true when no update was lost.
bool Exclusion(int others, int seconds) {
    ReentrantMutex mutex;
    counter.store(0);
    overlap.store(false);
    std::atomic<bool> stop{false};
    std::atomic<unsigned long long> expected{0};
    std::atomic<bool> owner_ready{false};
    std::thread owner([&] {
        mutex.SetFastThread();
        owner_ready.store(true);
        unsigned long long mine = 0;
        while (!stop.load(std::memory_order_relaxed)) {
            mutex.lock();
            Critical(3);
            mutex.lock(); // re-entrant on the owner
            Critical(1);
            mutex.unlock();
            mutex.unlock();
            mine += 4;
        }
        expected.fetch_add(mine);
    });
    while (!owner_ready.load()) {
        std::this_thread::yield();
    }
    std::vector<std::thread> threads;
    for (int t = 0; t < others; ++t) {
        threads.emplace_back([&, t] {
            unsigned long long mine = 0;
            for (unsigned n = 0; !stop.load(std::memory_order_relaxed); ++n) {
                if ((n + t) % 3 == 0) {
                    if (!mutex.try_lock()) {
                        continue;
                    }
                } else {
                    mutex.lock();
                }
                Critical(2);
                mutex.unlock();
                mine += 2;
                // Mostly away from the lock, as guest faults are.
                for (int i = 0; i < 200; ++i) {
                    _mm_pause();
                }
            }
            expected.fetch_add(mine);
        });
    }
    std::this_thread::sleep_for(std::chrono::seconds(seconds));
    stop.store(true);
    owner.join();
    for (auto& th : threads) {
        th.join();
    }
    const bool ok = counter.load() == expected.load() && !overlap.load();
    std::printf("  exclusion, owner + %d threads, %d s: %llu updates, %s\n", others, seconds,
                expected.load(), ok ? "none lost" : "LOST UPDATES");
    return ok;
}

/// The owner's lock + unlock with `bytes` of stores pending before each (ns per hold).
double OwnerCost(size_t bytes, bool streaming) {
    ReentrantMutex mutex;
    alignas(64) static unsigned char buffer[1 << 20];
    double ns = 0;
    std::thread owner([&] {
        mutex.SetFastThread();
        constexpr int holds = 200000;
        size_t pos = 0;
        const __m128i v = _mm_set1_epi32(0x5a5a5a5a);
        auto run = [&](bool hold) {
            const auto start = Clock::now();
            for (int i = 0; i < holds; ++i) {
                for (size_t b = 0; b < bytes; b += 16) {
                    auto* p = reinterpret_cast<__m128i*>(buffer + ((pos + b) & (sizeof(buffer) - 1)));
                    if (streaming) {
                        _mm_stream_si128(p, v);
                    } else {
                        _mm_store_si128(p, v);
                    }
                }
                pos += bytes;
                if (hold) {
                    mutex.lock();
                    mutex.unlock();
                }
            }
            return std::chrono::duration<double, std::nano>(Clock::now() - start).count() / holds;
        };
        run(true); // warm up
        double best = 1e18;
        for (int r = 0; r < 5; ++r) {
            best = std::min(best, run(true) - run(false));
        }
        _mm_sfence();
        ns = best;
    });
    owner.join();
    return ns;
}

/// The owner's lock + unlock between pieces of lookup-like work: `loads` independent loads and
/// `stores` stores that miss the cache (a 256 MiB table). A fence waits until the stores before it
/// have reached the cache, which the CPU otherwise overlaps with the work after it (ns per hold,
/// above the same loop without the lock).
double OwnerCostMisses(int loads, int stores) {
    ReentrantMutex mutex;
    static std::vector<unsigned long long> table(size_t{256} << 17); // 256 MiB
    for (size_t i = 0; i < table.size(); i += 512) {
        table[i] = i;
    }
    double ns = 0;
    std::thread owner([&] {
        mutex.SetFastThread();
        constexpr int holds = 200000;
        alignas(64) unsigned long long out[8]{};
        unsigned long long x = 88172645463325252ull, sum = 0;
        auto run = [&](bool hold) {
            const auto start = Clock::now();
            for (int i = 0; i < holds; ++i) {
                for (int l = 0; l < loads; ++l) {
                    x ^= x << 13;
                    x ^= x >> 7;
                    x ^= x << 17;
                    sum += table[(x >> 8) & (table.size() - 1)];
                }
                for (int s = 0; s < stores; ++s) {
                    x ^= x << 13;
                    x ^= x >> 7;
                    x ^= x << 17;
                    table[(x >> 8) & (table.size() - 1)] = sum + s;
                }
                out[0] = sum;
                if (hold) {
                    mutex.lock();
                    mutex.unlock();
                }
            }
            return std::chrono::duration<double, std::nano>(Clock::now() - start).count() / holds;
        };
        run(true); // warm up
        double best = 1e18;
        for (int r = 0; r < 5; ++r) {
            best = std::min(best, run(true) - run(false));
        }
        ns = best + static_cast<double>((sum + out[0]) & 0) ;
    });
    owner.join();
    return ns;
}

/// Another thread's lock + unlock (its barrier included) while `busy` threads of the process run
/// on other CPUs (us per hold).
double OtherCost(int busy) {
    ReentrantMutex mutex;
    std::atomic<bool> stop{false};
    std::thread owner([&] {
        mutex.SetFastThread();
        mutex.lock();
        mutex.unlock();
        while (!stop.load(std::memory_order_relaxed)) {
            _mm_pause();
        }
    });
    std::vector<std::thread> spinners;
    for (int i = 0; i < busy; ++i) {
        spinners.emplace_back([&] {
            while (!stop.load(std::memory_order_relaxed)) {
                _mm_pause();
            }
        });
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(50));
    constexpr int holds = 20000;
    const auto start = Clock::now();
    for (int i = 0; i < holds; ++i) {
        mutex.lock();
        mutex.unlock();
    }
    const double us = std::chrono::duration<double, std::micro>(Clock::now() - start).count() / holds;
    stop.store(true);
    owner.join();
    for (auto& th : spinners) {
        th.join();
    }
    return us;
}

int Child(int seconds) {
    std::printf("mode: %s\n", ReentrantMutex::LightFence()
                                  ? "SOTC_TC_MEMBARRIER=1 (membarrier, no fence on the owner)"
                                  : "full fences (as before)");
    bool ok = Exclusion(1, seconds);
    ok = Exclusion(3, seconds) && ok;
    ok = Exclusion(static_cast<int>(std::max(2u, std::thread::hardware_concurrency() / 2)),
                   seconds) &&
         ok;
    std::printf("  owner hold: %.1f ns with 0 B pending, %.1f with 256 B of stores, %.1f with "
                "256 B non-temporal, %.1f with 4 KiB non-temporal\n",
                OwnerCost(0, false), OwnerCost(256, false), OwnerCost(256, true),
                OwnerCost(4096, true));
    std::printf("  owner hold between lookups that miss the cache: %.1f ns with 8 loads, %.1f with "
                "8 loads + 1 store, %.1f with 8 loads + 4 stores, %.1f with 32 loads + 8 stores\n",
                OwnerCostMisses(8, 0), OwnerCostMisses(8, 1), OwnerCostMisses(8, 4),
                OwnerCostMisses(32, 8));
    const int cpus = static_cast<int>(std::thread::hardware_concurrency());
    std::printf("  other thread's hold: %.2f us with 1 busy thread, %.2f with 4, %.2f with %d\n",
                OtherCost(1), OtherCost(4), OtherCost(std::max(1, cpus - 3)), std::max(1, cpus - 3));
    std::printf("  barriers counted: %llu\n",
                static_cast<unsigned long long>(SotcStats::tc_slow_barriers.load()));
    return ok ? 0 : 1;
}

int RunChild(const char* self, const char* mode, int seconds) {
    std::fflush(stdout);
    const pid_t pid = fork();
    if (pid == 0) {
        setenv("SOTC_TC_MEMBARRIER", mode, 1);
        setenv("SOTC_TC_MUTEX_CHILD", std::to_string(seconds).c_str(), 1);
        execl(self, self, static_cast<char*>(nullptr));
        std::perror("execl");
        _exit(127);
    }
    int status = 0;
    waitpid(pid, &status, 0);
    return WIFEXITED(status) ? WEXITSTATUS(status) : 1;
}

} // namespace

int main(int argc, char** argv) {
    if (const char* child = std::getenv("SOTC_TC_MUTEX_CHILD")) {
        return Child(std::atoi(child));
    }
    const int seconds = argc > 1 ? std::atoi(argv[1]) : 2;
    const int full = RunChild("/proc/self/exe", "0", seconds);
    const int light = RunChild("/proc/self/exe", "1", seconds);
    std::printf("%s\n", full == 0 && light == 0 ? "PASS" : "FAIL");
    return full == 0 && light == 0 ? 0 : 1;
}
