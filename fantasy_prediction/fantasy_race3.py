import os
import sys
import json
import pandas as pd
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(__file__))
from fantasy_common import (
    score_driver, score_constructor, optimize_lineup, print_lineup,
    soft_equivalent, BUDGET,
)

# ── Config ───────────────────────────────────────────────────────────
# Normal weekend: FP1 → FP2 → FP3 → Race Qualifying → Race
# Team locks before race qualifying, so all three FP sessions are available.
LOCK_MODE      = "pre_race_quali_lock"
REFRESH_FASTF1 = True  # set True to repull FP sessions from FastF1

RACE_NAME  = "Japanese GP"
RACE_ROUND = 3

# ── Current team — fill in before running ────────────────────────────
# NEW_TEAM_ONLY = True  → ignore current team, find globally best lineup
#                         (use this for round 1 or when using a Wildcard chip)
# NEW_TEAM_ONLY = False → respect transfer limit; penalise extra transfers
#
# MAX_FREE_TRANSFERS: free transfers available this week (typically 3).
# Extra transfers beyond this are penalised at -10 pts each.
NEW_TEAM_ONLY        = True
MAX_FREE_TRANSFERS   = 3
CURRENT_DRIVERS      = ["RUS", "ANT", "LIN", "HUL", "BEA"]
CURRENT_CONSTRUCTORS = ["Audi", "Ferrari"]

# ── Driver → Team mapping ─────────────────────────────────────────────
driver_to_team = {
    "RUS": "Mercedes",      "ANT": "Mercedes",
    "LEC": "Ferrari",       "HAM": "Ferrari",
    "VER": "Red Bull",      "HAD": "Red Bull",
    "NOR": "McLaren",       "PIA": "McLaren",
    "ALB": "Williams",      "SAI": "Williams",
    "ALO": "Aston Martin",  "STR": "Aston Martin",
    "BEA": "Haas",          "OCO": "Haas",
    "LAW": "Racing Bulls",  "LIN": "Racing Bulls",
    "HUL": "Audi",          "BOR": "Audi",
    "GAS": "Alpine",        "COL": "Alpine",
    "PER": "Cadillac",      "BOT": "Cadillac",
}

# ── 2026 F1 Fantasy prices post-CHN — UPDATE FROM F1 FANTASY WEBSITE ─
# These are estimates based on performance through 2 rounds.
# Replace with official prices from fantasy.formula1.com before locking.
driver_prices = {
    "RUS": 28_000_000, "ANT": 23_800_000, "HAM": 22_900_000,
    "LEC": 23_400_000, "NOR": 26_800_000, "PIA": 24_900_000,
    "VER": 28_100_000, "HAD": 13_900_000, "LAW": 6_900_000,
    "BEA": 8_600_000, "GAS": 12_800_000, "HUL": 5_600_000,
    "LIN": 7_400_000, "OCO": 8_500_000, "COL": 7_000_000,
    "SAI": 12_200_000, "ALB": 10_800_000, "ALO": 8_800_000,
    "BOR":  6_400_000, "BOT":  4_700_000, "STR":  6_800_000,
    "PER":  6_400_000,
}
constructor_prices = {
    "Mercedes":     29_900_000, "Ferrari":      23_900_000,
    "McLaren":      28_500_000, "Red Bull":     28_800_000,
    "Haas":         8_600_000, "Racing Bulls": 7_500_000,
    "Alpine":       13_700_000, "Williams":      13_200_000,
    "Audi":          5_400_000, "Aston Martin":  9_100_000,
    "Cadillac":      5_200_000,
}

# ── Team performance: 2026 F1 championship points after 2 rounds ──────
# AUS race + CHN sprint + CHN race (constructor championship points)
team_points_2026 = {
    "Mercedes":     211,   # AUS(43) + CHN sprint(8) + CHN race(43)
    "Ferrari":      188,   # AUS(27) + CHN sprint(13) + CHN race(27)
    "McLaren":      12,   # AUS(10) + CHN sprint(9) — DNF in CHN race
    "Haas":         99,   # AUS(6) + CHN sprint(2) + CHN race(10)
    "Racing Bulls": 85,   # AUS(4) + CHN sprint(3) + CHN race(6)
    "Red Bull":     87,   # AUS(8) + CHN sprint(1) + CHN race(4)
    "Alpine":       67,   # AUS(1) + CHN race(9)
    "Williams":     42,   # CHN race(2)
    "Audi":          -4,   # AUS(2)
    "Aston Martin":  -58,
    "Cadillac":      9,
}
max_pts = max(team_points_2026.values())
team_score = {t: max(p, 0.5) / max_pts for t, p in team_points_2026.items()}

