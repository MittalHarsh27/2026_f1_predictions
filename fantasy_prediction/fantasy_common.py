import pandas as pd
from itertools import combinations

# ── Tyre compound normalization ───────────────────────────────────────
# How much slower each compound is vs SOFT, in seconds per lap.
# Lets us compare FP times set on different compounds fairly.
# Tune per-circuit if needed (e.g. some tracks have tighter gaps).
TYRE_DELTA_TO_SOFT = {
    "SOFT":         0.0,
    "MEDIUM":       0.6,
    "HARD":         1.1,   # medium gap + hard gap stacked
    "INTERMEDIATE": 4.0,   # not typically used in dry FP
    "WET":          8.0,
    "UNKNOWN":      0.0,   # no adjustment when compound not available
}


def soft_equivalent(lap_time_s, compound):
    """
    Adjust a lap time to its soft-tyre equivalent for cross-compound comparison.
    e.g. a 81.8s lap on MEDIUM → 81.8 - 0.6 = 81.2s soft-equivalent.
    """
    delta = TYRE_DELTA_TO_SOFT.get(str(compound).upper(), 0.0)
    return lap_time_s - delta

# ── Roster & budget ──────────────────────────────────────────────────
BUDGET            = 100_000_000
DRIVER_COUNT      = 5
CONSTRUCTOR_COUNT = 2
MAX_DRIVERS_PER_TEAM = 2

# ── Qualifying scoring ───────────────────────────────────────────────
# Q3 finishers (P1-P10); P11-P20 = 0; NC/DSQ/no time set = -5
QUALI_POINTS    = {1:10, 2:9, 3:8, 4:7, 5:6, 6:5, 7:4, 8:3, 9:2, 10:1}
QUALI_NO_TIME_PTS = -5      # NC / DSQ / no time set in Q1

# Constructor qualifying tier bonus
QUALI_CONSTRUCTOR_BONUS = {
    "neither_q2": -1,
    "one_q2":      1,
    "both_q2":     3,
    "one_q3":      5,
    "both_q3":    10,
    "dsq_driver": -5,    # per DSQ'd driver
}

# ── Race scoring ─────────────────────────────────────────────────────
RACE_POINTS          = {1:25, 2:18, 3:15, 4:12, 5:10, 6:8, 7:6, 8:4, 9:2, 10:1}
RACE_DNF_PTS         = -20
RACE_FASTEST_LAP_PTS = 10
RACE_OVERTAKE_PTS    = 1     # per overtake (on top of positions-gained bonus)
RACE_POS_GAINED_PTS  = 1     # per position gained vs grid
RACE_POS_LOST_PTS    = -1    # per position lost vs grid
DOTD_PTS             = 10    # Driver Of The Day (driver slot only, not constructor)

# Constructor pitstop bonus (unpredictable pre-race; listed for reference)
RACE_PITSTOP_PTS = {
    "over_3s":    0, "2.50_2.99s":  2, "2.20_2.49s":  5,
    "2.00_2.19s": 10, "under_2s":  20, "fastest":     5, "world_record": 15,
}
RACE_CONSTRUCTOR_DSQ_PTS = -20   # per DSQ'd driver

# ── Sprint scoring (2026: DNF reduced to -10) ────────────────────────
SPRINT_RACE_POINTS       = {1:8, 2:7, 3:6, 4:5, 5:4, 6:3, 7:2, 8:1}
SPRINT_DNF_PTS           = -10
SPRINT_FASTEST_LAP_PTS   = 5
SPRINT_OVERTAKE_PTS      = 1
SPRINT_POS_GAINED_PTS    = 1
SPRINT_POS_LOST_PTS      = -1
SPRINT_CONSTRUCTOR_DSQ_PTS = -10   # per DSQ'd driver


# ── Scoring helpers ──────────────────────────────────────────────────

def score_driver(quali_pos, race_pos, fastest_lap=False, dnf=False, no_time_set=False):
    """
    Expected fantasy points for a driver given predicted qualifying and race positions.
    grid_pos is assumed equal to quali_pos (no grid penalties assumed).

    no_time_set: True only for NC/DSQ/truly inactive drivers (applies -5 quali penalty).
                 P11-P22 finishers score 0 qualifying pts but are NOT penalised.
    Returns float.
    """
    pts = 0

    # Qualifying points (P1-P10 scored; P11+ = 0; NC/DSQ/no time = -5)
    if no_time_set:
        pts += QUALI_NO_TIME_PTS
    else:
        pts += QUALI_POINTS.get(quali_pos, 0)

    if dnf:
        pts += RACE_DNF_PTS
        return pts

    # Race finish points
    pts += RACE_POINTS.get(race_pos, 0)

    # Fastest lap bonus
    if fastest_lap:
        pts += RACE_FASTEST_LAP_PTS

    # Positions gained / lost vs grid (grid_pos = quali_pos)
    places = quali_pos - race_pos
    if places > 0:
        pts += places * (RACE_POS_GAINED_PTS + RACE_OVERTAKE_PTS)
    elif places < 0:
        pts += abs(places) * RACE_POS_LOST_PTS

    return float(pts)


