// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: SotcDisplay's lock (gpu/shadps4/video_core/renderer_vulkan/sotc_display.cpp) against a
// simulated fixed-refresh screen. Each frame is released either at LockedDue's time or, as
// before, on the port's free-running clock (the 1.04 ms tick grid of a 120 Hz vblank); it is
// ready a random time later, shown at the first refresh after that, and its feedback is seen at
// the present thread's next poll. The TRUE time each frame stays on screen is counted: "uneven"
// is the share of frames held for another number of refreshes than most.
//     ninja -C out/gpu display-lock-test && out/gpu/display-lock-test
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <deque>
#include <map>
#include <random>
#include "video_core/renderer_vulkan/sotc_display.h"

using namespace Vulkan::SotcDisplay;
using Ns = std::chrono::nanoseconds;

namespace {

Clock::time_point At(double ns) {
    return Clock::time_point{std::chrono::duration_cast<Clock::duration>(Ns{std::llround(ns)})};
}

double ToNs(Clock::time_point t) {
    return static_cast<double>(std::chrono::duration_cast<Ns>(t.time_since_epoch()).count());
}

struct Scenario {
    double true_hz;        // the screen's real rate (SDL reports `reported_hz`)
    double frame_ms;       // the frame limit's period
    double ready_ms;       // release -> frame ready, mean
    double jitter_ms;      // its standard deviation
    double reported_hz = 240.0;
    double late_share = 0.0;     // frames whose game frame comes 6 ms late
    double feedback_jitter_ms = 0.0;
    bool vrr = false;            // adaptive sync: a frame is shown when it is ready (240 Hz at most)
};

struct Result {
    double uneven = 0.0; // percent
    unsigned locked = 0, frames = 0;
};

Result Run(bool lock, const Scenario& c, double seconds = 120.0) {
    Reset();
    SetRefreshHz(c.reported_hz);
    std::mt19937_64 rng(42);
    std::normal_distribution<double> ready(c.ready_ms * 1e6, c.jitter_ms * 1e6);
    std::uniform_real_distribution<double> unit(0.0, 1.0);
    const double P = 1e9 / c.true_hz, tick = 1e9 / 120.0 / 8.0, latch = 0.3e6, delta = 0.2e6;
    const Ns period{std::llround(c.frame_ms * 1e6)};
    // Simulated time runs ahead of the real clock (LockedDue compares feedback with it).
    const double start = ToNs(Clock::now()) + 1e9;
    const double vblank = start + unit(rng) * P;
    struct Shown {
        double seen;
        unsigned long long id;
    };
    std::deque<Shown> feedback;
    double last_release = start, next_free = start, t = start, prev_shown = 0.0;
    unsigned long long id = 0;
    std::map<long, unsigned> holds;
    Result r;
    while (t < start + seconds * 1e9) {
        std::optional<Clock::time_point> due_lock = lock ? LockedDue(period, At(last_release))
                                                         : std::nullopt;
        double due;
        if (due_lock) {
            due = std::max(ToNs(*due_lock), t);
        } else { // as before: limit_next, taken on the tick grid
            next_free = std::max(next_free, t);
            due = start + std::ceil((next_free - tick / 2 - start) / tick) * tick;
            next_free += c.frame_ms * 1e6;
        }
        while (!feedback.empty() && feedback.front().seen <= due) {
            OnShown(feedback.front().id, At(feedback.front().seen), 0);
            feedback.pop_front();
        }
        if (due_lock) { // the loop asks again each tick, with the feedback seen meanwhile
            if (const auto again = LockedDue(period, At(last_release))) {
                due = std::max(ToNs(*again), t);
            }
        }
        bool on_time = true;
        if (c.late_share > 0.0 && unit(rng) < c.late_share) {
            due += 6e6;
            on_time = false;
        }
        NoteFlip(At(due), due_lock.has_value(), on_time);
        OnPresent(++id);
        r.locked += due_lock.has_value();
        const double ready_at = due + std::max(1e6, ready(rng));
        const double shown = c.vrr ? std::max(ready_at + latch, prev_shown + 1e9 / 240.0)
                                   : vblank + std::ceil((ready_at + latch - vblank) / P) * P;
        const double seen =
            start +
            std::ceil((shown + delta + unit(rng) * c.feedback_jitter_ms * 1e6 - start) / tick) * tick;
        feedback.push_back({seen, id});
        if (prev_shown != 0.0) {
            ++holds[std::lround((shown - prev_shown) / P)];
            ++r.frames;
        }
        prev_shown = shown;
        last_release = due;
        t = due + 0.1e6;
    }
    unsigned mode = 0;
    for (const auto& [k, n] : holds) {
        mode = std::max(mode, n);
    }
    r.uneven = 100.0 * (r.frames - mode) / r.frames;
    return r;
}

void Check(const char* what, const Scenario& c, double max_locked, bool must_beat_old) {
    const Result old_r = Run(false, c), locked_r = Run(true, c);
    std::printf("%-58s old %6.2f%%  locked %6.2f%%  (%u of %u frames locked)\n", what, old_r.uneven,
                locked_r.uneven, locked_r.locked, locked_r.frames);
    assert(locked_r.locked > locked_r.frames * 9 / 10);
    assert(locked_r.uneven <= max_locked);
    if (must_beat_old) {
        assert(locked_r.uneven < old_r.uneven);
    }
}

} // namespace