# ── Recent form: finish positions (DNF → 20) ─────────────────────────
#
# AUS race: Russell won, Antonelli 2nd, Leclerc 3rd, Hamilton 4th
aus_finish_pos = {
    "RUS": 1,  "ANT": 2,  "LEC": 3,  "HAM": 4,
    "NOR": 5,  "VER": 6,  "BEA": 7,  "LIN": 8,
    "BOR": 9,  "GAS": 10, "OCO": 11, "ALB": 12,
    "LAW": 13, "COL": 14, "SAI": 15, "PER": 16,
    "STR": 17, "ALO": 20, "BOT": 20, "HAD": 20,
    "PIA": 20, "HUL": 20,
}

# CHN race (real FastF1 data): Antonelli won
chn_finish_pos = {
    "ANT": 1,  "RUS": 2,  "HAM": 3,  "LEC": 4,
    "BEA": 5,  "GAS": 6,  "LAW": 7,  "HAD": 8,
    "SAI": 9,  "COL": 10, "HUL": 11, "LIN": 12,
    "BOT": 13, "OCO": 14, "PER": 15,
    # DNF: VER, ALO, STR, PIA, NOR, BOR, ALB
    "VER": 20, "ALO": 20, "STR": 20, "PIA": 20,
    "NOR": 20, "BOR": 20, "ALB": 20,
}

# ── FP session data — loaded exclusively from FastF1 snapshot ─────────
# No placeholder values. Only real data from FastF1 is used.
# FP1 was pulled on 2026-03-21 and is already in the snapshot.
# Run with REFRESH_FASTF1 = True after FP2/FP3 to pull those sessions.
fp1_jpn: dict = {}
fp2_jpn: dict = {}
fp3_jpn: dict = {}

SNAPSHOT_PATH = os.path.join(
    os.path.dirname(__file__), "data_snapshots", "jpn_2026_fp.json"
)

def _fastf1_best_lap_with_compound(session):
    """Return {driver_code: (time_s, compound)} for the fastest lap per driver."""
    laps = session.laps.pick_quicklaps()
    result = {}
    for drv, grp in laps.groupby("Driver"):
        idx = grp["LapTime"].idxmin()
        row = grp.loc[idx]
        result[drv] = (row["LapTime"].total_seconds(),
                       str(row.get("Compound", "UNKNOWN") or "UNKNOWN").upper())
    return result

if REFRESH_FASTF1:
    try:
        import fastf1
        fastf1.Cache.enable_cache("f1_cache")
        # Load existing snapshot so we don't lose sessions already saved
        existing = {}
        if os.path.exists(SNAPSHOT_PATH):
            with open(SNAPSHOT_PATH) as f:
                existing = json.load(f)
        for session_name, target in [("FP1", fp1_jpn), ("FP2", fp2_jpn), ("FP3", fp3_jpn)]:
            try:
                s = fastf1.get_session(2026, "Japan", session_name)
                s.load(telemetry=False, weather=False, messages=False)
                data = _fastf1_best_lap_with_compound(s)
                data = {d: v for d, v in data.items() if d in driver_to_team}
                if data:
                    target.update(data)
                    existing[session_name] = {d: list(v) for d, v in data.items()}
                    print(f"  FastF1 {session_name}: {len(data)} drivers loaded")
                else:
                    print(f"  FastF1 {session_name}: no lap data available yet — skipped")
            except Exception as e:
                print(f"  FastF1 {session_name}: unavailable — skipped ({e})")
        with open(SNAPSHOT_PATH, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"Snapshot saved → {SNAPSHOT_PATH}")
    except Exception as e:
        print(f"FastF1 unavailable ({e})")

if os.path.exists(SNAPSHOT_PATH):
    with open(SNAPSHOT_PATH) as f:
        snap = json.load(f)
    for session_name, target in [("FP1", fp1_jpn), ("FP2", fp2_jpn), ("FP3", fp3_jpn)]:
        if session_name in snap:
            data = {d: tuple(v) for d, v in snap[session_name].items()
                    if d in driver_to_team}
            target.update(data)
    available = [s for s in ("FP1", "FP2", "FP3") if s in snap]
    missing   = [s for s in ("FP1", "FP2", "FP3") if s not in snap]
    print(f"Snapshot loaded — real data: {', '.join(available)}"
          + (f" | not yet available: {', '.join(missing)}" if missing else ""))