def score_constructor(d1_quali, d2_quali, d1_race, d2_race):
    """
    Expected fantasy points for a constructor given both drivers' predicted positions.
    Includes: combined driver race pts + combined driver quali pts + qualifying tier bonus.
    Pitstop bonus is excluded (unpredictable pre-race).
    Returns float.
    """
    # Combined drivers' race and qualifying points (P11+ = 0, no NC penalty assumed)
    pts = (RACE_POINTS.get(d1_race, 0) + RACE_POINTS.get(d2_race, 0) +
           QUALI_POINTS.get(d1_quali, 0) +
           QUALI_POINTS.get(d2_quali, 0))

    # Qualifying tier bonus
    d1_q3 = d1_quali <= 10
    d2_q3 = d2_quali <= 10
    d1_q2 = d1_quali <= 15
    d2_q2 = d2_quali <= 15

    if d1_q3 and d2_q3:
        pts += QUALI_CONSTRUCTOR_BONUS["both_q3"]
    elif d1_q3 or d2_q3:
        pts += QUALI_CONSTRUCTOR_BONUS["one_q3"]
    elif d1_q2 and d2_q2:
        pts += QUALI_CONSTRUCTOR_BONUS["both_q2"]
    elif d1_q2 or d2_q2:
        pts += QUALI_CONSTRUCTOR_BONUS["one_q2"]
    else:
        pts += QUALI_CONSTRUCTOR_BONUS["neither_q2"]

    return float(pts)


def count_transfers(new_drivers, new_constructors, current_drivers, current_constructors,
                    new_turbo=None, current_turbo=None):
    """
    Number of transfers needed to move from current team to new lineup.
    Each driver/constructor brought IN counts as 1 transfer.
    Changing the Turbo Driver (2x chip) also counts as 1 transfer, even if
    the roster is otherwise unchanged.
    """
    driver_ins      = len(set(new_drivers)      - set(current_drivers))
    constructor_ins = len(set(new_constructors) - set(current_constructors))
    turbo_change    = (1 if current_turbo is not None
                            and new_turbo is not None
                            and new_turbo != current_turbo
                       else 0)
    return driver_ins + constructor_ins + turbo_change


