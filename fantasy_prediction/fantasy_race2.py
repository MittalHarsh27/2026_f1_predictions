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
# Sprint weekend session order:
#   FP1 → Sprint Qualifying → Sprint Race → [LOCK] → Race Qualifying → Race
#
# pre_sprint_quali_lock — only FP1 available; no sprint data yet
# pre_race_quali_lock   — FP1 + Sprint Qualifying + Sprint Race all done;
#                         team must be locked before race qualifying begins
#
# Set to whichever point in the weekend you're running this script.
LOCK_MODE      = "pre_race_quali_lock"
REFRESH_FASTF1 = False   # set True to repull sessions from FastF1

RACE_NAME  = "Chinese GP"
RACE_ROUND = 2

assert LOCK_MODE in ("pre_sprint_quali_lock", "pre_race_quali_lock"), (
    f"Unknown lock mode '{LOCK_MODE}'. "
    "Choose pre_sprint_quali_lock or pre_race_quali_lock."
)

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

# ── 2026 F1 Fantasy prices post-AUS — update from F1 Fantasy website ─
driver_prices = {
    "RUS": 25_000_000, "ANT": 20_000_000, "LEC": 22_000_000,
    "HAM": 20_000_000, "VER": 19_000_000, "NOR": 24_000_000,
    "PIA": 19_000_000, "HAD": 14_500_000, "LAW": 14_000_000,
    "GAS": 13_000_000, "BEA": 13_000_000, "HUL": 11_000_000,
    "LIN": 12_000_000, "OCO": 11_500_000, "COL": 10_500_000,
    "ALO": 10_000_000, "SAI": 10_000_000, "ALB": 10_500_000,
    "BOR": 10_000_000, "BOT":  8_000_000, "STR":  7_500_000,
    "PER":  8_000_000,
}
constructor_prices = {
    "McLaren":      23_000_000, "Mercedes":     24_000_000,
    "Ferrari":      19_000_000, "Red Bull":     17_000_000,
    "Racing Bulls": 13_500_000, "Williams":     11_000_000,
    "Haas":         12_000_000, "Audi":         10_000_000,
    "Alpine":        9_000_000, "Aston Martin":  8_500_000,
    "Cadillac":      6_500_000,
}

# ── Team performance (2026 season standings after AUS) ───────────────
team_points_2026 = {
    "Mercedes": 55, "Ferrari": 40, "McLaren": 18, "Red Bull": 8,
    "Haas": 7, "Racing Bulls": 6, "Audi": 2, "Alpine": 1,
    "Williams": 1, "Cadillac": 1, "Aston Martin": 1,
}
max_pts = max(team_points_2026.values())
team_score = {t: max(p, 0.5) / max_pts for t, p in team_points_2026.items()}

# ── Australia GP results (always available — happened before CHN) ─────
aus_finish_pos = {
    "RUS": 1,  "ANT": 2,  "LEC": 3,  "HAM": 4,
    "NOR": 5,  "VER": 6,  "BEA": 7,  "LIN": 8,
    "BOR": 9,  "GAS": 10, "OCO": 11, "ALB": 12,
    "LAW": 13, "COL": 14, "SAI": 15, "PER": 16,
    "STR": 17, "ALO": 20, "BOT": 20, "HAD": 20,
    "PIA": 21, "HUL": 21,
}

# ── China FP1 data: (best_lap_s, compound) ───────────────────────────
# Only one FP session in a sprint weekend.
fp1_chn = {
    "ANT": (92.50, "SOFT"),   "RUS": (92.65, "MEDIUM"), "NOR": (92.70, "SOFT"),
    "LEC": (92.80, "SOFT"),   "PIA": (92.85, "MEDIUM"), "HAM": (92.90, "SOFT"),
    "GAS": (93.10, "MEDIUM"), "VER": (93.25, "SOFT"),   "HAD": (93.40, "MEDIUM"),
    "BEA": (93.60, "SOFT"),   "LAW": (93.65, "MEDIUM"), "HUL": (93.75, "HARD"),
    "COL": (93.80, "MEDIUM"), "OCO": (93.85, "MEDIUM"), "LIN": (93.90, "SOFT"),
    "BOR": (93.95, "MEDIUM"), "SAI": (94.50, "HARD"),   "ALB": (94.60, "MEDIUM"),
    "ALO": (95.20, "HARD"),   "BOT": (95.40, "MEDIUM"), "STR": (95.80, "HARD"),
    "PER": (96.50, "HARD"),
}

