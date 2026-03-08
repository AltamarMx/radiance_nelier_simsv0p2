#!/bin/bash
set -e
cd "$(dirname "$0")/../edificio"

SENSOR_COUNT=$(wc -l < points.txt | tr -d ' ')
echo "Sensor count: $SENSOR_COUNT"

run_simulation() {
    local LABEL=$1
    local MATERIALS=$2
    local OCTREE="octrees/scene_${LABEL}.oct"
    local DC_MATRIX="matrices/dc/illum_${LABEL}.mtx"
    local ANNUAL="results/dc/annual_${LABEL}.ill"

    echo ""
    echo "Running simulation: $LABEL ($MATERIALS)"

    mkdir -p octrees matrices/dc results/dc

    echo "  [1/3] Building octree..."
    oconv "$MATERIALS" scene.rad objects/scene.geom objects/glazing.geom > "$OCTREE"

    echo "  [2/3] Calculating daylight coefficients..."
    rfluxmtx -v -faf -ab 5 -ad 10000 -lw 0.0001 -n 8 \
        -I+ -y "$SENSOR_COUNT" \
        - skyDomes/skyglow.rad \
        -i "$OCTREE" \
        < points.txt \
        > "$DC_MATRIX"

    echo "  [3/3] Generating annual illuminance..."
    dctimestep "$DC_MATRIX" skyVectors/nelier_annual.smx \
        | rmtxop -fa -t -c 47.4 119.9 11.6 - \
        > "$ANNUAL"

    echo "  Done: $ANNUAL"
}

run_simulation "jun_optimal" "materials_jun_optimal.rad"
run_simulation "nov_optimal" "materials_nov_optimal.rad"

echo ""
echo "Both simulations complete!"