def optimize_lineup(drivers_df, constructors_df, use_turbo=True,
                    current_drivers=None, current_constructors=None,
                    max_free_transfers=None, transfer_penalty=-10,
                    current_turbo_driver=None):
    """
    Brute-force optimizer: enumerate all valid driver/constructor combos and
    pick the one with the highest expected points under budget constraints.

    22 drivers C 5 = 26,334  ×  11 constructors C 2 = 55  ≈ 1.4M combos.
    Runs in under a second on modern hardware — no external solver needed.

    use_turbo: if True, also picks the best Turbo Driver (2x chip) from the
               selected 5 — the driver whose doubled points add the most.
               The turbo multiplier is applied to pts only, not price.

    current_drivers / current_constructors: your existing team. When provided,
        transfers are counted and a penalty is applied for exceeding
        max_free_transfers (default: each extra transfer = transfer_penalty pts).
        The optimizer finds the best net-points lineup accounting for this cost.

    current_turbo_driver: the Turbo Driver you had last race. Switching to a
        different Turbo Driver counts as 1 additional transfer.

    drivers_df columns:      driver_code, team, price, expected_pts
    constructors_df columns: team, price, expected_pts

    Returns dict: drivers (list), constructors (list), total_price,
                  projected_pts, turbo_driver (str or None),
                  transfers (int), penalty (float).
    """
    d_pts   = dict(zip(drivers_df["driver_code"], drivers_df["expected_pts"]))
    d_price = dict(zip(drivers_df["driver_code"], drivers_df["price"]))
    d_team  = dict(zip(drivers_df["driver_code"], drivers_df["team"]))
    c_pts   = dict(zip(constructors_df["team"], constructors_df["expected_pts"]))
    c_price = dict(zip(constructors_df["team"], constructors_df["price"]))

    all_drivers      = list(d_pts)
    all_constructors = list(c_pts)
    has_current      = current_drivers is not None and current_constructors is not None

    best_pts    = -1e9
    best_lineup = None

    for driver_combo in combinations(all_drivers, DRIVER_COUNT):
        # Check team spread constraint
        team_counts = {}
        for d in driver_combo:
            t = d_team[d]
            team_counts[t] = team_counts.get(t, 0) + 1
        if max(team_counts.values()) > MAX_DRIVERS_PER_TEAM:
            continue

        driver_price    = sum(d_price[d] for d in driver_combo)
        base_driver_pts = sum(d_pts[d]   for d in driver_combo)

        # Best turbo target: driver with highest pts (adding their pts again = +1x)
        if use_turbo:
            turbo_d     = max(driver_combo, key=lambda d: d_pts[d])
            turbo_bonus = d_pts[turbo_d]   # +1x on top of the base 1x
        else:
            turbo_d, turbo_bonus = None, 0.0

        driver_pts = base_driver_pts + turbo_bonus

        for cons_combo in combinations(all_constructors, CONSTRUCTOR_COUNT):
            total_price = driver_price + sum(c_price[t] for t in cons_combo)
            if total_price > BUDGET:
                continue

            raw_pts = driver_pts + sum(c_pts[t] for t in cons_combo)

            # Transfer penalty
            penalty = 0.0
            transfers = 0
            if has_current and max_free_transfers is not None:
                transfers = count_transfers(
                    driver_combo, cons_combo,
                    current_drivers, current_constructors,
                    new_turbo=turbo_d if use_turbo else None,
                    current_turbo=current_turbo_driver,
                )
                extra = max(0, transfers - max_free_transfers)
                penalty = extra * transfer_penalty   # negative value

            net_pts = raw_pts + penalty
            if net_pts > best_pts:
                best_pts    = net_pts
                best_lineup = (driver_combo, cons_combo, total_price,
                               turbo_d, transfers, penalty)

    if best_lineup is None:
        raise RuntimeError("No feasible lineup found within budget constraints.")

    drv, cons, total_price, turbo_driver, transfers, penalty = best_lineup
    return {
        "drivers":       list(drv),
        "constructors":  list(cons),
        "total_price":   float(total_price),
        "projected_pts": float(best_pts),   # net of any transfer penalty
        "turbo_driver":  turbo_driver,
        "transfers":     transfers,
        "penalty":       float(penalty),
    }


def print_lineup(result, drivers_df, constructors_df, race_name, lock_mode):
    """Print the optimised fantasy lineup."""
    turbo = result.get("turbo_driver")

    print("\n" + "=" * 62)
    print(f"  FANTASY LINEUP: {race_name.upper()} ({lock_mode})")
    print("=" * 62)

    print("\n  DRIVERS:")
    sorted_drivers = sorted(
        result["drivers"],
        key=lambda d: -drivers_df.loc[drivers_df["driver_code"] == d, "expected_pts"].values[0],
    )
    for d in sorted_drivers:
        row  = drivers_df.loc[drivers_df["driver_code"] == d].iloc[0]
        pts  = row["expected_pts"]
        tag  = "  [2x TURBO]" if d == turbo else ""
        disp = pts * 2 if d == turbo else pts
        print(f"    {d:<5} {row['team']:<16} ${row['price']/1e6:.1f}M"
              f"  →  est. {disp:.1f} pts{tag}")

    print("\n  CONSTRUCTORS:")
    sorted_cons = sorted(
        result["constructors"],
        key=lambda t: -constructors_df.loc[constructors_df["team"] == t, "expected_pts"].values[0],
    )
    for t in sorted_cons:
        row = constructors_df.loc[constructors_df["team"] == t].iloc[0]
        print(f"    {t:<20} ${row['price']/1e6:.1f}M"
              f"  →  est. {row['expected_pts']:.1f} pts")

    print(f"\n  TOTAL SPEND:      ${result['total_price']/1e6:.1f}M / ${BUDGET/1e6:.0f}M")
    print(f"  REMAINING:        ${(BUDGET - result['total_price'])/1e6:.1f}M")
    if turbo:
        turbo_pts = drivers_df.loc[drivers_df["driver_code"] == turbo, "expected_pts"].values[0]
        print(f"  TURBO DRIVER:     {turbo} (+{turbo_pts:.1f} bonus pts from 2x chip)")
    transfers = result.get("transfers")
    penalty   = result.get("penalty", 0.0)
    if transfers is not None:
        if penalty < 0:
            print(f"  TRANSFERS:        {transfers}  ({int(abs(penalty))} pt penalty for {int(abs(penalty/10))} extra transfer(s))")
        else:
            print(f"  TRANSFERS:        {transfers}  (within free limit — no penalty)")
    print(f"  PROJECTED POINTS: {result['projected_pts']:.1f}"
          + (f"  (gross {result['projected_pts'] - penalty:.1f} − {int(abs(penalty))} penalty)" if penalty < 0 else ""))
    print("=" * 62)
