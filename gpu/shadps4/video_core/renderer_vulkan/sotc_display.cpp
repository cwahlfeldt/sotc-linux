// SPDX-License-Identifier: GPL-2.0-or-later
// sotc: when frames reach the screen, and flips locked to the screen's real refresh
// (sotc_display.h).

#include "video_core/renderer_vulkan/sotc_display.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <deque>
#include <mutex>
#include <string>
#include <vector>

namespace Vulkan::SotcDisplay {
namespace {

using Ns = std::chrono::nanoseconds;

double ToNs(Clock::time_point t) {
    return static_cast<double>(std::chrono::duration_cast<Ns>(t.time_since_epoch()).count());
}

Clock::time_point FromNs(double v) {
    return Clock::time_point{std::chrono::duration_cast<Clock::duration>(Ns{std::llround(v)})};
}

bool EnvOn(const char* name) {
    const char* v = std::getenv(name);
    return !(v && v[0] == '0');
}

// The refresh grid follows the shown times with a second-order loop: the phase moves by kAlpha of
// each error, the period by kBeta of it per refresh (both small: a shown time is only known to
// within the poll, ~1 ms).
constexpr double kAlpha = 0.05;
constexpr double kBeta = 0.0005;
// The lead, in refreshes (a phase: one whole refresh more aims at the next refresh, the same
// release time). A frame released on time that came out a refresh later than most of the last 64
// moves it earlier by kLeadStep (0.13 ms at 240 Hz), one that came out a refresh earlier moves it
// later: the two tails balance where the frames' readiness sits in the middle of a refresh, as
// far from both edges as their spread allows. (Steering by the best refresh seen instead ran
// away: once a quick frame made an earlier refresh, every normal one looked late.)
constexpr double kLeadStart = 0.5;
constexpr double kLeadStep = 0.03;
constexpr double kStaleNs = 250e6; // no feedback for this long: not locked
// How well the shown times sit on a refresh grid: the average distance to the nearest refresh, in
// refreshes. A fixed refresh gives the poll's spread (~0.06 at 240 Hz, less below); with
// adaptive sync (VRR) the screen refreshes when a frame comes, the times fall anywhere (0.25) and
// there is nothing to lock to. A new grid starts at "no grid" until the times prove one.
constexpr double kFitGain = 0.02;
constexpr double kFitNoGrid = 0.25;
constexpr double kFitLock = 0.15;
constexpr u32 kLateWindow = 64;    // late or early against the most common of the last 64

struct Pending {
    u64 id = 0;
    bool flip = false;
    bool locked = false;
    bool on_time = false;
    s64 slot = 0; // the refresh it aimed at (locked)
    u32 generation = 0;
    double release_ns = 0;
};

struct State {
    std::mutex mutex;
    // The refresh grid: a refresh at grid_ns (absolute slot grid_slot), one every period_ns.
    bool grid = false;
    u32 generation = 0; // a new grid: slots of older flips no longer compare
    double grid_ns = 0, period_ns = 0, nominal_ns = 0;
    s64 grid_slot = 0;
    double fit = kFitNoGrid; // average distance to the grid, in refreshes
    double last_shown_ns = 0;
    // The lock.
    double lead = kLeadStart;
    bool armed = false;
    s64 armed_slot = 0;
    u32 armed_generation = 0;
    bool noted = false;
    Pending note{};
    std::deque<Pending> pending;
    std::array<s64, kLateWindow> late_ring{};
    u32 late_filled = 0, late_pos = 0;
    // The 5 s line.
    double window_ns = 0;
    std::array<u32, 8> holds{}; // shown frames held 1..7 refreshes; [0]: 8 or more
    u32 shown = 0, replaced = 0, late = 0, early = 0, locked_flips = 0;
    bool have_prev = false;
    double prev_ns = 0;
    std::vector<float> latency_ms;
    std::vector<float> interval_ms; // between shown frames (the measure with adaptive sync)
};

State& S() {
    static State s;
    return s;
}

std::atomic<double> refresh_hz{0.0};

void NewGrid(State& s, double t, double nominal) {
    s.grid = true;
    ++s.generation;
    s.nominal_ns = s.period_ns = nominal;
    s.grid_ns = t;
    s.grid_slot = 0;
    s.fit = kFitNoGrid;
    s.lead = kLeadStart;
    s.late_filled = s.late_pos = 0;
}

// The grid follows the shown time t.
void Track(State& s, double t) {
    const double hz = refresh_hz.load(std::memory_order_relaxed);
    if (hz < 20.0 || hz > 1000.0) {
        s.grid = false;
        return;
    }
    const double nominal = 1e9 / hz;
    if (!s.grid || std::abs(nominal - s.nominal_ns) > s.nominal_ns * 0.005 ||
        t - s.last_shown_ns > 1e9 || t < s.grid_ns) {
        NewGrid(s, t, nominal);
        return;
    }
    const double k = std::round((t - s.grid_ns) / s.period_ns);
    const double predicted = s.grid_ns + k * s.period_ns;
    const double err = t - predicted; // within half a refresh
    s.fit += kFitGain * (std::abs(err) / s.period_ns - s.fit);
    s.grid_ns = predicted + kAlpha * err;
    s.grid_slot += static_cast<s64>(k);
    if (k >= 1.0) {
        s.period_ns = std::clamp(s.period_ns + kBeta * err / k, s.nominal_ns * 0.995,
                                 s.nominal_ns * 1.005);
    }
}

// A locked flip released on time was shown at t (after Track): move the lead toward the side
// the frames miss.
void Steer(State& s, const Pending& p, double t) {
    const s64 shown_slot =
        s.grid_slot + static_cast<s64>(std::llround((t - s.grid_ns) / s.period_ns));
    const s64 refreshes = shown_slot - p.slot; // from the refresh it aimed at to the one it made
    s.late_ring[s.late_pos] = refreshes;
    s.late_pos = (s.late_pos + 1) % kLateWindow;
    s.late_filled = std::min(s.late_filled + 1, kLateWindow);
    // The most common count of the window (ties: the smaller).
    s64 mode = refreshes;
    u32 mode_n = 0;
    for (u32 i = 0; i < s.late_filled; ++i) {
        u32 n = 0;
        for (u32 j = 0; j < s.late_filled; ++j) {
            n += s.late_ring[j] == s.late_ring[i];
        }
        if (n > mode_n || (n == mode_n && s.late_ring[i] < mode)) {
            mode = s.late_ring[i];
            mode_n = n;
        }
    }
    if (refreshes > mode) {
        s.lead += kLeadStep;
        ++s.late;
    } else if (refreshes < mode) {
        s.lead -= kLeadStep;
        ++s.early;
    }
    // One refresh more lead aims one refresh later (the same release): the counts of the window
    // move by one the other way, so they still compare with the flips to come.
    if (s.lead >= 1.0) {
        s.lead -= 1.0;
        for (u32 i = 0; i < s.late_filled; ++i) {
            ++s.late_ring[i];
        }
    } else if (s.lead < 0.0) {
        s.lead += 1.0;
        for (u32 i = 0; i < s.late_filled; ++i) {
            --s.late_ring[i];
        }
    }
}

void Print(State& s, double t) {
    u32 total = 0, mode_count = 0;
    std::string held;
    for (size_t i = 1; i <= s.holds.size(); ++i) {
        const u32 n = s.holds[i % s.holds.size()];
        total += n;
        if (n) {
            held += (held.empty() ? "" : " ") + (i < s.holds.size() ? std::to_string(i) : "8+") +
                    ":" + std::to_string(n);
        }
        if (i < s.holds.size() && n > mode_count) {
            mode_count = n;
        }
    }
    float p50 = 0.0f, p95 = 0.0f;
    if (!s.latency_ms.empty()) {
        std::sort(s.latency_ms.begin(), s.latency_ms.end());
        const size_t n = s.latency_ms.size();
        p50 = s.latency_ms[n / 2];
        p95 = s.latency_ms[std::min(n - 1, n * 95 / 100)];
    }
    float i10 = 0.0f, i50 = 0.0f, i90 = 0.0f;
    if (!s.interval_ms.empty()) {
        std::sort(s.interval_ms.begin(), s.interval_ms.end());
        const size_t n = s.interval_ms.size();
        i10 = s.interval_ms[n / 10];
        i50 = s.interval_ms[n / 2];
        i90 = s.interval_ms[std::min(n - 1, n * 9 / 10)];
    }
    char lock[96];
    if (s.fit > kFitLock) {
        std::snprintf(lock, sizeof(lock), "no fixed refresh (adaptive sync?), not locked");
    } else if (s.locked_flips) {
        std::snprintf(lock, sizeof(lock), "locked %u, lead %.2f ms, late %u, early %u",
                      s.locked_flips, s.lead * s.period_ns / 1e6, s.late, s.early);
    } else {
        std::snprintf(lock, sizeof(lock), "not locked");
    }
    std::fprintf(stderr,
                 "SOTC DISPLAY %.0fs: %u shown at %.2f Hz, held %s refreshes (uneven %.1f%%); "
                 "intervals p10/p50/p90 %.1f/%.1f/%.1f ms; replaced %u; flip to screen p50 %.1f "
                 "ms, p95 %.1f ms; grid fit %.2f; %s\n",
                 (t - s.window_ns) / 1e9, s.shown, 1e9 / s.period_ns,
                 held.empty() ? "-" : held.c_str(),
                 total ? 100.0 * (total - mode_count) / total : 0.0, i10, i50, i90, s.replaced,
                 p50, p95, s.fit, lock);
    s.window_ns = t;
    s.holds = {};
    s.shown = s.replaced = s.late = s.early = s.locked_flips = 0;
    s.latency_ms.clear();
    s.interval_ms.clear();
}

} // namespace

bool TimingWanted() {
    static const bool on = EnvOn("SOTC_DISPLAY_TIMING");
    return on;
}

void SetRefreshHz(double hz) {
    refresh_hz.store(hz, std::memory_order_relaxed);
}

void OnPresent(u64 id) {
    auto& s = S();
    std::scoped_lock lock{s.mutex};
    Pending p = s.noted ? s.note : Pending{};
    p.id = id;
    s.noted = false;
    s.pending.push_back(p);
    while (s.pending.size() > 64) {
        s.pending.pop_front();
    }
}

void OnShown(u64 id, Clock::time_point when, u32 replaced) {
    auto& s = S();
    std::scoped_lock lock{s.mutex};
    const double t = ToNs(when);
    Pending shown{};
    bool found = false;
    while (!s.pending.empty() && s.pending.front().id <= id) {
        if (s.pending.front().id == id) {
            shown = s.pending.front();
            found = true;
        }
        s.pending.pop_front();
    }
    Track(s, t);
    s.last_shown_ns = t;
    if (!s.grid) {
        return;
    }
    if (s.window_ns == 0) {
        s.window_ns = t;
    }
    s.replaced += replaced;
    ++s.shown;
    if (s.have_prev) {
        const long held = std::lround((t - s.prev_ns) / s.period_ns);
        ++s.holds[held >= 1 && held < static_cast<long>(s.holds.size()) ? held : 0];
        if (s.interval_ms.size() < 4096) {
            s.interval_ms.push_back(static_cast<float>((t - s.prev_ns) / 1e6));
        }
    }
    s.have_prev = true;
    s.prev_ns = t;
    if (found && shown.flip) {
        if (s.latency_ms.size() < 4096) {
            s.latency_ms.push_back(static_cast<float>((t - shown.release_ns) / 1e6));
        }
        s.locked_flips += shown.locked;
        if (shown.on_time && shown.generation == s.generation) {
            Steer(s, shown, t);
        }
    }
    if (t - s.window_ns >= 5e9) {
        Print(s, t);
    }
}

void Reset() {
    auto& s = S();
    std::scoped_lock lock{s.mutex};
    s.pending.clear();
    s.grid = false;
    ++s.generation;
    s.have_prev = false;
    s.noted = false;
    s.armed = false;
}

std::optional<Clock::time_point> LockedDue(std::chrono::nanoseconds period,
                                           Clock::time_point last_release) {
    static const bool on = EnvOn("SOTC_DISPLAY_LOCK") && TimingWanted();
    if (!on) {
        return std::nullopt;
    }
    auto& s = S();
    std::scoped_lock lock{s.mutex};
    s.armed = false;
    if (!s.grid || s.fit > kFitLock || ToNs(Clock::now()) - s.last_shown_ns > kStaleNs) {
        return std::nullopt;
    }
    const double refreshes = static_cast<double>(period.count()) / s.period_ns;
    const double whole = std::round(refreshes);
    if (whole < 1.0 || std::abs(refreshes - whole) > 0.015 * whole) {
        return std::nullopt;
    }
    // The refresh nearest to `whole` refreshes after the last release (within half of one either
    // way), released the lead before it.
    const double lead_ns = s.lead * s.period_ns;
    const double earliest = ToNs(last_release) + (whole - 0.5) * s.period_ns;
    const double slot = std::ceil((earliest + lead_ns - s.grid_ns) / s.period_ns);
    s.armed = true;
    s.armed_slot = s.grid_slot + static_cast<s64>(slot);
    s.armed_generation = s.generation;
    return FromNs(s.grid_ns + slot * s.period_ns - lead_ns);
}

void NoteFlip(Clock::time_point released, bool locked, bool on_time) {
    auto& s = S();
    std::scoped_lock lock{s.mutex};
    const bool aimed = locked && s.armed;
    s.note = Pending{
        .flip = true,
        .locked = aimed,
        .on_time = aimed && on_time,
        .slot = s.armed_slot,
        .generation = s.armed_generation,
        .release_ns = ToNs(released),
    };
    s.noted = true;
    s.armed = false;
}

} // namespace Vulkan::SotcDisplay