else:
    raise FileNotFoundError(
        f"No snapshot found at {SNAPSHOT_PATH}. "
        "Set REFRESH_FASTF1 = True to pull data from FastF1."
    )

# ── Build driver DataFrame ────────────────────────────────────────────
drivers = list(driver_to_team.keys())
df = pd.DataFrame({
    "driver_code": drivers,
    "team":        [driver_to_team[d] for d in drivers],
    "price":       [driver_prices[d]  for d in drivers],
    "team_score":  [team_score[driver_to_team[d]] for d in drivers],
})

def _gap_norm(series):
    """Normalise gap-from-best: 0 = fastest / best, 1 = slowest / worst."""
    best = series.min()
    span = series.max() - best
    return (series - best) / (span if span > 0 else 1)

# Soft-equivalent lap times — only for sessions with real data
have_fp1 = bool(fp1_jpn)
have_fp2 = bool(fp2_jpn)
have_fp3 = bool(fp3_jpn)

if not have_fp1:
    raise RuntimeError("FP1 data is missing. Set REFRESH_FASTF1 = True to pull from FastF1.")

df["fp1_norm"] = _gap_norm(df["driver_code"].map(
    lambda d: soft_equivalent(*fp1_jpn.get(d, (98.0, "UNKNOWN")))
))
if have_fp2:
    df["fp2_norm"] = _gap_norm(df["driver_code"].map(
        lambda d: soft_equivalent(*fp2_jpn.get(d, (98.0, "UNKNOWN")))
    ))
if have_fp3:
    df["fp3_norm"] = _gap_norm(df["driver_code"].map(
        lambda d: soft_equivalent(*fp3_jpn.get(d, (98.0, "UNKNOWN")))
    ))

# Recent form: recency-weighted finish positions (60% CHN, 40% AUS)
df["form_pos"] = df["driver_code"].map(
    lambda d: 0.60 * chn_finish_pos.get(d, 20) + 0.40 * aus_finish_pos.get(d, 20)
)
df["form_norm"] = _gap_norm(df["form_pos"])

max_team = df["team_score"].max()
df["team_norm"] = 1.0 - df["team_score"] / max_team   # 0 = strongest team

# ── Feature model — weights adapt to which sessions are available ──────
#
# Full model (FP1 + FP2 + FP3):
#   Quali: FP3 50% | FP1 20% | team 15% | form 15%
#   Race:  FP2 40% | FP3 25% | team 15% | form 15% | FP1 5%
#
# FP1 + FP2 only (FP3 not yet run):
#   Quali: FP2 55% | FP1 25% | team 10% | form 10%
#   Race:  FP2 55% | FP1 15% | team 15% | form 15%
#   (FP2 at Suzuka was all SOFT — usable as quali-pace proxy too)
#
# FP1 only (fallback):
#   Quali: FP1 50% | team 25% | form 25%
#   Race:  FP1 40% | team 30% | form 30%
#
# Lower score = better predicted performance.

if have_fp1 and have_fp2 and have_fp3:
    df["quali_score"] = (
        0.50 * df["fp3_norm"] +
        0.20 * df["fp1_norm"] +
        0.15 * df["team_norm"] +
        0.15 * df["form_norm"]
    )
    df["race_score"] = (
        0.40 * df["fp2_norm"] +
        0.25 * df["fp3_norm"] +
        0.15 * df["team_norm"] +
        0.15 * df["form_norm"] +
        0.05 * df["fp1_norm"]
    )
    quali_model_desc = "FP3 50% | FP1 20% | Team 15% | Form 15%"
    race_model_desc  = "FP2 40% | FP3 25% | Team 15% | Form 15% | FP1 5%"

elif have_fp1 and have_fp2:
    df["quali_score"] = (
        0.55 * df["fp2_norm"] +
        0.25 * df["fp1_norm"] +
        0.10 * df["team_norm"] +
        0.10 * df["form_norm"]
    )
    df["race_score"] = (
        0.55 * df["fp2_norm"] +
        0.15 * df["fp1_norm"] +
        0.15 * df["team_norm"] +
        0.15 * df["form_norm"]
    )
    quali_model_desc = "FP2 55% | FP1 25% | Team 10% | Form 10%  [FP3 not yet run]"
    race_model_desc  = "FP2 55% | FP1 15% | Team 15% | Form 15%  [FP3 not yet run]"

