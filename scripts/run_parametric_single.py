#!/usr/bin/env python3
"""
run_parametric_single.py - Run a single Radiance simulation with specified parameters

This script runs a single Two-Phase Method simulation for the 63-point validation grid
with user-specified glazing transmittance, floor reflectance, and hallway reflectance.

Usage:
    python run_parametric_single.py --tau 0.77 --rho-floor 0.12 --rho-hall 0.25
    python run_parametric_single.py -t 0.77 -f 0.12 -h 0.25 --output results.json

Returns error metrics as JSON to stdout (or to file if --output specified).
"""

import argparse
import json
import subprocess
import tempfile
import os
import sys
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime


def generate_materials_file(tau: float, rho_floor: float, rho_hall: float, output_path: str) -> None:
    """Generate a materials.rad file with specified parameters."""
    content = f"""# Radiance Materials - Parametric Calibration
# Glazing transmittance (tau): {tau}
# Floor reflectance (rho_floor): {rho_floor}
# Hallway reflectance (rho_hall): {rho_hall}

# FLOORS
void plastic PISO-CONCRETO-PULIDOIER
0
0
5 {rho_floor} {rho_floor} {rho_floor} 0.06 0.02

void plastic PISO-PASILLOIER
0
0
5 {rho_hall} {rho_hall} {rho_hall} 0 0

# WALLS & STRUCTURE
void plastic LadrilloIER
0
0
5 0.55 0.55 0.55 0.04 0.03

void plastic Material-de-bloque-de-componente-del-proyecto
0
0
5 0.4 0.4 0.4 0 0

# CEILING
void plastic CONCRETO-ARMADOIER
0
0
5 0.1 0.1 0.1 0 0

# METAL ELEMENTS
void metal AluminiumIER
0
0
5 0.68 0.68 0.68 0.9 0.15

# GLAZING
void glass Acristalamiento-exterior-del-proyecto
0
0
3 {tau} {tau} {tau}
"""
    with open(output_path, 'w') as f:
        f.write(content)


