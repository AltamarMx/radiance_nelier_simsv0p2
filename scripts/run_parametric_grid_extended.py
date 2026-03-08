#!/usr/bin/env python3
"""
run_parametric_grid_extended.py - Extended parametric grid search

Run grid search over glazing transmittance (tau), floor reflectance (rho_floor),
and hallway reflectance (rho_hall) to find optimal calibration parameters.

Uses ASHRAE-compliant metrics: NMBE, CV(RMSE), R², GOF.

Usage:
    python run_parametric_grid_extended.py
    python run_parametric_grid_extended.py --resume
    python run_parametric_grid_extended.py --tau-step 0.05  # Coarser grid for testing

Output:
    results/parametric/grid_results_extended.csv
    results/parametric/optimal_parameters_extended.json
"""

import argparse
import json
import subprocess
import tempfile
import os
import sys
import time
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime
from itertools import product


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


def run_simulation(materials_file: str, edificio_dir: Path) -> str:
    """Run Radiance simulation and return path to annual.ill file."""
    octree_file = edificio_dir / "octrees" / "scene_parametric.oct"
    dc_matrix_file = edificio_dir / "matrices" / "dc" / "illum_parametric.mtx"
    annual_file = edificio_dir / "results" / "parametric" / "annual_parametric.ill"

    # Ensure output directories exist
    octree_file.parent.mkdir(parents=True, exist_ok=True)
    dc_matrix_file.parent.mkdir(parents=True, exist_ok=True)
    annual_file.parent.mkdir(parents=True, exist_ok=True)

    # Step 1: Build octree
    oconv_cmd = [
        "oconv",
        str(materials_file),
        str(edificio_dir / "scene.rad"),
        str(edificio_dir / "objects" / "scene.geom"),
        str(edificio_dir / "objects" / "glazing.geom")
    ]
    with open(octree_file, 'w') as f:
        subprocess.run(oconv_cmd, stdout=f, stderr=subprocess.PIPE, check=True)

    # Step 2: Count sensors
    points_file = edificio_dir / "points_validation.txt"
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
        str(edificio_dir / "skyDomes" / "skyglow.rad"),
        "-i", str(octree_file)
    ]
    with open(points_file, 'r') as stdin_file:
        with open(dc_matrix_file, 'w') as stdout_file:
            subprocess.run(rfluxmtx_cmd, stdin=stdin_file, stdout=stdout_file,
                         stderr=subprocess.PIPE, check=True)

    # Step 4: Multiply DC × sky matrix
    sky_matrix = edificio_dir / "skyVectors" / "nelier_annual.smx"

    dctimestep_cmd = ["dctimestep", str(dc_matrix_file), str(sky_matrix)]
    dctimestep_proc = subprocess.Popen(dctimestep_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    rmtxop_cmd = ["rmtxop", "-fa", "-t", "-c", "47.4", "119.9", "11.6", "-"]
    with open(annual_file, 'w') as f:
        rmtxop_proc = subprocess.Popen(rmtxop_cmd, stdin=dctimestep_proc.stdout,
                                       stdout=f, stderr=subprocess.PIPE)
        dctimestep_proc.stdout.close()
        rmtxop_proc.communicate()

    return str(annual_file)


def parse_annual_ill_file(filepath: str) -> np.ndarray:
    """Parse the annual.ill file, skip header lines."""
    with open(filepath, 'r') as f:
        lines = f.readlines()

    skip_keywords = ['#', 'NCOMP', 'NROWS', 'NCOLS', 'FORMAT', 'SOFTWARE',
                     'CAPDATE', 'GMT', 'rmtxop', 'dctimestep', 'Applied',
                     'Transposed', 'LATLONG']

    data_start = 0
    for i, line in enumerate(lines):
        is_header = any(line.startswith(kw) for kw in skip_keywords)
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
    return max(0, int(delta.total_seconds() / 3600) - 1)


def load_experimental_data(base_path: Path, hours: list, reverse_odd_hours: bool = True) -> list:
    """Load experimental data from CSV files."""
    cols_map = ['I1N', 'I2N', 'I3N', 'I4N', 'I1S', 'I2S', 'I3S', 'I4S', 'I5S']
    dataframes = []

    for hour in hours:
        f = base_path / f"{hour:02d}h.csv"
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
        illum_matched = illum_2d[::-1, ::-1]
        df = pd.DataFrame(illum_matched, columns=cols_map)
        dataframes.append(df)

    return dataframes


def compute_metrics(exp_list: list, rad_list: list) -> dict:
    """Compute ASHRAE-compliant error metrics."""
    all_exp = np.concatenate([df.values.flatten() for df in exp_list])
    all_rad = np.concatenate([df.values.flatten() for df in rad_list])

    n = len(all_exp)
    mean_exp = all_exp.mean()

    # Errors: measured - simulated (ASHRAE convention)
    errors = all_exp - all_rad

    # NMBE (positive = underestimation)
    nmbe = (np.sum(errors) / (n * mean_exp)) * 100

    # RMSE and CV(RMSE)
    rmse = np.sqrt(np.mean(errors**2))
    cvrmse = (rmse / mean_exp) * 100

    # R²
    ss_res = np.sum(errors**2)
    ss_tot = np.sum((all_exp - mean_exp)**2)
    r2 = 1 - (ss_res / ss_tot)

    # GOF
    gof = np.sqrt(nmbe**2 + cvrmse**2)

    return {
        'nmbe': float(nmbe),
        'cvrmse': float(cvrmse),
        'r2': float(r2),
        'gof': float(gof),
        'rmse': float(rmse)
    }


def run_single_parametric(tau: float, rho_floor: float, rho_hall: float,
                          edificio_dir: Path, data_dir: Path) -> dict:
    """Run a single parametric simulation and return metrics."""
    hours = [9, 10, 11, 12, 13, 14, 15, 16, 17]

    # Create temporary materials file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.rad', delete=False) as f:
        materials_file = f.name

    try:
        # Generate materials file
        generate_materials_file(tau, rho_floor, rho_hall, materials_file)

        # Run simulation
        annual_file = run_simulation(materials_file, edificio_dir)

        # Load experimental data
        exp_jun26 = load_experimental_data(data_dir / "005_26Junio", hours)
        exp_nov20 = load_experimental_data(data_dir / "006_20Nov", hours)

        # Load radiance results
        rad_jun26 = load_radiance_data(annual_file, 6, 26, hours)
        rad_nov20 = load_radiance_data(annual_file, 11, 20, hours)

        # Compute metrics for each day
        metrics_jun = compute_metrics(exp_jun26, rad_jun26)
        metrics_nov = compute_metrics(exp_nov20, rad_nov20)

        # Combined metrics (equal weight)
        nmbe_combined = (metrics_jun['nmbe'] + metrics_nov['nmbe']) / 2
        cvrmse_combined = (metrics_jun['cvrmse'] + metrics_nov['cvrmse']) / 2
        r2_combined = (metrics_jun['r2'] + metrics_nov['r2']) / 2
        gof_combined = np.sqrt(nmbe_combined**2 + cvrmse_combined**2)

        # Check ASHRAE compliance
        meets_ashrae = abs(nmbe_combined) <= 10 and cvrmse_combined <= 30

        return {
            'tau': tau,
            'rho_floor': rho_floor,
            'rho_hall': rho_hall,
            'nmbe_jun': metrics_jun['nmbe'],
            'nmbe_nov': metrics_nov['nmbe'],
            'nmbe_combined': nmbe_combined,
            'cvrmse_jun': metrics_jun['cvrmse'],
            'cvrmse_nov': metrics_nov['cvrmse'],
            'cvrmse_combined': cvrmse_combined,
            'r2_jun': metrics_jun['r2'],
            'r2_nov': metrics_nov['r2'],
            'r2_combined': r2_combined,
            'gof': gof_combined,
            'meets_ashrae': meets_ashrae,
            'success': True
        }

    except Exception as e:
        return {
            'tau': tau,
            'rho_floor': rho_floor,
            'rho_hall': rho_hall,
            'error': str(e),
            'success': False
        }

    finally:
        if os.path.exists(materials_file):
            os.remove(materials_file)


def main():
    parser = argparse.ArgumentParser(
        description='Extended parametric grid search with hallway reflectance',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python run_parametric_grid_extended.py
    python run_parametric_grid_extended.py --resume
    python run_parametric_grid_extended.py --tau-step 0.05  # Coarser for testing
        """
    )
    parser.add_argument('--tau-min', type=float, default=0.58,
                       help='Minimum transmittance (default: 0.58)')
    parser.add_argument('--tau-max', type=float, default=0.88,
                       help='Maximum transmittance (default: 0.88)')
    parser.add_argument('--tau-step', type=float, default=0.02,
                       help='Transmittance step (default: 0.02)')
    parser.add_argument('--rho-floor-min', type=float, default=0.05,
                       help='Minimum floor reflectance (default: 0.05)')
    parser.add_argument('--rho-floor-max', type=float, default=0.30,
                       help='Maximum floor reflectance (default: 0.30)')
    parser.add_argument('--rho-floor-step', type=float, default=0.02,
                       help='Floor reflectance step (default: 0.02)')
    parser.add_argument('--rho-hall-min', type=float, default=0.11,
                       help='Minimum hallway reflectance (default: 0.11)')
    parser.add_argument('--rho-hall-max', type=float, default=0.36,
                       help='Maximum hallway reflectance (default: 0.36)')
    parser.add_argument('--rho-hall-step', type=float, default=0.02,
                       help='Hallway reflectance step (default: 0.02)')
    parser.add_argument('--resume', action='store_true',
                       help='Resume from existing results file')

    args = parser.parse_args()

    # Paths
    script_dir = Path(__file__).parent
    edificio_dir = script_dir
    data_dir = script_dir.parent / "data" / "experimental"
    results_dir = edificio_dir / "results" / "parametric"
    results_dir.mkdir(parents=True, exist_ok=True)

    results_file = results_dir / "grid_results_extended.csv"
    optimal_file = results_dir / "optimal_parameters_extended.json"

    # Generate parameter grids
    tau_grid = np.arange(args.tau_min, args.tau_max + args.tau_step/2, args.tau_step)
    rho_floor_grid = np.arange(args.rho_floor_min, args.rho_floor_max + args.rho_floor_step/2, args.rho_floor_step)
    rho_hall_grid = np.arange(args.rho_hall_min, args.rho_hall_max + args.rho_hall_step/2, args.rho_hall_step)

    # Round to avoid floating point issues
    tau_grid = np.round(tau_grid, 2)
    rho_floor_grid = np.round(rho_floor_grid, 2)
    rho_hall_grid = np.round(rho_hall_grid, 2)

    print("=" * 70)
    print("EXTENDED PARAMETRIC GRID SEARCH")
    print("=" * 70)
    print(f"Transmittance (τ):      {args.tau_min:.2f} - {args.tau_max:.2f} (step {args.tau_step:.2f}) = {len(tau_grid)} values")
    print(f"Floor reflectance (ρf): {args.rho_floor_min:.2f} - {args.rho_floor_max:.2f} (step {args.rho_floor_step:.2f}) = {len(rho_floor_grid)} values")
    print(f"Hall reflectance (ρh):  {args.rho_hall_min:.2f} - {args.rho_hall_max:.2f} (step {args.rho_hall_step:.2f}) = {len(rho_hall_grid)} values")
    total = len(tau_grid) * len(rho_floor_grid) * len(rho_hall_grid)
    print(f"Total combinations: {total}")
    print("=" * 70)
    print()

    # Load existing results if resuming
    completed = set()
    results = []
    if args.resume and results_file.exists():
        existing_df = pd.read_csv(results_file)
        results = existing_df.to_dict('records')
        for r in results:
            completed.add((round(r['tau'], 2), round(r['rho_floor'], 2), round(r['rho_hall'], 2)))
        print(f"Resuming: {len(completed)} simulations already completed")
        print()

    # Generate all combinations
    all_combinations = list(product(tau_grid, rho_floor_grid, rho_hall_grid))

    # Run grid search
    start_time = time.time()
    idx = 0

    for tau, rho_floor, rho_hall in all_combinations:
        idx += 1

        # Skip if already completed
        if (round(tau, 2), round(rho_floor, 2), round(rho_hall, 2)) in completed:
            continue

        # Progress and ETA
        elapsed = time.time() - start_time
        remaining = len(all_combinations) - idx
        if idx > len(completed) + 1:
            sims_done = idx - len(completed) - 1
            if sims_done > 0:
                avg_time = elapsed / sims_done
                eta_seconds = remaining * avg_time
                eta_str = f"ETA: {eta_seconds/60:.1f} min"
            else:
                eta_str = ""
        else:
            eta_str = ""

        print(f"[{idx}/{total}] τ={tau:.2f}, ρf={rho_floor:.2f}, ρh={rho_hall:.2f} ... ", end="", flush=True)

        sim_start = time.time()
        result = run_single_parametric(tau, rho_floor, rho_hall, edificio_dir, data_dir)
        sim_time = time.time() - sim_start

        if result['success']:
            gof = result['gof']
            ashrae = "✓" if result['meets_ashrae'] else ""
            print(f"done ({sim_time:.1f}s) GOF={gof:.1f}% {ashrae} {eta_str}")
        else:
            print(f"FAILED: {result.get('error', 'Unknown')}")

        results.append(result)

        # Save intermediate results
        pd.DataFrame(results).to_csv(results_file, index=False)

    total_time = time.time() - start_time

    # Filter successful results
    results_df = pd.DataFrame(results)
    successful_df = results_df[results_df['success'] == True].copy()

    print()
    print("=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"Total simulations: {len(results_df)}")
    print(f"Successful: {len(successful_df)}")
    print(f"Failed: {len(results_df) - len(successful_df)}")
    print(f"Total time: {total_time/60:.1f} minutes ({total_time/3600:.2f} hours)")
    print()

    if len(successful_df) > 0:
        # Find optimal (minimum GOF)
        optimal_idx = successful_df['gof'].idxmin()
        optimal = successful_df.loc[optimal_idx]

        # Count ASHRAE compliant
        ashrae_compliant = successful_df[successful_df['meets_ashrae'] == True]

        print(f"ASHRAE compliant solutions: {len(ashrae_compliant)} / {len(successful_df)}")
        print()
        print("OPTIMAL PARAMETERS (minimum GOF):")
        print(f"  Transmittance (τ):      {optimal['tau']:.2f}")
        print(f"  Floor reflectance (ρf): {optimal['rho_floor']:.2f}")
        print(f"  Hall reflectance (ρh):  {optimal['rho_hall']:.2f}")
        print()
        print("Metrics at optimal:")
        print(f"  June 26:     NMBE = {optimal['nmbe_jun']:+.1f}%, CV(RMSE) = {optimal['cvrmse_jun']:.1f}%, R² = {optimal['r2_jun']:.3f}")
        print(f"  November 20: NMBE = {optimal['nmbe_nov']:+.1f}%, CV(RMSE) = {optimal['cvrmse_nov']:.1f}%, R² = {optimal['r2_nov']:.3f}")
        print(f"  Combined:    NMBE = {optimal['nmbe_combined']:+.1f}%, CV(RMSE) = {optimal['cvrmse_combined']:.1f}%, R² = {optimal['r2_combined']:.3f}")
        print(f"  GOF = {optimal['gof']:.1f}%")
        print(f"  Meets ASHRAE: {'Yes' if optimal['meets_ashrae'] else 'No'}")
        print("=" * 70)

        # Save optimal parameters
        optimal_params = {
            'tau': float(optimal['tau']),
            'rho_floor': float(optimal['rho_floor']),
            'rho_hall': float(optimal['rho_hall']),
            'nmbe_jun': float(optimal['nmbe_jun']),
            'nmbe_nov': float(optimal['nmbe_nov']),
            'nmbe_combined': float(optimal['nmbe_combined']),
            'cvrmse_jun': float(optimal['cvrmse_jun']),
            'cvrmse_nov': float(optimal['cvrmse_nov']),
            'cvrmse_combined': float(optimal['cvrmse_combined']),
            'r2_jun': float(optimal['r2_jun']),
            'r2_nov': float(optimal['r2_nov']),
            'r2_combined': float(optimal['r2_combined']),
            'gof': float(optimal['gof']),
            'meets_ashrae': bool(optimal['meets_ashrae'])
        }

        with open(optimal_file, 'w') as f:
            json.dump(optimal_params, f, indent=2)

        print(f"\nResults saved to: {results_file}")
        print(f"Optimal parameters saved to: {optimal_file}")

        # Show top 5
        print("\nTop 5 configurations by GOF:")
        top5 = successful_df.nsmallest(5, 'gof')[['tau', 'rho_floor', 'rho_hall', 'gof', 'nmbe_combined', 'cvrmse_combined', 'meets_ashrae']]
        print(top5.to_string(index=False))

    else:
        print("No successful simulations!")
        sys.exit(1)


if __name__ == '__main__':
    main()