# ── Sprint Qualifying times: (lap_time_s, compound) ──────────────────
# Source: racepace.py (China sprint quali sector times + overall lap)
# Compound is SOFT — sprint qualifying always uses fresh softs.
# Available for: pre_race_quali_lock only.
sprint_quali_chn = {
    "ANT": (92.064, "SOFT"), "RUS": (92.286, "SOFT"), "HAM": (92.415, "SOFT"),
    "LEC": (92.428, "SOFT"), "PIA": (92.550, "SOFT"), "NOR": (92.608, "SOFT"),
    "GAS": (92.873, "SOFT"), "VER": (93.002, "SOFT"), "HAD": (93.121, "SOFT"),
    "BEA": (93.292, "SOFT"), "HUL": (93.238, "SOFT"), "COL": (93.279, "SOFT"),
    "OCO": (93.404, "SOFT"), "LAW": (93.367, "SOFT"), "LIN": (93.403, "SOFT"),
    "BOR": (93.480, "SOFT"), "SAI": (94.317, "SOFT"), "ALB": (94.590, "SOFT"),
    "ALO": (95.203, "SOFT"), "BOT": (95.436, "SOFT"), "STR": (95.935, "SOFT"),
    "PER": (96.560, "SOFT"),
}

# ── Sprint Race data: total gap to winner (seconds) ──────────────────
# Source: prediction2.py sprint_gaps + sprint_penalties.
# Drivers with gap = 35.0 are DNF / not classified.
# Available for: pre_race_quali_lock only.
SPRINT_RACING_LAPS = 15

_sprint_gaps_raw = {
    "RUS": 0.000,  "LEC": 0.674,  "HAM": 2.554,  "NOR": 4.433,
    "ANT": 5.688,  "PIA": 6.809,  "LAW": 10.900, "BEA": 11.271,
    "VER": 11.619, "OCO": 13.887, "GAS": 14.780, "SAI": 15.753,
    "BOR": 15.858, "COL": 16.393, "HAD": 16.430, "ALB": 20.014,
    "ALO": 21.599, "STR": 21.971, "PER": 28.241,
    "HUL": 35.0,   "BOT": 35.0,   "LIN": 35.0,   # DNF / not classified
}
_sprint_penalties = {"ANT": 10.0, "PER": 5.0}

# Apply time penalties, then convert to per-lap gap
sprint_race_gap_per_lap = {
    d: max(_sprint_gaps_raw[d] - _sprint_penalties.get(d, 0.0), 0.0) / SPRINT_RACING_LAPS
    for d in _sprint_gaps_raw
}

# ── Optional FastF1 refresh ──────────────────────────────────────────
SNAPSHOT_PATH = os.path.join(
    os.path.dirname(__file__), "data_snapshots", "chn_2026_sprint.json"
)

def _fastf1_best_lap_with_compound(session):
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
        pulled = {}

        # FP1
        s_fp1 = fastf1.get_session(2026, "China", "FP1")
        s_fp1.load(telemetry=False, weather=False, messages=False)
        fp1_data = _fastf1_best_lap_with_compound(s_fp1)
        fp1_chn.update(fp1_data)
        pulled["FP1"] = {d: list(v) for d, v in fp1_data.items()}
        print(f"  FastF1 FP1: {len(fp1_data)} drivers loaded")

        # Sprint Qualifying
        s_sq = fastf1.get_session(2026, "China", "Sprint Qualifying")
        s_sq.load(telemetry=False, weather=False, messages=False)
        sq_data = _fastf1_best_lap_with_compound(s_sq)
        sprint_quali_chn.update(sq_data)
        pulled["SQ"] = {d: list(v) for d, v in sq_data.items()}
        print(f"  FastF1 Sprint Qualifying: {len(sq_data)} drivers loaded")

        # Sprint Race — compute gap-per-lap from results
        s_sr = fastf1.get_session(2026, "China", "Sprint")
        s_sr.load(telemetry=False, weather=False, messages=False)
        res = s_sr.results[["Abbreviation", "Time"]].copy()
        res = res.dropna(subset=["Time"])
        if not res.empty:
            winner_s = res["Time"].dt.total_seconds().min()
            res["gap_per_lap"] = (res["Time"].dt.total_seconds() - winner_s) / SPRINT_RACING_LAPS
            sr_data = dict(zip(res["Abbreviation"], res["gap_per_lap"]))
            sprint_race_gap_per_lap.update(sr_data)
            pulled["SR"] = sr_data
            print(f"  FastF1 Sprint Race: {len(sr_data)} drivers loaded")

        with open(SNAPSHOT_PATH, "w") as f:
            json.dump(pulled, f, indent=2)
        print(f"Snapshot saved → {SNAPSHOT_PATH}")

    except Exception as e:
        print(f"FastF1 unavailable — using hardcoded sprint data ({e})")

elif os.path.exists(SNAPSHOT_PATH):
    with open(SNAPSHOT_PATH) as f:
        snap = json.load(f)
    if "FP1" in snap:
        fp1_chn.update({d: tuple(v) for d, v in snap["FP1"].items()})
    if "SQ" in snap:
        sprint_quali_chn.update({d: tuple(v) for d, v in snap["SQ"].items()})
    if "SR" in snap:
        sprint_race_gap_per_lap.update(snap["SR"])
    print(f"Loaded sprint snapshot from {SNAPSHOT_PATH}")
