# Validation Folder - Radiance Daylighting Simulation

## Purpose

Self-contained folder for validating a Radiance annual daylighting simulation against experimental luxmeter measurements. Everything needed to reproduce the analysis is here — no dependencies on the parent project.

## Location

Temixco, Mexico (18.85N, 99.14W). Building exported from DesignBuilder.

## Measurement Dates

- **June 26, 2024**: Summer (high sun angle)
- **November 20, 2024**: Fall/winter (low sun angle)

## Folder Structure

```
validation/
├── CLAUDE.md                  # This file
├── validation_report.qmd      # Main Quarto report (renders to HTML)
├── pyproject.toml             # Python dependencies (use `uv run`)
│
├── data/
│   ├── experimental/
│   │   ├── 005_26Junio/       # Raw luxmeter CSVs (10 files, 9h-18h)
│   │   └── 006_20Nov/         # Raw luxmeter CSVs (9 files, 9h-17h)
│   ├── radiance/              # Processed comparison CSVs (63 points x 9 hours)
│   │   ├── 26jun_experimental.csv / 20nov_experimental.csv
│   │   ├── 26jun_radiance.csv / 20nov_radiance.csv
│   │   ├── 26jun_difference.csv / 20nov_difference.csv
│   │   └── comparison_26jun.csv / comparison_20nov.csv
│   └── parametric/
│       ├── grid_results_extended.csv      # 2704 combinations (tau x rho_floor x rho_hall)
│       └── optimal_parameters_extended.json
│
├── edificio/                  # Radiance scene (self-contained)
│   ├── materials.rad          # Original (tau=0.88, rho_floor=0.30, rho_hall=0.36)
│   ├── materials_calibrated.rad  # Combined optimum (tau=0.76, rho_floor=0.21, rho_hall=0.29)
│   ├── materials_jun_optimal.rad # June optimum (tau=0.80, rho_floor=0.17, rho_hall=0.13)
│   ├── materials_nov_optimal.rad # Nov optimum (tau=0.70, rho_floor=0.11, rho_hall=0.17)
│   ├── scene.rad / objects/ / skyDomes/ / skyVectors/
│   ├── points.txt             # 480-point grid (20x24, ~0.405m spacing)
│   ├── points_validation.txt  # 63-point grid (7x9, 1.08m spacing)
│   ├── nelier.wea / nelier_26jun_20novCST.epw  # Weather data
│   ├── octrees/               # Compiled octrees
│   ├── matrices/dc/           # Daylight coefficient matrices
│   └── results/dc/
│       ├── annual_validation.ill          # 8784h x 63pts (original materials)
│       ├── annual_jun_optimal.ill         # 8784h x 480pts (June optimal)
│       └── annual_nov_optimal.ill         # 8784h x 480pts (Nov optimal)
│
└── scripts/
    ├── generate_sensor_grid_validation.py
    ├── run_parametric_single.py           # Single parametric simulation
    ├── run_parametric_grid_extended.py    # Full 2704-combo grid search
    ├── run_simulation_validation_calibrated.sh
    ├── run_udi_simulations.sh            # Runs Jun/Nov optimal on 480-grid
    └── 004_comparison_tables.py          # Generates processed CSVs
```

## Key Parameters

### Parametric Search (Extended, 3 parameters)

2704 combinations: 16 tau x 13 rho_floor x 13 rho_hall

| Parameter | Symbol | Measured | Min | Max | Step |
|-----------|--------|----------|-----|-----|------|
| Glazing transmittance | tau | 0.88 | 0.58 | 0.88 | 0.02 |
| Classroom floor reflectance | rho_floor | 0.30 | 0.05 | 0.30 | 0.02 |
| Hallway floor reflectance | rho_hall | 0.36 | 0.11 | 0.36 | 0.02 |

### Optimal Parameters (per-day GOF minimization)

