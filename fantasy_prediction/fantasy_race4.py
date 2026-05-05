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
# Miami is a SPRINT weekend. Session order:
#   FP1 → Sprint Qualifying → Sprint Race → Qualifying → Race
#
# LOCK_MODE options:
#   "pre_quali_lock"  — lock before Qualifying (Saturday). Uses FP1 pace +
#                       Sprint Qualifying grid + Sprint Race results as signals.
#                       This is the DEFAULT and most data-rich option.
#   "pre_sprint_lock" — lock before the Sprint Race (Saturday morning).
#                       Only FP1 + Sprint Qualifying grid available at this point.
#
# Switch LOCK_MODE to "pre_sprint_lock" if you need to lock before the sprint.
LOCK_MODE      = "pre_sprint_lock"
REFRESH_FASTF1 = True   # set True to pull live session data from FastF1

RACE_NAME  = "Miami GP"
RACE_ROUND = 4   # 4th race in this project's scripts (Bahrain & Saudi cancelled)

# ── Current team — fill in before running ────────────────────────────
# NEW_TEAM_ONLY = True  → ignore current team, find globally best lineup
#                         (use this for a Wildcard chip)
# NEW_TEAM_ONLY = False → respect transfer limit; penalise extra transfers
#
# Update CURRENT_DRIVERS / CURRENT_CONSTRUCTORS with your JPN-recommended team.
# MAX_FREE_TRANSFERS: free transfers available this week (typically 3).
NEW_TEAM_ONLY         = False
MAX_FREE_TRANSFERS    = 2   # 2 free transfers available heading into Miami
CURRENT_DRIVERS       = ["ANT", "BEA", "LAW", "GAS", "OCO"]
CURRENT_CONSTRUCTORS  = ["Mercedes", "Haas"]
CURRENT_TURBO_DRIVER  = "ANT"

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

# ── 2026 F1 Fantasy prices — confirmed from fantasy.formula1.com ──────
driver_prices = {
    "ANT": 24_100_000, "RUS": 28_300_000, "LEC": 23_700_000,
    "HAM": 23_200_000, "VER": 28_200_000, "LAW":  7_500_000,
    "GAS": 13_000_000, "OCO":  9_100_000, "SAI": 12_400_000,
    "BEA":  9_200_000, "NOR": 26_500_000, "PER":  7_000_000,
    "COL":  7_600_000, "LIN":  7_600_000, "PIA": 24_600_000,
    "HAD": 13_300_000, "BOR":  5_800_000, "ALB": 10_200_000,
    "HUL":  5_000_000, "BOT":  4_100_000, "ALO":  8_200_000,
    "STR":  6_200_000,
}
# ── Constructor prices — confirmed from fantasy.formula1.com ──────────
constructor_prices = {
    "Mercedes":     30_200_000, "Ferrari":      24_200_000,
    "Red Bull":     29_100_000, "Racing Bulls":  8_100_000,
    "Haas":          9_200_000, "Alpine":       14_300_000,
    "McLaren":      28_600_000, "Williams":     13_800_000,
    "Audi":          5_600_000, "Aston Martin":  8_500_000,
    "Cadillac":      5_000_000,
}

# ── Team performance: official F1 Fantasy constructor points (post-JPN) ─
# Source: fantasy.formula1.com constructor leaderboard — includes all bonuses
# (qualifying tier, pitstop, positions gained, etc.), not just race finish pts.
team_points_2026 = {
    "Mercedes":     303,
    "Ferrari":      263,
    "Red Bull":     112,
    "Racing Bulls": 103,
    "Haas":          95,
    "Alpine":        92,
    "McLaren":       84,
    "Williams":      51,
    "Audi":          19,
    "Cadillac":      14,
    "Aston Martin":  -70,
}
max_pts = max(team_points_2026.values())
team_score = {t: max(p, 0.5) / max_pts for t, p in team_points_2026.items()}

# ── Recent form: finish positions (DNF → 20) ─────────────────────────
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
    "VER": 20, "ALO": 20, "STR": 20, "PIA": 20,
    "NOR": 20, "BOR": 20, "ALB": 20,
}

# JPN race result (Suzuka, March 29)
# Positions 14–20 estimated — verify and update if needed.
jpn_finish_pos = {
    "ANT": 1,  "PIA": 2,  "LEC": 3,  "RUS": 4,
    "NOR": 5,  "HAM": 6,  "GAS": 7,  "VER": 8,
    "LAW": 9,  "OCO": 10, "HUL": 11, "HAD": 12,
    "BOR": 13, "LIN": 14, "SAI": 15, "ALB": 16,
    "COL": 17, "ALO": 18, "PER": 19, "BOT": 20,
    "BEA": 20, "STR": 20,   # DNF
}

