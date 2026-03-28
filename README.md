# Mar's 2026 F1 Race Predictions

> If this helped you, star the repo — it helps more people find it
> Will be updating throughout the season too ;) 

## Scripts

### prediction1.py — Australian GP
Predicts race finish times and podium for the 2026 Australian Grand Prix.
- XGBoost regressor trained on qualifying times, grid positions, team scores, regulation change boosts, and weather
- Qualifying-to-race pace conversion with monotone constraints for logical feature relationships

### prediction2.py — Chinese GP
Predicts full finishing order for the 2026 Chinese Grand Prix.
- Blends Australia race results with China sprint race gaps as the target variable
- XGBoost with Leave-One-Out cross-validation across 7 features (sector times, grid positions, team score, weather)
- Live weather forecast from the OpenWeatherMap API with sensible fallback defaults

### racepace.py — Single Lap Pace Analysis
Pure pace comparison for the Chinese GP — no ML, just sector time analysis.
- Computes each driver's "ultimate lap" (best S1 + S2 + S3) and gap to the fastest car
- Estimates race pace from sprint pole reference with tire compound deltas

## Fantasy Prediction

Optimises an F1 Fantasy lineup (5 drivers + 2 constructors, $100M budget) before qualifying locks. The fantasy system is **independent** of the race prediction scripts — it uses practice pace and recent form only, since you must lock your team before qualifying.

### Scripts

| Script | Lock point | Primary signals |
|---|---|---|
| `fantasy_prediction/fantasy_race1.py` | pre_race_quali_lock | FP3 pace + team strength (round 1 cold start) |
| `fantasy_prediction/fantasy_race2.py` | pre_race_quali_lock | Sprint Qualifying + Sprint Race pace + FP1 + AUS form |
| `fantasy_prediction/fantasy_race3.py` | pre_race_quali_lock | FP1 (real) + FP2/FP3 (update via FastF1) + CHN+AUS form |

### Lock modes

- **`pre_quali_lock`** — lock before qualifying. Uses FP3 best laps + team strength. Available for all races.
- **`pre_sprint_lock`** — lock after qualifying but before the sprint. Uses actual qualifying grid + AUS form. Only relevant for sprint weekends (e.g. China).

Change the `LOCK_MODE` constant at the top of each script before running.

### Usage

```bash
python fantasy_prediction/fantasy_race1.py   # Australian GP lineup
python fantasy_prediction/fantasy_race2.py   # Chinese GP lineup (pre_race_quali_lock)
python fantasy_prediction/fantasy_race3.py   # Japanese GP lineup (FP2/FP3 via FastF1)
```

### Refreshing FastF1 snapshots

Set `REFRESH_FASTF1 = True` in the script to pull live FP3 data from FastF1 and write it to `fantasy_prediction/data_snapshots/`. Subsequent runs will load from the snapshot automatically (no FastF1 re-fetch).

### Updating prices

Driver and constructor prices are pre-season estimates. Replace the `driver_prices` and `constructor_prices` dicts at the top of each script with the official F1 Fantasy prices from [fantasy.formula1.com](https://fantasy.formula1.com) before locking your team.

## Setup

```bash
pip install pandas numpy scikit-learn xgboost requests
```

For weather data in `prediction2.py`, create a `.env` file:

```bash
cp .env.example .env
# add your OpenWeatherMap API key to .env
```

Or export directly:

```bash
export OPENWEATHERMAP_API_KEY=your_key_here
```

The script works without a key — it falls back to default weather values.

## Usage

```bash
python prediction1.py    # Australian GP prediction
python prediction2.py    # Chinese GP prediction
python racepace.py       # Single lap pace analysis
```