int main() {
    std::freopen("/dev/null", "w", stderr); // the module's own "SOTC DISPLAY" lines
    Check("60 FPS, 239.97 Hz screen, ready 10 +- 0.5 ms", {239.97, 1000.0 / 60, 10, 0.5}, 1.0,
          true);
    Check("60 FPS, exactly 240 Hz, ready 10 +- 0.5 ms", {240.0, 1000.0 / 60, 10, 0.5}, 1.0, true);
    Check("60 FPS, 239.97 Hz, ready 10 +- 1 ms (spread wider)", {239.97, 1000.0 / 60, 10, 1.0},
          12.0, true);
    Check("30 FPS cap, 239.97 Hz, ready 20 +- 0.5 ms", {239.97, 1000.0 / 30, 20, 0.5}, 1.0, true);
    Check("48 FPS dynamic step, 239.97 Hz, ready 13 +- 1 ms", {239.97, 1000.0 / 48, 13, 1.0}, 12.0,
          true);
    Check("60 FPS, 239.76 Hz screen reported as 240 (SDL 0.1% off)",
          {239.76, 1000.0 / 60, 10, 0.5, 240.0}, 1.0, true);
    Check("60 FPS, ready 20 ms (feedback after the next release)", {239.97, 1000.0 / 60, 20, 0.5},
          1.0, true);
    Check("60 FPS, compositor feedback jitter up to 1 ms",
          {239.97, 1000.0 / 60, 10, 0.5, 240.0, 0.0, 1.0}, 1.0, true);
    Check("60 FPS, 10% of the game's frames 6 ms late", {239.97, 1000.0 / 60, 10, 0.5, 240.0, 0.1},
          15.0, true);
    Check("60 FPS on a 59.94 Hz screen, ready 10 +- 1 ms", {59.94, 1000.0 / 60, 10, 1.0, 59.94}, 1.0,
          true);
    // Adaptive sync: the shown times sit on no grid, so the flips are never locked.
    {
        const Scenario vrr{240.0, 1000.0 / 60, 10, 1.0, 240.0, 0.0, 0.0, true};
        const Result r = Run(true, vrr);
        std::printf("%-58s locked %u of %u frames\n", "60 FPS with adaptive sync (VRR)", r.locked,
                    r.frames);
        assert(r.locked < r.frames / 100);
    }
    // 60 FPS on 144 Hz is no whole number of refreshes (2.4): never locked.
    Reset();
    SetRefreshHz(144.0);
    const auto now = Clock::now();
    for (u64 i = 1; i <= 200; ++i) { // frames on a 144 Hz grid until the fit shows one
        OnPresent(i);
        OnShown(i, now + std::chrono::nanoseconds{static_cast<s64>(i * 6'944'444)}, 0);
    }
    assert(!LockedDue(Ns{16'666'667}, now));
    assert(LockedDue(Ns{20'833'333}, now)); // the 48 FPS step: 3 refreshes
    std::printf("PASS: display lock\n");
    return 0;
}
