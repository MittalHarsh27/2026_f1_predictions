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
REFRESH_FASTF1 = False   # set True to repull FP1/FP2/FP3 from FastF1

RACE_NAME  = "Australian GP"
RACE_ROUND = 1

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

# ── 2026 F1 Fantasy prices — update when official prices are released ─
driver_prices = {
    "NOR": 25_000_000, "RUS": 23_000_000, "VER": 22_000_000,
    "PIA": 20_000_000, "LEC": 20_000_000, "HAM": 19_000_000,
    "ANT": 18_000_000, "HAD": 14_000_000, "LAW": 14_000_000,
    "GAS": 13_000_000, "BEA": 12_000_000, "HUL": 11_000_000,
    "LIN": 11_000_000, "OCO": 11_000_000, "COL": 10_000_000,
    "ALO": 10_000_000, "SAI": 10_000_000, "ALB": 10_000_000,
    "BOR":  9_000_000, "BOT":  8_000_000, "STR":  7_500_000,
    "PER":  7_500_000,
}
constructor_prices = {
    "McLaren":      24_000_000, "Mercedes":     21_000_000,
    "Ferrari":      20_000_000, "Red Bull":     18_000_000,
    "Racing Bulls": 13_000_000, "Williams":     11_000_000,
    "Haas":         11_000_000, "Audi":         10_000_000,
    "Alpine":        9_000_000, "Aston Martin":  9_000_000,
    "Cadillac":      7_000_000,
}

# ── Team strength: 2025 constructor points × 2026 regulation boost ───
team_points_2025 = {
    "McLaren": 800, "Mercedes": 459, "Red Bull": 426, "Ferrari": 382,
    "Williams": 137, "Aston Martin": 80, "Haas": 73, "Racing Bulls": 92,
    "Audi": 68, "Alpine": 22, "Cadillac": 5,
}
max_pts = max(team_points_2025.values())
team_perf_score = {t: p / max_pts for t, p in team_points_2025.items()}
reg_change_boost = {
    "Mercedes": 1.15, "Ferrari": 1.05, "Red Bull": 0.95, "McLaren": 1.00,
    "Williams": 0.80, "Aston Martin": 0.70, "Haas": 0.85,
    "Racing Bulls": 0.88, "Audi": 0.83, "Alpine": 0.80, "Cadillac": 0.70,
}
adj_team_score = {t: team_perf_score[t] * reg_change_boost[t] for t in team_perf_score}

# ── Practice session data: (best_lap_time_s, compound) per driver ─────
#
# FP1 — early weekend setup runs, mixed compounds, ~1.5-2s off FP3 pace.
#        Compound info matters here: a HARD time looks slower but normalises up.
# FP2 — race simulation laps on MEDIUM/HARD. Best lap is representative of
#        race pace; normalise to soft-equivalent to compare fairly vs FP3.
# FP3 — qualifying simulation on SOFT. Closest to race qualifying pace.
#
# Update with actual FastF1 data by setting REFRESH_FASTF1 = True.
# These are placeholder estimates — ordering matters, exact times less so.

fp1_aus = {   # (time_s, compound)
    "NOR": (81.80, "SOFT"),   "PIA": (82.10, "MEDIUM"), "RUS": (81.95, "SOFT"),
    "ANT": (82.35, "MEDIUM"), "LEC": (82.15, "SOFT"),   "HAM": (82.28, "MEDIUM"),
    "VER": (82.50, "MEDIUM"), "HAD": (82.90, "SOFT"),   "LAW": (83.10, "MEDIUM"),
    "LIN": (83.50, "MEDIUM"), "BEA": (83.25, "SOFT"),   "OCO": (83.40, "MEDIUM"),
    "GAS": (83.30, "SOFT"),   "COL": (83.70, "MEDIUM"), "HUL": (83.55, "HARD"),
    "BOR": (83.80, "MEDIUM"), "SAI": (84.00, "MEDIUM"), "ALB": (84.20, "HARD"),
    "ALO": (84.65, "MEDIUM"), "STR": (85.10, "MEDIUM"), "PER": (85.40, "MEDIUM"),
    "BOT": (85.60, "HARD"),
}

fp2_aus = {   # (time_s, compound) — race sims, MEDIUM/HARD typical
    "NOR": (81.40, "MEDIUM"), "PIA": (81.65, "MEDIUM"), "RUS": (81.55, "MEDIUM"),
    "ANT": (82.00, "HARD"),   "LEC": (81.75, "MEDIUM"), "HAM": (81.90, "MEDIUM"),
    "VER": (82.10, "HARD"),   "HAD": (82.55, "MEDIUM"), "LAW": (82.75, "MEDIUM"),
    "LIN": (83.15, "HARD"),   "BEA": (82.90, "MEDIUM"), "OCO": (83.05, "MEDIUM"),
    "GAS": (82.95, "MEDIUM"), "COL": (83.35, "HARD"),   "HUL": (83.20, "MEDIUM"),
    "BOR": (83.45, "HARD"),   "SAI": (83.65, "MEDIUM"), "ALB": (83.80, "HARD"),
    "ALO": (84.30, "MEDIUM"), "STR": (84.75, "HARD"),   "PER": (85.00, "MEDIUM"),
    "BOT": (85.20, "HARD"),
}