| Optimized for | tau | rho_floor | rho_hall | NMBE [%] | CV(RMSE) [%] | R2 | GOF [%] |
|---------------|-----|-----------|---------|----------|--------------|------|---------|
| June 26       | 0.80 | 0.17 | 0.13 | -2.1 | 40.3 | 0.848 | 40.3 |
| November 20   | 0.70 | 0.11 | 0.17 | +0.8 | 51.4 | 0.399 | 51.4 |
| Combined      | 0.76 | 0.21 | 0.29 | -3.4 | 47.0 | 0.606 | 47.1 |

None meet ASHRAE Guideline 14 (|NMBE| <= 10%, CV(RMSE) <= 30%).

### Error Metrics (ASHRAE Guideline 14)

- **NMBE**: Normalized Mean Bias Error. Positive = simulation underestimates. Threshold: |NMBE| <= 10%
- **CV(RMSE)**: Coefficient of Variation of RMSE. Threshold: CV(RMSE) <= 30%
- **R2**: Coefficient of Determination. Threshold: R2 > 0.85
- **GOF**: sqrt(NMBE^2 + CV(RMSE)^2). Optimization target (minimize).

## Quarto Report Sections

The report (`validation_report.qmd`) contains:

1. **Load Experimental Data** — raw CSVs to DataFrames (klux -> lux, odd-hour reversal)
2. **Load Radiance Data** — parse annual.ill, extract hours, reshape to 7x9 grid
3. **Error Metrics** — NMBE, CV(RMSE), R2, GOF definitions and original simulation results
4. **Parametric Calibration Results** — best per day, parameter ranges
5. **GOF Heatmaps and Sensitivity Analysis** — 2D heatmaps + 1D sensitivity curves
6. **Illuminance Contour Maps** — two versions:
   - 6.1/6.2: Paired experimental/radiance per hour (6x3 grid)
   - 6.3/6.4: Stacked 3x3 grids (experimental above, radiance below)
7. **Scatter Plots** — experimental vs simulated with 1:1 line
8. **Hourly Mean Comparison** — spatial mean per hour
9. **UDI (Useful Daylight Illuminance)** — 480-point grid, 8:00-18:00
   - Bins: UDI_under (<300 lux), UDI_useful (300-2000 lux), UDI_over (>2000 lux)
   - Two simulations: June optimal and November optimal
10. **Temporal Comfort Map** — hour x month heatmap of % area in 300-2000 lux
    - June optimal, November optimal, and difference map
11. **Summary** — comparison table and parameter ranges

## How to Render

```bash
cd validation
quarto render validation_report.qmd
```

## How to Re-run Simulations

### UDI simulations (480-point grid, Jun/Nov optimal)

```bash
cd validation
bash scripts/run_udi_simulations.sh
```

### Single parametric point

```bash
cd validation/edificio
uv run python ../scripts/run_parametric_single.py --tau 0.80 --rho-floor 0.17 --rho-hall 0.13
```

### Full parametric grid search (2704 combos, ~hours)

```bash
cd validation/edificio
uv run python ../scripts/run_parametric_grid_extended.py
```

## Experimental Data Format

- Raw files: 7 rows x 10 columns (I1N, I2N, I3N, I4N, I5N, I1S, I2S, I3S, I4S, I5S)
- Column I5N is excluded (faulty sensor: ~60 klux in June, zeros in November)
- Units: kilolux in raw files, converted to lux (* 1000) in processing
- Odd hours are reversed row-wise to match coordinate system

## Sensor Grids

### Validation grid (63 points)
- 7 lines x 9 sensors, 1.08m uniform spacing
- Work plane: 0.75m
- Offsets: 0.71m from east wall, 0.51m from north/south walls

### Full grid (480 points)
- 20 x 24, ~0.405m spacing
- X: 0.559 to 8.219m (east-west), Y: -9.553 to -0.183m (north-south)
- Work plane: 0.75m

## Known Issues / Notes

- Data is 8784 hours (leap year 2024), not 8760
- `invert_yaxis()` with `sharey=True` toggles per call — use only once after loop
- Contour maps use physical coordinates [m] with `invert_yaxis()` for correct orientation
- UDI maps use rotated axes (Y horizontal, X vertical) to match room orientation
- The `jet` colormap is used for illuminance contour maps (matching original code style)
