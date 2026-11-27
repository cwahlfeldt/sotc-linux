// SPDX-FileCopyrightText: Copyright 2026 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the texture cache lock, moved out of texture_cache.h (tests/test_tc_mutex.cpp builds it on
// its own).

#pragma once

#include <atomic>
#include <thread>

#include "common/types.h"
#include "video_core/sotc_stats.h"

namespace VideoCore {

/// sotc: the texture cache lock, re-entrant on its owner thread. The command processor holds it
/// over a whole binding pass (Rasterizer::BindTextures, BeginRendering, PrepareRenderState), so the
/// FindImage and UpdateImage calls inside (two per texture, ~62,000 per frame at the Shrine) only
/// count their depth. SOTC_TC_BATCH=0 drops the outer holds (every call locks as before).
///
/// It is also biased to the first thread to take a batch hold (the draw thread, which runs the
/// binds; the command processor without it): there it is a plain store and load. Any atomic read-modify-write on that thread waits for its pending
/// stores to drain (write-combined staging copies among them): the uncontended std::mutex, and
/// then a spinlock's xchg, each cost ~5% of the thread at ~10,000 holds per frame. Other threads
/// (guest write faults, ~200 per frame) take a spinlock, announce themselves and run an
/// asymmetric barrier (FlushProcessWriteBuffers) before waiting for the command processor to
/// leave: either its store of fast_held is visible to them after the barrier, or its following
/// load of slow_wants sees theirs. SOTC_TC_BIASED=0: every thread takes the spinlock.
///
/// On Linux both sides ran a full fence, so the owner's store and load became store, mfence,
/// load: at the temple (21:9, 60 FPS) ~6.5% of the draw thread waited in that mfence for its
/// pending stores. SOTC_TC_MEMBARRIER=1 makes the other threads' barrier a
/// membarrier(MEMBARRIER_CMD_PRIVATE_EXPEDITED), which runs a full barrier on every CPU running a
/// thread of the process before it returns, the owner then orders its store and load only for the
/// compiler, as on Windows (sotc_tc_mutex.cpp; the old fences when the kernel lacks it).
class alignas(64) ReentrantMutex {
public:
    /// Makes the calling thread the biased owner (once).
    void SetFastThread() {
        if (!fast_token.load(std::memory_order_relaxed) && Biased() && !HeldByThisThread()) {
            // Under the spinlock: a thread holding it read fast_token as null and skipped the
            // announcement, so the biased path must not start before it leaves.
            RawLock();
            fast_token.store(Token(), std::memory_order_relaxed);
            word.store(0, std::memory_order_release);
        }
    }
    void lock() {
        const void* self = Token();
        if (owner.load(std::memory_order_relaxed) == self) {
            ++depth;
            return;
        }
        if (self == fast_token.load(std::memory_order_relaxed)) {
            if (FastTryAcquire()) {
                mode = Mode::Fast;
            } else {
                RawLock(); // a guest holds it or is waiting for us: queue behind it
                mode = Mode::FastSlow;
                SotcStats::tc_fast_queued.fetch_add(1, std::memory_order_relaxed);
            }
        } else {
            RawLock();
            AnnounceAndWait();
            mode = Mode::Slow;
        }
        owner.store(self, std::memory_order_relaxed);
        depth = 1;
    }
    bool try_lock() {
        const void* self = Token();
        if (owner.load(std::memory_order_relaxed) == self) {
            ++depth;
            return true;
        }
        if (self == fast_token.load(std::memory_order_relaxed)) {
            if (!FastTryAcquire()) {
                return false;
            }
            mode = Mode::Fast;
        } else {
            if (!RawTryLock()) {
                return false;
            }
            if (!AnnounceAndTry()) {
                return false;
            }
            mode = Mode::Slow;
        }
        owner.store(self, std::memory_order_relaxed);
        depth = 1;
        return true;
    }
    bool HeldByThisThread() const {
        return owner.load(std::memory_order_relaxed) == Token();
    }
    void unlock() {
        if (--depth != 0) {
            return;
        }
        owner.store(nullptr, std::memory_order_relaxed);
        switch (mode) {
        case Mode::Fast:
            fast_held.store(0, std::memory_order_release);
            break;
        case Mode::Slow:
            slow_wants.store(0, std::memory_order_release);
            word.store(0, std::memory_order_release);
            break;
        case Mode::FastSlow:
            word.store(0, std::memory_order_release);
            break;
        }
    }

private:
    enum class Mode : u8 { Fast, Slow, FastSlow };

