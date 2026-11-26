// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: when frames reach the screen, and flips locked to the screen's real refresh.
//
// Without adaptive sync (VRR) every frame waits for the screen's next refresh. At 60 FPS on a
// 240 Hz screen a frame is shown for 4 refreshes (16.7 ms) when it is ready in time, for 5
// (20.8 ms) when it is a little late and the next one for 3 (12.5 ms): the stutter of a steady
// 60. The flips were timed on the port's own 120 Hz clock, which drifts against the screen's, so
// the frames' readiness slid across the refresh boundaries again and again. Here the swapchain
// reports when each present was done (VK_KHR_present_wait, polled without blocking by the thread
// that presents), a phase-locked loop follows the screen's refresh grid from those times, and the
// frame limits (the 60 FPS limit, the dynamic step, the 30 FPS cap) release each flip at a lead
// before one refresh of that grid, a whole number of refreshes after the last one. The lead moves
// earlier when a frame released on time came out a refresh later than most, later when one came
// out a refresh earlier, so the frames' readiness settles in the middle of a refresh. With
// adaptive sync (VRR) the shown times sit on no grid and nothing is locked: the screen already
// waits for each frame. Every 5 s the log gets a "SOTC DISPLAY" line: how many refreshes each
// shown frame stayed on screen, the intervals between them, and whether the flips were locked.
//   SOTC_DISPLAY_TIMING=0  no present ids, no feedback (the line and the lock go away)
//   SOTC_DISPLAY_LOCK=0    feedback and the line only; the flips timed as before
#pragma once

#include <chrono>
#include <optional>
#include "common/types.h"

namespace Vulkan::SotcDisplay {

using Clock = std::chrono::steady_clock;

/// SOTC_DISPLAY_TIMING (default on): present ids and present-wait feedback wanted.
bool TimingWanted();

/// The screen's refresh rate in Hz (window thread, from SDL; 0 when unknown).
void SetRefreshHz(double hz);

/// Presenting thread: present `id` was queued (vkQueuePresentKHR succeeded).
void OnPresent(u64 id);

/// Presenting thread: the presents up to `id` are done, seen at `when`; `replaced` of them, the
/// older ones, were replaced before they were shown (several done between two polls).
void OnShown(u64 id, Clock::time_point when, u32 replaced);

/// The swapchain went away (recreated, lost): the feedback starts over.
void Reset();

/// Present thread: when the next flip of a frame limit with `period` should be released, a whole
/// number of the screen's refreshes after `last_release`, at the lead before one of them;
/// nullopt when not locked (disabled, no recent feedback, `period` not a whole number of
/// refreshes).
std::optional<Clock::time_point> LockedDue(std::chrono::nanoseconds period,
                                           Clock::time_point last_release);

/// Present thread, as a game flip is released, before it is presented: `locked` when its time
/// came from LockedDue, `on_time` when it went out at that time (not late, after its frame came).
void NoteFlip(Clock::time_point released, bool locked, bool on_time);

} // namespace Vulkan::SotcDisplay