# ── FP session data — loaded exclusively from FastF1 snapshot ─────────
# Miami is a SPRINT WEEKEND — only FP1 is run as a traditional practice session.
# The script also pulls:
#   "Sprint Qualifying" → used as quali-pace proxy (fp2 equivalent)
#   "Sprint"            → used as race-pace proxy  (fp3 equivalent)
# If these sessions haven't happened yet, only fp1 data will be available.
# Run with REFRESH_FASTF1 = True after each session completes.
fp1_mia: dict = {}
fp_sq_mia: dict = {}    # Sprint Qualifying (quali-pace proxy)
fp_sr_mia: dict = {}    # Sprint Race best lap (race-pace proxy)

SNAPSHOT_PATH = os.path.join(
    os.path.dirname(__file__), "data_snapshots", "mia_2026_fp.json"
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
        existing = {}
        if os.path.exists(SNAPSHOT_PATH):
            with open(SNAPSHOT_PATH) as f:
                existing = json.load(f)
        # Sprint weekend sessions: FP1, Sprint Qualifying, Sprint (race)
        session_map = [
            ("FP1",               fp1_mia,    "FP1"),
            ("Sprint Qualifying", fp_sq_mia,  "SQ"),
            ("Sprint",            fp_sr_mia,  "SR"),
        ]
        for fastf1_name, target, snap_key in session_map:
            try:
                s = fastf1.get_session(2026, "Miami", fastf1_name)
                s.load(telemetry=False, weather=False, messages=False)
                data = _fastf1_best_lap_with_compound(s)
                data = {d: v for d, v in data.items() if d in driver_to_team}
                if data:
                    target.update(data)
                    existing[snap_key] = {d: list(v) for d, v in data.items()}
                    print(f"  FastF1 {fastf1_name}: {len(data)} drivers loaded")
                else:
                    print(f"  FastF1 {fastf1_name}: no lap data available yet — skipped")
            except Exception as e:
                print(f"  FastF1 {fastf1_name}: unavailable — skipped ({e})")
        with open(SNAPSHOT_PATH, "w") as f:
            json.dump(existing, f, indent=2)
        print(f"Snapshot saved → {SNAPSHOT_PATH}")
    except Exception as e:
        print(f"FastF1 unavailable ({e})")

if os.path.exists(SNAPSHOT_PATH):
    with open(SNAPSHOT_PATH) as f:
        snap = json.load(f)
    for snap_key, target in [("FP1", fp1_mia), ("SQ", fp_sq_mia), ("SR", fp_sr_mia)]:
        if snap_key in snap:
            data = {d: tuple(v) for d, v in snap[snap_key].items()
                    if d in driver_to_team}
            target.update(data)
    available = [k for k in ("FP1", "SQ", "SR") if k in snap]
    missing   = [k for k in ("FP1", "SQ", "SR") if k not in snap]
    labels    = {"FP1": "FP1", "SQ": "Sprint Qualifying", "SR": "Sprint Race"}
    print(f"Snapshot loaded — real data: {', '.join(labels[k] for k in available)}"
          + (f" | not yet available: {', '.join(labels[k] for k in missing)}" if missing else ""))
else:
    print("No snapshot found. Set REFRESH_FASTF1 = True to pull data from FastF1.")

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

have_fp1 = bool(fp1_mia)
have_sq  = bool(fp_sq_mia)    # Sprint Qualifying (quali proxy)
have_sr  = bool(fp_sr_mia)    # Sprint Race (race proxy)

if not have_fp1:
    raise RuntimeError("FP1 data is missing. Set REFRESH_FASTF1 = True to pull from FastF1.")

df["fp1_norm"] = _gap_norm(df["driver_code"].map(
    lambda d: soft_equivalent(*fp1_mia.get(d, (95.0, "UNKNOWN")))
))
if have_sq:
    df["sq_norm"] = _gap_norm(df["driver_code"].map(
        lambda d: soft_equivalent(*fp_sq_mia.get(d, (95.0, "UNKNOWN")))
    ))
if have_sr:
    df["sr_norm"] = _gap_norm(df["driver_code"].map(
        lambda d: soft_equivalent(*fp_sr_mia.get(d, (95.0, "UNKNOWN")))
    ))

# Recent form: JPN 50% + CHN 30% + AUS 20% (recency-weighted, 3 completed races)
df["form_pos"] = df["driver_code"].map(
    lambda d: (0.50 * jpn_finish_pos.get(d, 20)
             + 0.30 * chn_finish_pos.get(d, 20)
             + 0.20 * aus_finish_pos.get(d, 20))
)
df["form_norm"] = _gap_norm(df["form_pos"])

max_team = df["team_score"].max()
df["team_norm"] = 1.0 - df["team_score"] / max_team   # 0 = strongest team

# ── Feature model — weights adapt to which sessions are available ──────
#
# Sprint weekend session mapping:
#   fp1_norm  → FP1 best lap (raw pace baseline)
#   sq_norm   → Sprint Qualifying best lap (best quali-pace proxy on a sprint weekend)
#   sr_norm   → Sprint Race best lap (best race-pace proxy on a sprint weekend)
#
# Full model (FP1 + Sprint Qualifying + Sprint Race):
#   Quali: SQ 55% | FP1 20% | team 15% | form 10%
#   Race:  SR 45% | SQ 25% | team 15% | form 15%
#
# FP1 + Sprint Qualifying only:
#   Quali: SQ 60% | FP1 20% | team 10% | form 10%
#   Race:  SQ 50% | FP1 20% | team 15% | form 15%
#
# FP1 only (fallback, pre-sprint):
#   Quali: FP1 50% | team 25% | form 25%
#   Race:  FP1 40% | team 30% | form 30%
#
# Lower score = better predicted performance.

if have_fp1 and have_sq and have_sr:
    df["quali_score"] = (
        0.55 * df["sq_norm"] +
        0.20 * df["fp1_norm"] +
        0.15 * df["team_norm"] +
        0.10 * df["form_norm"]
    )
    df["race_score"] = (
        0.45 * df["sr_norm"] +
        0.25 * df["sq_norm"] +
        0.15 * df["team_norm"] +
        0.15 * df["form_norm"]
    )
    quali_model_desc = "Sprint Quali 55% | FP1 20% | Team 15% | Form 10%"
    race_model_desc  = "Sprint Race 45% | Sprint Quali 25% | Team 15% | Form 15%"

elif have_fp1 and have_sq:
    df["quali_score"] = (
        0.60 * df["sq_norm"] +
        0.20 * df["fp1_norm"] +
        0.10 * df["team_norm"] +
        0.10 * df["form_norm"]
    )
    df["race_score"] = (
        0.50 * df["sq_norm"] +
        0.20 * df["fp1_norm"] +
        0.15 * df["team_norm"] +
        0.15 * df["form_norm"]
    )
    quali_model_desc = "Sprint Quali 60% | FP1 20% | Team 10% | Form 10%  [Sprint Race not yet run]"
    race_model_desc  = "Sprint Quali 50% | FP1 20% | Team 15% | Form 15%  [Sprint Race not yet run]"

else:  # FP1 only (pre-sprint, very early)
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
    quali_model_desc = "FP1 50% | Team 25% | Form 25%  [Sprint sessions not yet run]"
    race_model_desc  = "FP1 40% | Team 30% | Form 30%  [Sprint sessions not yet run]"

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
df["pred_quali_pos"] += 1
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
    current_turbo_driver=None if NEW_TEAM_ONLY else CURRENT_TURBO_DRIVER,
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

_available = [k for k in ("FP1", "SQ", "SR") if k in (snap if os.path.exists(SNAPSHOT_PATH) else {})]
_labels    = {"FP1": "FP1", "SQ": "Sprint Qualifying", "SR": "Sprint Race"}
_miss      = [k for k in ("FP1", "SQ", "SR") if k not in _available]

print(f"\n  Quali model:  {quali_model_desc}")
print(f"  Race model:   {race_model_desc}")
print(f"  All FP times compound-normalised to soft-equivalent.")
print(f"  Form: JPN 50% + CHN 30% + AUS 20% (recency-weighted, 3 races).")
if _available:
    print(f"  Real FastF1 data: {', '.join(_labels[k] for k in _available)}.")
if _miss:
    print(f"  Not yet available: {', '.join(_labels[k] for k in _miss)} — set REFRESH_FASTF1=True after sessions run.")
print(f"  IMPORTANT: Update driver_prices and constructor_prices from fantasy.formula1.com before locking.")
print(f"  IMPORTANT: Update CURRENT_DRIVERS and CURRENT_CONSTRUCTORS with your actual JPN lineup.")
print(f"  NOTE: Miami is a sprint weekend — LOCK_MODE='pre_sprint_lock' available if locking before Sprint Race.")