else:
    print("Using hardcoded sprint data (FP1 / Sprint Qualifying / Sprint Race).")

# ── Build driver DataFrame ───────────────────────────────────────────
drivers = list(driver_to_team.keys())
df = pd.DataFrame({
    "driver_code": drivers,
    "team":        [driver_to_team[d] for d in drivers],
    "price":       [driver_prices[d]  for d in drivers],
    "aus_pos":     [aus_finish_pos.get(d, 20) for d in drivers],
    "team_score":  [team_score[driver_to_team[d]] for d in drivers],
})

# FP1 soft-equivalent (available for all lock modes)
df["fp1_se"]   = df["driver_code"].map(
    lambda d: soft_equivalent(*fp1_chn.get(d, (98.0, "UNKNOWN")))
)

def _gap_norm(series):
    best = series.min()
    span = series.max() - best
    return (series - best) / (span if span > 0 else 1)

df["fp1_norm"] = _gap_norm(df["fp1_se"])

max_team = df["team_score"].max()
df["team_norm"] = 1.0 - df["team_score"] / max_team   # 0 = strongest team

aus_norm = (df["aus_pos"] - 1) / 21

# ── Feature model by lock mode ────────────────────────────────────────
if LOCK_MODE == "pre_race_quali_lock":
    # Sprint Qualifying time → best proxy for race qualifying single-lap pace.
    # Sprint Race gap/lap → best proxy for race pace (actual race conditions).
    # FP1 + AUS form + team strength → background context.
    #
    # Quali prediction: sprint qualifying heavily weighted (it IS a qualifying
    #   session), supported by FP1 and team strength.
    # Race prediction: sprint race pace is primary signal (race conditions
    #   most similar to the main race), sprint quali adds single-lap context.

    df["sq_se"]   = df["driver_code"].map(
        lambda d: soft_equivalent(*sprint_quali_chn.get(d, (98.0, "SOFT")))
    )
    df["sq_norm"] = _gap_norm(df["sq_se"])

    # Sprint race gap per lap: 0 = winner, higher = slower (DNF ~2.33 s/lap)
    df["sr_gap"]  = df["driver_code"].map(
        lambda d: sprint_race_gap_per_lap.get(d, 35.0 / SPRINT_RACING_LAPS)
    )
    df["sr_norm"] = _gap_norm(df["sr_gap"])

    df["quali_score"] = (
        0.70 * df["sq_norm"] +
        0.15 * df["team_norm"] +
        0.15 * df["fp1_norm"]
    )
    df["race_score"] = (
        0.55 * df["sr_norm"] +
        0.20 * df["sq_norm"] +
        0.10 * df["team_norm"] +
        0.10 * df["fp1_norm"] +
        0.05 * aus_norm
    )
    print(f"\nLock mode: pre_race_quali_lock")
    print(f"  Quali model: Sprint Qualifying 70% | FP1 15% | Team 15%")
    print(f"  Race model:  Sprint Race pace 55% | Sprint Quali 20% | FP1 10% | Team 10% | AUS form 5%")
    print(f"  (Race qualifying, sprint and race outcomes NOT included.)")

else:  # pre_sprint_quali_lock
    # Only FP1 available. Use it with AUS form and team strength.
    # Both quali and race predictions use the same signal.
    df["quali_score"] = (
        0.50 * df["fp1_norm"] +
        0.30 * aus_norm +
        0.20 * df["team_norm"]
    )
    df["race_score"] = (
        0.40 * df["fp1_norm"] +
        0.30 * aus_norm +
        0.30 * df["team_norm"]
    )
    print(f"\nLock mode: pre_sprint_quali_lock")
    print(f"  Quali model: FP1 50% | AUS form 30% | Team 20%")
    print(f"  Race model:  FP1 40% | AUS form 30% | Team 30%")
    print(f"  (Sprint qualifying, sprint race, and race qualifying NOT included.)")

# Rank by each score to get predicted positions
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

# ── Build constructor DataFrame ──────────────────────────────────────
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

# ── Optimise lineup ──────────────────────────────────────────────────
result = optimize_lineup(df, cons_df)

assert result["total_price"] <= BUDGET, "Budget constraint violated!"
assert len(result["drivers"]) == 5
assert len(result["constructors"]) == 2
team_counts = {}
for d in result["drivers"]:
    t = driver_to_team[d]
    team_counts[t] = team_counts.get(t, 0) + 1
assert max(team_counts.values()) <= 2, "Max 2 drivers per team violated!"

# ── Print output ─────────────────────────────────────────────────────
print_lineup(result, df, cons_df, RACE_NAME, LOCK_MODE)

print(f"\n  All FP1 times compound-normalised to soft-equivalent.")
print(f"  Note: Update driver_prices with F1 Fantasy prices after AUS.")
print(f"  Set REFRESH_FASTF1 = True to pull live data from FastF1.")
