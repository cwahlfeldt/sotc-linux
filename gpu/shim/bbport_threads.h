// SPDX-License-Identifier: GPL-2.0-or-later
// bbport: helper thread sizing. Counts follow the hardware threads this process may run on
// (the affinity mask, so `taskset` can emulate a Steam Deck), and speculative helpers run as
// SCHED_IDLE: they use cores the game leaves idle and never take time from its threads.

#pragma once

#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <thread>
#ifdef _WIN32
#include <bit>
#include <windows.h>
#else
#include <sched.h>
#include <sys/resource.h>
#include <unistd.h>
#endif

namespace BbThreads {
#ifdef _WIN32
/// Hardware threads available to the process (its affinity mask).
inline unsigned Available() {
    DWORD_PTR process = 0, system = 0;
    if (GetProcessAffinityMask(GetCurrentProcess(), &process, &system) && process) {
        return std::max(1, std::popcount(static_cast<unsigned long long>(process)));
    }
    return std::max(1u, std::thread::hardware_concurrency());
}

/// The calling thread only runs when cores are otherwise idle (lowest Windows priority).
inline void MakeBackground() {
    SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_IDLE);
}

/// Linux only (below); Windows' scheduler places threads on hybrid CPUs itself.
inline void PreferPerformanceCores() {}
#else

/// Hardware threads available to the process.
inline unsigned Available() {
    cpu_set_t set;
    CPU_ZERO(&set);
    if (sched_getaffinity(0, sizeof(set), &set) == 0) {
        return std::max(1, CPU_COUNT(&set));
    }
    return std::max(1u, std::thread::hardware_concurrency());
}

/// The calling thread only runs on otherwise idle cores (falls back to the lowest nice level).
inline void MakeBackground() {
    sched_param param{};
    if (sched_setscheduler(0, SCHED_IDLE, &param) != 0) {
        setpriority(PRIO_PROCESS, static_cast<id_t>(gettid()), 19);
    }
}

/// A sysfs CPU list ("0-11,16") as a set; false when the file is absent or empty.
inline bool ReadCpuList(const char* path, cpu_set_t& set) {
    CPU_ZERO(&set);
    FILE* file = std::fopen(path, "r");
    if (!file) {
        return false;
    }
    unsigned first = 0, last = 0;
    char separator = 0;
    while (std::fscanf(file, "%u", &first) == 1) {
        last = first;
        if (std::fscanf(file, "%c", &separator) == 1 && separator == '-') {
            if (std::fscanf(file, "%u", &last) != 1) {
                break;
            }
            separator = 0;
            if (std::fscanf(file, "%c", &separator) != 1) {
                separator = 0;
            }
        }
        for (unsigned cpu = first; cpu <= last && cpu < CPU_SETSIZE; ++cpu) {
            CPU_SET(cpu, &set);
        }
        if (separator != ',') {
            break;
        }
    }
    std::fclose(file);
    return CPU_COUNT(&set) > 0;
}

/// sotc (Linux): on Intel hybrid CPUs the calling thread runs on the performance cores. The
/// command processor, draw and recorder threads each keep a core busy, and the scheduler left
/// them on E-cores (3.9 against 5.1 GHz on an i5-13600KF) about a quarter of the time while the
/// game's four job workers spun on P-cores. The kernel lists the two core types in
/// /sys/devices/cpu_core/cpus and /sys/devices/cpu_atom/cpus; without both (AMD, the Steam Deck,
/// older Intel) nothing changes. The P-cores are taken within the thread's current affinity (a
/// taskset stays honoured), and only when at least 4 of them remain. Threads these threads start
/// later inherit it (the copy helpers, which they wait for). SOTC_PCORES=0 turns it off.
inline void PreferPerformanceCores() {
    static const bool off = [] {
        const char* v = std::getenv("SOTC_PCORES");
        return v && v[0] == '0';
    }();
    if (off) {
        return;
    }
    cpu_set_t performance, efficient, mine, want;
    if (!ReadCpuList("/sys/devices/cpu_core/cpus", performance) ||
        !ReadCpuList("/sys/devices/cpu_atom/cpus", efficient) ||
        sched_getaffinity(0, sizeof(mine), &mine) != 0) {
        return;
    }
    CPU_AND(&want, &mine, &performance);
    if (CPU_COUNT(&want) < 4 || CPU_EQUAL(&want, &mine)) {
        return;
    }
    if (sched_setaffinity(0, sizeof(want), &want) == 0) {
        static std::atomic<bool> logged{false};
        if (!logged.exchange(true)) {
            std::printf("SOTC CPU: hybrid CPU, the GPU threads run on its %d performance-core "
                        "threads (SOTC_PCORES=0: anywhere)\n",
                        CPU_COUNT(&want));
        }
    }
}
#endif

} // namespace BbThreads
