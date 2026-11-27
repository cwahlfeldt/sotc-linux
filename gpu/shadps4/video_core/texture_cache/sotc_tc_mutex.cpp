// SPDX-FileCopyrightText: Copyright 2026 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: the texture cache lock's asymmetric barrier (sotc_tc_mutex.h). No logging or assert
// headers: tests/test_tc_mutex.cpp builds this file on its own.

#include <cstdio>
#include <cstdlib>

#ifdef _WIN32
#include <windows.h>
#elif defined(__linux__)
#include <linux/membarrier.h>
#include <sys/syscall.h>
#include <unistd.h>
#endif

#include "video_core/texture_cache/sotc_tc_mutex.h"

namespace VideoCore {

bool ReentrantMutex::InitLightFence() {
#if defined(__linux__)
    const char* v = std::getenv("SOTC_TC_MEMBARRIER");
    if (v && v[0] == '0') {
        return false;
    }
    // Registered once for the process; the expedited command then needs no further setup.
    const long commands = syscall(__NR_membarrier, MEMBARRIER_CMD_QUERY, 0, 0);
    if (commands < 0 || !(commands & MEMBARRIER_CMD_PRIVATE_EXPEDITED) ||
        syscall(__NR_membarrier, MEMBARRIER_CMD_REGISTER_PRIVATE_EXPEDITED, 0, 0) != 0) {
        std::fprintf(stderr, "SOTC TC LOCK: membarrier unavailable (commands %#lx), full fences\n",
                     commands);
        return false;
    }
    std::fprintf(stderr, "SOTC TC LOCK: membarrier barrier, the draw thread's fence left out "
                         "(SOTC_TC_MEMBARRIER=0: fences)\n");
    return true;
#else
    return false;
#endif
}

void ReentrantMutex::AsymmetricBarrier() {
    SotcStats::tc_slow_barriers.fetch_add(1, std::memory_order_relaxed);
#ifdef _WIN32
    FlushProcessWriteBuffers();
#else
#if defined(__linux__)
    if (kLightFence) {
        // Every CPU running a thread of this process runs a full barrier before this returns:
        // the owner's store of fast_held is visible to the load after it, or its load of
        // slow_wants comes after the barrier and sees ours.
        if (syscall(__NR_membarrier, MEMBARRIER_CMD_PRIVATE_EXPEDITED, 0, 0) == 0) {
            return;
        }
        // Registered at start, so the kernel cannot refuse it; without it the lock would no
        // longer exclude the owner.
        std::fprintf(stderr, "SOTC TC LOCK: membarrier failed after registration\n");
        std::abort();
    }
#endif
    std::atomic_thread_fence(std::memory_order_seq_cst);
#endif
}

} // namespace VideoCore