fp3_aus = {   # (time_s, compound) — quali sim, mostly SOFT
    "NOR": (80.21, "SOFT"),   "PIA": (80.45, "SOFT"),   "RUS": (80.38, "SOFT"),
    "ANT": (80.82, "SOFT"),   "LEC": (80.56, "SOFT"),   "HAM": (80.71, "SOFT"),
    "VER": (80.93, "SOFT"),   "HAD": (81.35, "SOFT"),   "LAW": (81.55, "SOFT"),
    "LIN": (81.90, "SOFT"),   "BEA": (81.70, "SOFT"),   "OCO": (81.85, "SOFT"),
    "GAS": (81.75, "SOFT"),   "COL": (82.10, "SOFT"),   "HUL": (81.95, "SOFT"),
    "BOR": (82.20, "SOFT"),   "SAI": (82.45, "SOFT"),   "ALB": (82.60, "SOFT"),
    "ALO": (83.10, "SOFT"),   "STR": (83.50, "SOFT"),   "PER": (83.80, "SOFT"),
    "BOT": (84.00, "SOFT"),
}

# ── Optional FastF1 refresh ──────────────────────────────────────────
SNAPSHOT_PATH = os.path.join(
    os.path.dirname(__file__), "data_snapshots", "aus_2026_fp.json"
)

def _fastf1_best_lap_with_compound(session):
    """Return {driver_code: (time_s, compound)} for the fastest lap per driver."""
    laps = session.laps.pick_quicklaps()
    result = {}
    for drv, grp in laps.groupby("Driver"):
        idx  = grp["LapTime"].idxmin()
        row  = grp.loc[idx]
        result[drv] = (row["LapTime"].total_seconds(),
                       str(row.get("Compound", "UNKNOWN") or "UNKNOWN").upper())
    return result

if REFRESH_FASTF1:
    try:
        import fastf1
        fastf1.Cache.enable_cache("f1_cache")
        pulled = {}
        for session_name, target in [("FP1", fp1_aus), ("FP2", fp2_aus), ("FP3", fp3_aus)]:
            s = fastf1.get_session(2026, "Australia", session_name)
            s.load(telemetry=False, weather=False, messages=False)
            data = _fastf1_best_lap_with_compound(s)
            target.update(data)
            pulled[session_name] = {d: list(v) for d, v in data.items()}
            print(f"  FastF1 {session_name}: {len(data)} drivers loaded")
        with open(SNAPSHOT_PATH, "w") as f:
            json.dump(pulled, f, indent=2)
        print(f"Snapshot saved → {SNAPSHOT_PATH}")
    except Exception as e:
        print(f"FastF1 unavailable — using hardcoded FP times ({e})")
elif os.path.exists(SNAPSHOT_PATH):
    with open(SNAPSHOT_PATH) as f:
        snap = json.load(f)
    for session_name, target in [("FP1", fp1_aus), ("FP2", fp2_aus), ("FP3", fp3_aus)]:
        if session_name in snap:
            target.update({d: tuple(v) for d, v in snap[session_name].items()})
    print(f"Loaded FP snapshot from {SNAPSHOT_PATH}")
else:
    print("Using hardcoded FP fallback data (FP1 / FP2 / FP3).")

# ── Build driver DataFrame ───────────────────────────────────────────
drivers = list(driver_to_team.keys())
df = pd.DataFrame({
    "driver_code": drivers,
    "team":        [driver_to_team[d] for d in drivers],
    "price":       [driver_prices[d]  for d in drivers],
    "adj_team":    [adj_team_score[driver_to_team[d]] for d in drivers],
})

# Soft-equivalent best lap per session — removes compound bias
df["fp1_se"] = df["driver_code"].map(
    lambda d: soft_equivalent(*fp1_aus.get(d, (88.0, "UNKNOWN")))
)
df["fp2_se"] = df["driver_code"].map(
    lambda d: soft_equivalent(*fp2_aus.get(d, (88.0, "UNKNOWN")))
)
df["fp3_se"] = df["driver_code"].map(
    lambda d: soft_equivalent(*fp3_aus.get(d, (88.0, "UNKNOWN")))
)

def _gap_norm(series):
    """Normalise gap-from-best: 0 = fastest, 1 = slowest."""
    best = series.min()
    span = series.max() - best
    return (series - best) / (span if span > 0 else 1)

df["fp1_norm"] = _gap_norm(df["fp1_se"])
df["fp2_norm"] = _gap_norm(df["fp2_se"])
df["fp3_norm"] = _gap_norm(df["fp3_se"])

max_team = df["adj_team"].max()
df["team_norm"] = 1.0 - df["adj_team"] / max_team   # 0 = strongest team

# ── Feature model ─────────────────────────────────────────────────────
#
# Qualifying position prediction:
#   FP3 (fresh-tyre quali sim) carries the most weight.
#   FP1/FP2 add supporting signal; team strength fills residual.
#
# Race position prediction:
#   FP2 (race-sim laps on MEDIUM/HARD) is the primary signal.
#   FP3 still informative; team strength matters more over race distance.
#
# Lower score = better predicted performance.

df["quali_score"] = (
    0.55 * df["fp3_norm"] +
    0.20 * df["fp2_norm"] +
    0.10 * df["fp1_norm"] +
    0.15 * df["team_norm"]
)
df["race_score"] = (
    0.25 * df["fp3_norm"] +
    0.45 * df["fp2_norm"] +
    0.10 * df["fp1_norm"] +
    0.20 * df["team_norm"]
)

df_q = df.sort_values("quali_score").reset_index(drop=True)
df_r = df.sort_values("race_score").reset_index(drop=True)

# Merge predicted positions back onto the main frame keyed by driver_code
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

print(f"\n  Quali model:  FP3 55% | FP2 20% | FP1 10% | Team 15%")
print(f"  Race model:   FP2 45% | FP3 25% | FP1 10% | Team 20%")
print(f"  All FP times compound-normalised to soft-equivalent.")
print(f"  Note: prices and FP data are pre-season estimates.")
print(f"  Set REFRESH_FASTF1 = True to pull live data from FastF1.")
