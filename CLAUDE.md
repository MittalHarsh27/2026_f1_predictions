# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment Setup

The project uses a local virtual environment in the `f1/` directory (gitignored). Always use `f1/bin/python` to run scripts — not the system Python.

```bash
# Install dependencies into the venv
f1/bin/pip install -r requirements.txt

# Optional: PuLP for LP-based lineup optimisation (used by fantasy scripts)
f1/bin/pip install pulp
```

For weather data in `prediction2.py`, copy `.env.example` to `.env` and set `OPENWEATHERMAP_API_KEY`. The script falls back to defaults if no key is set.

## Running Scripts

```bash
# Race prediction models
f1/bin/python prediction1.py          # Australian GP — XGBoost on qualifying times
f1/bin/python prediction2.py          # Chinese GP — blends AUS results + CHN sprint gaps
f1/bin/python racepace.py             # Single-lap pace analysis (no ML)

# Fantasy lineup optimiser
f1/bin/python fantasy_prediction/fantasy_race1.py   # AUS
f1/bin/python fantasy_prediction/fantasy_race2.py   # CHN
f1/bin/python fantasy_prediction/fantasy_race3.py   # JPN (uses FastF1 live data)
```

## Architecture

### Race Prediction Scripts (`prediction1.py`, `prediction2.py`, `racepace.py`)

Each prediction script is self-contained — all input data (qualifying times, sector splits, grid positions, team scores, historical results) is hardcoded at the top of the file as dicts/DataFrames. There is no shared module between prediction scripts; each one re-declares the `driver_to_team` map and team performance scores independently.

`prediction1.py` uses an XGBoost regressor with monotone constraints (faster qualifying time → better race result). `prediction2.py` uses Leave-One-Out cross-validation across 7 features, blending Australian race finishing positions with Chinese sprint race gaps as the training target. `racepace.py` is pure pandas — it computes each driver's "ultimate lap" (best S1 + S2 + S3) and estimates race pace from a sprint pole reference with tyre delta adjustments.

### Fantasy Prediction System (`fantasy_prediction/`)

The fantasy system is entirely decoupled from the race prediction scripts. It uses practice pace and recent form only, not qualifying results.

- **`fantasy_common.py`** — shared library imported by all `fantasy_raceN.py` scripts. Contains tyre normalisation (`TYRE_DELTA_TO_SOFT` constants + `soft_equivalent()`), the F1 Fantasy scoring model (`score_driver()`, `score_constructor()`), and the brute-force lineup optimiser (`optimize_lineup()`). The optimiser iterates all valid driver 5-combinations and constructor 2-combinations under the $100M budget with a max 2 drivers per team constraint.
- **`fantasy_raceN.py`** — one file per race weekend. Each script hardcodes driver/constructor prices, team performance scores, practice session lap times (as `fp1_*, fp2_*, fp3_*` dicts of `(time_s, compound)` tuples), and prior race form. At the top of each file, set `LOCK_MODE`, `REFRESH_FASTF1`, `NEW_TEAM_ONLY`, `MAX_FREE_TRANSFERS`, `CURRENT_DRIVERS`, and `CURRENT_CONSTRUCTORS` before running.

### FastF1 Integration

`fantasy_race3.py` (and future scripts) can fetch live FP session data via FastF1. Set `REFRESH_FASTF1 = True` to pull from the API; results are cached to `fantasy_prediction/data_snapshots/<race>_fp.json`. Subsequent runs with `REFRESH_FASTF1 = False` load from the snapshot. The FastF1 HTTP cache lives in `f1_cache/` (gitignored).

### Data Flow for a New Race Weekend

1. Create a new `fantasy_raceN.py` by copying the previous one.
2. Update prices from [fantasy.formula1.com](https://fantasy.formula1.com).
3. Update team performance scores with latest constructor championship points.
4. Set `REFRESH_FASTF1 = True` and run to fetch FP data; snapshot is saved automatically.
5. Update `CURRENT_DRIVERS`, `CURRENT_CONSTRUCTORS`, and `MAX_FREE_TRANSFERS`.
6. Set `LOCK_MODE` (`pre_quali_lock` or `pre_sprint_lock`) and run to get the lineup.

For race prediction scripts, duplicate the closest prior race script, replace the qualifying/sector data at the top, and adjust the feature set and target variable as needed.