else:  # FP1 only
    df["quali_score"] = (
        0.50 * df["fp1_norm"] +
        0.25 * df["team_norm"] +
        0.25 * df["form_norm"]
    )
    df["race_score"] = (
        0.40 * df["fp1_norm"] +
        0.30 * df["team_norm"] +
        0.30 * df["form_norm"]
    )
    quali_model_desc = "FP1 50% | Team 25% | Form 25%  [FP2/FP3 not yet run]"
    race_model_desc  = "FP1 40% | Team 30% | Form 30%  [FP2/FP3 not yet run]"

df_q = df.sort_values("quali_score").reset_index(drop=True)
df_r = df.sort_values("race_score").reset_index(drop=True)

df = df.merge(
    df_q[["driver_code"]].reset_index().rename(columns={"index": "pred_quali_pos"}),
    on="driver_code",
)
df = df.merge(
    df_r[["driver_code"]].reset_index().rename(columns={"index": "pred_race_pos"}),
    on="driver_code",
)
df["pred_quali_pos"] += 1   # 0-indexed → 1-indexed
df["pred_race_pos"]  += 1

df["expected_pts"] = df.apply(
    lambda r: score_driver(int(r.pred_quali_pos), int(r.pred_race_pos)), axis=1
)

# ── Build constructor DataFrame ───────────────────────────────────────
constructors = list(constructor_prices.keys())
team_pred = {}
for team in constructors:
    td = df[df["team"] == team].sort_values("pred_race_pos")
    if len(td) >= 2:
        team_pred[team] = {
            "d1_quali": int(td.iloc[0]["pred_quali_pos"]),
            "d2_quali": int(td.iloc[1]["pred_quali_pos"]),
            "d1_race":  int(td.iloc[0]["pred_race_pos"]),
            "d2_race":  int(td.iloc[1]["pred_race_pos"]),
        }
    else:
        team_pred[team] = {"d1_quali": 22, "d2_quali": 22, "d1_race": 22, "d2_race": 22}

cons_df = pd.DataFrame([
    {"team": t, "price": constructor_prices[t], **team_pred[t]}
    for t in constructors
])
cons_df["expected_pts"] = cons_df.apply(
    lambda r: score_constructor(
        int(r.d1_quali), int(r.d2_quali), int(r.d1_race), int(r.d2_race)
    ),
    axis=1,
)

# ── Optimise lineup ───────────────────────────────────────────────────
result = optimize_lineup(
    df, cons_df,
    use_turbo=True,
    current_drivers=None if NEW_TEAM_ONLY else CURRENT_DRIVERS,
    current_constructors=None if NEW_TEAM_ONLY else CURRENT_CONSTRUCTORS,
    max_free_transfers=None if NEW_TEAM_ONLY else MAX_FREE_TRANSFERS,
)

assert result["total_price"] <= BUDGET, "Budget constraint violated!"
assert len(result["drivers"]) == 5
assert len(result["constructors"]) == 2
team_counts = {}
for d in result["drivers"]:
    t = driver_to_team[d]
    team_counts[t] = team_counts.get(t, 0) + 1
assert max(team_counts.values()) <= 2, "Max 2 drivers per team violated!"

# ── Print output ──────────────────────────────────────────────────────
print_lineup(result, df, cons_df, RACE_NAME, LOCK_MODE)

_real  = [s for s in ("FP1", "FP2", "FP3") if s in snap]
_miss  = [s for s in ("FP1", "FP2", "FP3") if s not in snap]
print(f"\n  Quali model:  {quali_model_desc}")
print(f"  Race model:   {race_model_desc}")
print(f"  All FP times compound-normalised to soft-equivalent.")
print(f"  Form: CHN finish 60% + AUS finish 40% (recency-weighted).")
print(f"  Real FastF1 data: {', '.join(_real)}.")
if _miss:
    print(f"  Not yet available: {', '.join(_miss)} — set REFRESH_FASTF1=True after sessions run.")
print(f"  IMPORTANT: Update driver_prices and constructor_prices from fantasy.formula1.com before locking.")