    static bool Biased() {
        static const bool on = [] {
            const char* v = std::getenv("SOTC_TC_BIASED");
            return !v || v[0] != '0';
        }();
        return on;
    }
    /// Only the owner stores its own token, and clears it before unlocking, so a thread reads
    /// its token back exactly while it holds the lock.
    static const void* Token() {
        static thread_local char token;
        return &token;
    }
    /// FlushProcessWriteBuffers on Windows, membarrier with kLightFence, else a full fence
    /// (sotc_tc_mutex.cpp).
    static void AsymmetricBarrier();
    /// SOTC_TC_MEMBARRIER=1 and the kernel's membarrier registered for the process: fixed for
    /// the process before any thread takes the lock (static initialisation).
    static bool InitLightFence();
    static inline const bool kLightFence = InitLightFence();

public:
    /// True when the biased owner runs without a CPU fence (SOTC_TC_MEMBARRIER, Linux).
    static bool LightFence() {
        return kLightFence;
    }

private:
    static void Pause(u32& spins) {
        if (++spins < 4096) {
            __builtin_ia32_pause();
        } else {
            std::this_thread::yield();
        }
    }
    bool FastTryAcquire() {
        fast_held.store(1, std::memory_order_relaxed);
#ifdef _WIN32
        std::atomic_signal_fence(std::memory_order_seq_cst); // the barrier is on the other side
#else
        if (kLightFence) {
            std::atomic_signal_fence(std::memory_order_seq_cst); // membarrier on the other side
        } else {
            std::atomic_thread_fence(std::memory_order_seq_cst);
        }
#endif
        if (slow_wants.load(std::memory_order_acquire) == 0) {
            return true;
        }
        fast_held.store(0, std::memory_order_release);
        return false;
    }
    void AnnounceAndWait() {
        if (!fast_token.load(std::memory_order_relaxed)) {
            return; // no biased owner (SOTC_TC_BIASED=0, or before the first batch hold)
        }
        slow_wants.store(1, std::memory_order_relaxed);
        AsymmetricBarrier();
        for (u32 spins = 0; fast_held.load(std::memory_order_acquire);) {
            Pause(spins);
        }
    }
    bool AnnounceAndTry() {
        if (!fast_token.load(std::memory_order_relaxed)) {
            return true;
        }
        slow_wants.store(1, std::memory_order_relaxed);
        AsymmetricBarrier();
        if (!fast_held.load(std::memory_order_acquire)) {
            return true;
        }
        slow_wants.store(0, std::memory_order_release);
        word.store(0, std::memory_order_release);
        return false;
    }
    void RawLock() {
        if (!word.exchange(1, std::memory_order_acquire)) {
            return;
        }
        for (u32 spins = 0;;) {
            while (word.load(std::memory_order_relaxed)) {
                Pause(spins);
            }
            if (!word.exchange(1, std::memory_order_acquire)) {
                return;
            }
        }
    }
    bool RawTryLock() {
        return !word.load(std::memory_order_relaxed) &&
               !word.exchange(1, std::memory_order_acquire);
    }
    std::atomic<u32> word{0};       ///< spinlock of the other threads (and of the biased owner
                                    ///< when it had to queue behind them)
    std::atomic<u32> slow_wants{0}; ///< a thread holding `word` waits for or holds the lock
    std::atomic<const void*> fast_token{nullptr};
    std::atomic<const void*> owner{nullptr};
    u32 depth = 0;
    Mode mode = Mode::Fast;
    alignas(64) std::atomic<u32> fast_held{0}; ///< the biased owner holds it (written by it only)
};

} // namespace VideoCore
