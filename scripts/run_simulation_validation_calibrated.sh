#!/bin/bash
#
# run_simulation_validation_calibrated.sh - Calibrated validation simulation
#
# This script runs the Two-Phase Method simulation with CALIBRATED materials
# for the 63-point validation sensor grid (matching luxmeter measurement positions).
#
# Calibration adjustments (from extended 3-parameter grid search):
#   - Glazing transmittance: 0.88 -> 0.76 (accounts for frame obstruction + dirt)
#   - Floor reflectance: 0.30 -> 0.21 (accounts for desk/furniture coverage)
#   - Hallway reflectance: 0.36 -> 0.29 (accounts for hallway furniture/equipment)
#
# Usage: bash run_simulation_validation_calibrated.sh
#

set -e  # Exit on error

# Change to script directory
cd "$(dirname "$0")"

echo "=============================================="
echo "Radiance Validation Simulation (CALIBRATED)"
echo "=============================================="
echo ""
echo "Calibration parameters (optimal from extended 3-parameter search):"
echo "  - Glazing transmittance: 0.76 (from 0.88)"
echo "  - Floor reflectance:     0.21 (from 0.30)"
echo "  - Hallway reflectance:   0.29 (from 0.36)"
echo ""

# ----------------------------------------------
# Step 1: Generate validation sensor grid
# ----------------------------------------------
echo "[Step 1/4] Generating validation sensor grid..."
uv run python generate_sensor_grid_validation.py

# Count sensors for rfluxmtx -y parameter
SENSOR_COUNT=$(wc -l < points_validation.txt | tr -d ' ')
echo "  Sensor count: $SENSOR_COUNT"
echo ""

# ----------------------------------------------
# Step 2: Build octree with CALIBRATED materials
# ----------------------------------------------
echo "[Step 2/4] Building octree with calibrated materials..."
oconv materials_calibrated.rad scene.rad objects/scene.geom objects/glazing.geom > octrees/scene_calibrated.oct
echo "  Created: octrees/scene_calibrated.oct"
echo ""

# ----------------------------------------------
# Step 3: Calculate daylight coefficients
# ----------------------------------------------
echo "[Step 3/4] Calculating daylight coefficients..."
echo "  This may take a few minutes..."
echo "  Parameters: -ab 5 -ad 10000 -lw 0.0001"

rfluxmtx -v -faf -ab 5 -ad 10000 -lw 0.0001 -n 8 \
    -I+ -y "$SENSOR_COUNT" \
    - skyDomes/skyglow.rad \
    -i octrees/scene_calibrated.oct \
    < points_validation.txt \
    > matrices/dc/illum_validation_calibrated.mtx

echo "  Created: matrices/dc/illum_validation_calibrated.mtx"
echo ""

# ----------------------------------------------
# Step 4: Multiply DC × sky matrix
# ----------------------------------------------
echo "[Step 4/4] Generating annual illuminance..."
dctimestep matrices/dc/illum_validation_calibrated.mtx skyVectors/nelier_annual.smx \
    | rmtxop -fa -t -c 47.4 119.9 11.6 - \
    > results/dc/annual_validation_calibrated.ill

echo "  Created: results/dc/annual_validation_calibrated.ill"
echo ""

echo "=============================================="
echo "Calibrated validation simulation complete!"
echo "=============================================="
echo ""
echo "Results:"
echo "  - Octree:            octrees/scene_calibrated.oct"
echo "  - DC matrix:         matrices/dc/illum_validation_calibrated.mtx"
echo "  - Annual illuminance: results/dc/annual_validation_calibrated.ill"
echo ""
echo "Compare with uncalibrated: results/dc/annual_validation.ill"
echo ""