def run_simulation(materials_file: str, edificio_dir: str) -> str:
    """Run Radiance simulation and return path to annual.ill file."""
    octree_file = os.path.join(edificio_dir, "octrees", "scene_parametric.oct")
    dc_matrix_file = os.path.join(edificio_dir, "matrices", "dc", "illum_parametric.mtx")
    annual_file = os.path.join(edificio_dir, "results", "parametric", "annual_parametric.ill")

    # Ensure output directories exist
    os.makedirs(os.path.dirname(octree_file), exist_ok=True)
    os.makedirs(os.path.dirname(dc_matrix_file), exist_ok=True)
    os.makedirs(os.path.dirname(annual_file), exist_ok=True)

    # Step 1: Build octree
    oconv_cmd = [
        "oconv",
        materials_file,
        os.path.join(edificio_dir, "scene.rad"),
        os.path.join(edificio_dir, "objects", "scene.geom"),
        os.path.join(edificio_dir, "objects", "glazing.geom")
    ]
    with open(octree_file, 'w') as f:
        subprocess.run(oconv_cmd, stdout=f, stderr=subprocess.PIPE, check=True)

    # Step 2: Count sensors
    points_file = os.path.join(edificio_dir, "points_validation.txt")
    with open(points_file, 'r') as f:
        sensor_count = sum(1 for line in f if line.strip())

    # Step 3: Calculate daylight coefficients
    rfluxmtx_cmd = [
        "rfluxmtx",
        "-v",
        "-faf",
        "-ab", "5",
        "-ad", "10000",
        "-lw", "0.0001",
        "-n", "8",
        "-I+",
        "-y", str(sensor_count),
        "-",
        os.path.join(edificio_dir, "skyDomes", "skyglow.rad"),
        "-i", octree_file
    ]
    with open(points_file, 'r') as stdin_file:
        with open(dc_matrix_file, 'w') as stdout_file:
            subprocess.run(rfluxmtx_cmd, stdin=stdin_file, stdout=stdout_file,
                         stderr=subprocess.PIPE, check=True)

    # Step 4: Multiply DC × sky matrix
    sky_matrix = os.path.join(edificio_dir, "skyVectors", "nelier_annual.smx")

    dctimestep_cmd = ["dctimestep", dc_matrix_file, sky_matrix]
    dctimestep_proc = subprocess.Popen(dctimestep_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    rmtxop_cmd = ["rmtxop", "-fa", "-t", "-c", "47.4", "119.9", "11.6", "-"]
    with open(annual_file, 'w') as f:
        rmtxop_proc = subprocess.Popen(rmtxop_cmd, stdin=dctimestep_proc.stdout,
                                       stdout=f, stderr=subprocess.PIPE)
        dctimestep_proc.stdout.close()
        rmtxop_proc.communicate()

    return annual_file


def parse_annual_ill_file(filepath: str) -> np.ndarray:
    """Parse the annual.ill file, skip header lines."""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    skip_keywords = ['#', 'NCOMP', 'NROWS', 'NCOLS', 'FORMAT', 'SOFTWARE',
                     'CAPDATE', 'GMT', 'rmtxop', 'dctimestep', 'Applied',
                     'Transposed', 'LATLONG']

    data_start = 0
    for i, line in enumerate(lines):
        is_header = False
        for keyword in skip_keywords:
            if line.startswith(keyword):
                is_header = True
                break
        if not is_header and line.strip():
            data_start = i
            break

    data = []
    for line in lines[data_start:]:
        if line.strip():
            try:
                values = [float(x) for x in line.split()]
                if len(values) > 0:
                    data.append(values)
            except ValueError:
                continue

    return np.array(data)


def datetime_to_hour_of_year(month: int, day: int, hour: int, year: int = 2024) -> int:
    """Convert date/time to hour of year index (0-8759)."""
    start_of_year = datetime(year, 1, 1, 0, 0, 0)
    target_dt = datetime(year, month, day, hour, 0, 0)
    delta = target_dt - start_of_year
    hour_of_year = int(delta.total_seconds() / 3600)
    return max(0, hour_of_year - 1)


def load_experimental_data(base_path: str, hours: list, reverse_odd_hours: bool = True) -> list:
    """Load experimental data from CSV files."""
    cols_map = ['I1N', 'I2N', 'I3N', 'I4N', 'I1S', 'I2S', 'I3S', 'I4S', 'I5S']
    dataframes = []

    for hour in hours:
        f = os.path.join(base_path, f"{hour:02d}h.csv")
        df = pd.read_csv(f)
        if reverse_odd_hours and hour % 2 == 1:
            df = df[::-1].reset_index(drop=True)
        dataframes.append(df[cols_map] * 1000)  # Convert klux to lux

    return dataframes


def load_radiance_data(ill_file: str, month: int, day: int, hours: list) -> list:
    """Load radiance data for specific date and hours."""
    radiance_data = parse_annual_ill_file(ill_file)
    NX, NY = 7, 9
    cols_map = ['I1N', 'I2N', 'I3N', 'I4N', 'I1S', 'I2S', 'I3S', 'I4S', 'I5S']

    dataframes = []
    for hour in hours:
        hour_idx = datetime_to_hour_of_year(month, day, hour)
        illum_1d = radiance_data[hour_idx, :]
        illum_2d = illum_1d.reshape(NX, NY)
        # Flip rows (to match experimental row order) and columns (N to S)
        illum_matched = illum_2d[::-1, ::-1]
        df = pd.DataFrame(illum_matched, columns=cols_map)
        dataframes.append(df)

    return dataframes


def compute_metrics(exp_list: list, rad_list: list) -> dict:
    """Compute error metrics for experimental vs radiance data.

    Returns ASHRAE-compliant metrics:
    - NMBE: Normalized Mean Bias Error (positive = underestimation)
    - CV(RMSE): Coefficient of Variation of RMSE
    - R²: Coefficient of Determination
    - GOF: Goodness of Fit = sqrt(NMBE² + CV(RMSE)²)
    """
    all_exp = np.concatenate([df.values.flatten() for df in exp_list])
    all_rad = np.concatenate([df.values.flatten() for df in rad_list])

    n = len(all_exp)
    mean_exp = all_exp.mean()

    # Errors: measured - simulated (ASHRAE convention)
    errors = all_exp - all_rad

    # NMBE: Normalized Mean Bias Error (positive = underestimation)
    nmbe = (np.sum(errors) / (n * mean_exp)) * 100

    # RMSE and CV(RMSE)
    rmse = np.sqrt(np.mean(errors**2))
    cvrmse = (rmse / mean_exp) * 100

    # R² (Coefficient of Determination)
    ss_res = np.sum(errors**2)
    ss_tot = np.sum((all_exp - mean_exp)**2)
    r2 = 1 - (ss_res / ss_tot)

    # GOF (Goodness of Fit) - minimize this
    gof = np.sqrt(nmbe**2 + cvrmse**2)

    # MBE (for backwards compatibility): simulated - measured
    mbe = -np.sum(errors) / n
    mbe_pct = (mbe / mean_exp) * 100

    # Check ASHRAE compliance
    meets_ashrae = abs(nmbe) <= 10 and cvrmse <= 30

    return {
        'exp_mean': float(mean_exp),
        'sim_mean': float(all_rad.mean()),
        'nmbe': float(nmbe),
        'cvrmse': float(cvrmse),
        'r2': float(r2),
        'gof': float(gof),
        'rmse': float(rmse),
        'mbe_lux': float(mbe),
        'mbe_pct': float(mbe_pct),
        'meets_ashrae': meets_ashrae
    }


def main():
    parser = argparse.ArgumentParser(
        description='Run single parametric Radiance simulation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_parametric_single.py --tau 0.77 --rho-floor 0.12 --rho-hall 0.25
    python run_parametric_single.py -t 0.77 -f 0.12 -h 0.25 -o results.json
        """
    )
    parser.add_argument('-t', '--tau', type=float, required=True,
                       help='Glazing transmittance (0.0-1.0)')
    parser.add_argument('-f', '--rho-floor', type=float, required=True,
                       help='Floor reflectance (0.0-1.0)')
    parser.add_argument('-h', '--rho-hall', type=float, required=True,
                       help='Hallway reflectance (0.0-1.0)')
    parser.add_argument('-o', '--output', type=str, default=None,
                       help='Output JSON file (default: stdout)')
    parser.add_argument('--edificio-dir', type=str, default=None,
                       help='Path to edificio directory')
    parser.add_argument('--data-dir', type=str, default=None,
                       help='Path to data/experimental directory')

    args = parser.parse_args()

    # Determine paths
    script_dir = Path(__file__).parent
    edificio_dir = args.edificio_dir or str(script_dir)
    data_dir = args.data_dir or str(script_dir.parent / "data" / "experimental")

    hours = [9, 10, 11, 12, 13, 14, 15, 16, 17]

    # Create temporary materials file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.rad', delete=False) as f:
        materials_file = f.name

    try:
        # Generate materials file
        generate_materials_file(args.tau, args.rho_floor, args.rho_hall, materials_file)

        # Run simulation
        annual_file = run_simulation(materials_file, edificio_dir)

        # Load experimental data
        exp_jun26 = load_experimental_data(os.path.join(data_dir, "005_26Junio"), hours)
        exp_nov20 = load_experimental_data(os.path.join(data_dir, "006_20Nov"), hours)

        # Load radiance results
        rad_jun26 = load_radiance_data(annual_file, 6, 26, hours)
        rad_nov20 = load_radiance_data(annual_file, 11, 20, hours)

        # Compute metrics for each day
        metrics_jun26 = compute_metrics(exp_jun26, rad_jun26)
        metrics_nov20 = compute_metrics(exp_nov20, rad_nov20)

        # Combined metrics (equal weight for both days)
        nmbe_combined = (metrics_jun26['nmbe'] + metrics_nov20['nmbe']) / 2
        cvrmse_combined = (metrics_jun26['cvrmse'] + metrics_nov20['cvrmse']) / 2
        r2_combined = (metrics_jun26['r2'] + metrics_nov20['r2']) / 2
        rmse_combined = np.sqrt((metrics_jun26['rmse']**2 + metrics_nov20['rmse']**2) / 2)
        gof_combined = np.sqrt(nmbe_combined**2 + cvrmse_combined**2)
        meets_ashrae_combined = abs(nmbe_combined) <= 10 and cvrmse_combined <= 30

        # Legacy combined error (for backwards compatibility)
        combined_error = (
            0.25 * abs(metrics_jun26['mbe_pct']) +
            0.25 * abs(metrics_nov20['mbe_pct']) +
            0.25 * metrics_jun26['cvrmse'] +
            0.25 * metrics_nov20['cvrmse']
        )

        result = {
            'tau': args.tau,
            'rho_floor': args.rho_floor,
            'rho_hall': args.rho_hall,
            'june26': metrics_jun26,
            'november20': metrics_nov20,
            'combined': {
                'nmbe': float(nmbe_combined),
                'cvrmse': float(cvrmse_combined),
                'r2': float(r2_combined),
                'rmse': float(rmse_combined),
                'gof': float(gof_combined),
                'meets_ashrae': meets_ashrae_combined
            },
            'gof': float(gof_combined),
            'combined_error': float(combined_error),  # Legacy
            'success': True
        }

        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
        else:
            print(json.dumps(result, indent=2))

    except Exception as e:
        result = {
            'tau': args.tau,
            'rho_floor': args.rho_floor,
            'rho_hall': args.rho_hall,
            'error': str(e),
            'success': False
        }
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(result, f, indent=2)
        else:
            print(json.dumps(result, indent=2))
        sys.exit(1)

    finally:
        # Cleanup temporary files
        if os.path.exists(materials_file):
            os.remove(materials_file)


if __name__ == '__main__':
    main()
