# %%
import pandas as pd
import numpy as np
from datetime import datetime

# %%
# =============================================================================
# Helper Functions
# =============================================================================
def parse_annual_ill_file(filepath):
    """Parse the annual.ill file, skip header lines"""
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

def datetime_to_hour_of_year(month, day, hour, year=2024):
    """Convert date/time to hour of year index (0-8759)"""
    start_of_year = datetime(year, 1, 1, 0, 0, 0)
    target_dt = datetime(year, month, day, hour, 0, 0)
    delta = target_dt - start_of_year
    hour_of_year = int(delta.total_seconds() / 3600)
    return max(0, hour_of_year - 1)

def load_experimental_data(base_path, hours, reverse_odd_hours=True):
    """Load experimental data from CSV files"""
    cols_map = ['I1N', 'I2N', 'I3N', 'I4N', 'I1S', 'I2S', 'I3S', 'I4S', 'I5S']
    dataframes = []

    for hour in hours:
        f = f"{base_path}/{hour:02d}h.csv"
        df = pd.read_csv(f)
        # Reverse odd hours to match coordinate system
        if reverse_odd_hours and hour % 2 == 1:
            df = df[::-1].reset_index(drop=True)
        dataframes.append(df[cols_map] * 1000)  # Convert klux to lux

    return dataframes

def load_radiance_data(ill_file, month, day, hours):
    """Load radiance data for specific date and hours"""
    radiance_data = parse_annual_ill_file(ill_file)
    NX, NY = 7, 9
    cols_map = ['I1N', 'I2N', 'I3N', 'I4N', 'I1S', 'I2S', 'I3S', 'I4S', 'I5S']

    dataframes = []
    for hour in hours:
        hour_idx = datetime_to_hour_of_year(month, day, hour)
        illum_1d = radiance_data[hour_idx, :]
        illum_2d = illum_1d.reshape(NX, NY)
        # Reverse Y direction to match N to S
        illum_matched = illum_2d[:, ::-1]
        df = pd.DataFrame(illum_matched, columns=cols_map)
        dataframes.append(df)

    return dataframes

# %%
# =============================================================================
# Load Data
# =============================================================================
hours = [9, 10, 11, 12, 13, 14, 15, 16, 17]
ill_file = "../edificio/results/dc/annual_validation.ill"

# June 26
print("Loading June 26 data...")
exp_jun26 = load_experimental_data("../data/experimental/005_26Junio", hours)
rad_jun26 = load_radiance_data(ill_file, 6, 26, hours)

# November 20
print("Loading November 20 data...")
exp_nov20 = load_experimental_data("../data/experimental/006_20Nov", hours)
rad_nov20 = load_radiance_data(ill_file, 11, 20, hours)

# %%
# =============================================================================
# Create Comparison Tables
# =============================================================================
def create_comparison_table(exp_dataframes, rad_dataframes, hours, date_label):
    """Create a comparison table with Experimental, Numerical, Difference"""
    cols_map = ['I1N', 'I2N', 'I3N', 'I4N', 'I1S', 'I2S', 'I3S', 'I4S', 'I5S']
    rows = []

    for hour_idx, hour in enumerate(hours):
        exp_df = exp_dataframes[hour_idx]
        rad_df = rad_dataframes[hour_idx]

        # Iterate through grid (7 rows x 9 cols = 63 points)
        for row in range(7):
            for col in range(9):
                point_id = row * 9 + col + 1  # 1-63
                sensor_name = cols_map[col]
                line_num = row + 1  # 1-7

                exp_val = exp_df.iloc[row, col]
                rad_val = rad_df.iloc[row, col]
                diff = rad_val - exp_val

                rows.append({
                    'Hour': f"{hour}:00",
                    'Line': line_num,
                    'Sensor': sensor_name,
                    'Point': point_id,
                    'Experimental_lux': round(exp_val, 1),
                    'Radiance_lux': round(rad_val, 1),
                    'Difference_lux': round(diff, 1),
                    'Error_%': round(100 * diff / exp_val, 1) if exp_val > 0 else np.nan
                })

    df = pd.DataFrame(rows)
    return df

# Create tables
print("\nCreating comparison tables...")
table_jun26 = create_comparison_table(exp_jun26, rad_jun26, hours, "June 26")
table_nov20 = create_comparison_table(exp_nov20, rad_nov20, hours, "November 20")

# %%
# =============================================================================
# Save Tables
# =============================================================================
output_dir = "../edificio/results"
table_jun26.to_csv(f"{output_dir}/comparison_26jun.csv", index=False)
table_nov20.to_csv(f"{output_dir}/comparison_20nov.csv", index=False)
print(f"\nSaved: {output_dir}/comparison_26jun.csv")
print(f"Saved: {output_dir}/comparison_20nov.csv")

# %%
# =============================================================================
# Summary Statistics
# =============================================================================
def print_summary(table, date_label):
    """Print summary statistics for a comparison table"""
    print(f"\n{'='*60}")
    print(f"Summary Statistics - {date_label}")
    print('='*60)

    diff = table['Difference_lux']
    exp = table['Experimental_lux']

    print(f"  Total points: {len(diff)}")
    print(f"  Mean Bias (MBE): {diff.mean():+.1f} lux")
    print(f"  Std Dev: {diff.std():.1f} lux")
    print(f"  RMSE: {np.sqrt((diff**2).mean()):.1f} lux")
    print(f"  Range: {diff.min():+.1f} to {diff.max():+.1f} lux")
    print(f"  Exp Mean: {exp.mean():.1f} lux")
    print(f"  MBE %: {100 * diff.mean() / exp.mean():+.1f}%")
    print(f"  CV(RMSE): {100 * np.sqrt((diff**2).mean()) / exp.mean():.1f}%")

    # Per-hour summary
    print(f"\n  Per-hour Mean Error:")
    for hour in hours:
        hour_data = table[table['Hour'] == f"{hour}:00"]
        mean_err = hour_data['Difference_lux'].mean()
        print(f"    {hour}:00 -> {mean_err:+.1f} lux")

print_summary(table_jun26, "June 26")
print_summary(table_nov20, "November 20")

# %%
# =============================================================================
# Create Point x Hour Tables (63 points x 9 hours)
# =============================================================================
def create_point_hour_tables(exp_dataframes, rad_dataframes, hours, date_label):
    """Create tables with points as rows and hours as columns"""
    hour_labels = [f"{h}:00" for h in hours]

    # Initialize arrays (63 points x 9 hours)
    exp_array = np.zeros((63, 9))
    rad_array = np.zeros((63, 9))

    for hour_idx, hour in enumerate(hours):
        exp_df = exp_dataframes[hour_idx]
        rad_df = rad_dataframes[hour_idx]

        # Flatten grid to 63 points
        for row in range(7):
            for col in range(9):
                point_id = row * 9 + col  # 0-62
                exp_array[point_id, hour_idx] = exp_df.iloc[row, col]
                rad_array[point_id, hour_idx] = rad_df.iloc[row, col]

    # Create DataFrames with point numbers as index
    exp_table = pd.DataFrame(exp_array, columns=hour_labels)
    exp_table.insert(0, 'Point', range(1, 64))

    rad_table = pd.DataFrame(rad_array, columns=hour_labels)
    rad_table.insert(0, 'Point', range(1, 64))

    diff_table = pd.DataFrame(rad_array - exp_array, columns=hour_labels)
    diff_table.insert(0, 'Point', range(1, 64))

    return exp_table, rad_table, diff_table

# Create point x hour tables for both days
print("\nCreating point x hour tables...")

exp_jun26_table, rad_jun26_table, diff_jun26_table = create_point_hour_tables(
    exp_jun26, rad_jun26, hours, "June 26")

exp_nov20_table, rad_nov20_table, diff_nov20_table = create_point_hour_tables(
    exp_nov20, rad_nov20, hours, "November 20")

# Save tables
exp_jun26_table.round(1).to_csv(f"{output_dir}/26jun_experimental.csv", index=False)
rad_jun26_table.round(1).to_csv(f"{output_dir}/26jun_radiance.csv", index=False)
diff_jun26_table.round(1).to_csv(f"{output_dir}/26jun_difference.csv", index=False)

exp_nov20_table.round(1).to_csv(f"{output_dir}/20nov_experimental.csv", index=False)
rad_nov20_table.round(1).to_csv(f"{output_dir}/20nov_radiance.csv", index=False)
diff_nov20_table.round(1).to_csv(f"{output_dir}/20nov_difference.csv", index=False)

print(f"\nSaved point x hour tables:")
print(f"  {output_dir}/26jun_experimental.csv")
print(f"  {output_dir}/26jun_radiance.csv")
print(f"  {output_dir}/26jun_difference.csv")
print(f"  {output_dir}/20nov_experimental.csv")
print(f"  {output_dir}/20nov_radiance.csv")
print(f"  {output_dir}/20nov_difference.csv")

# %%
# =============================================================================
# Display Tables
# =============================================================================
print("\n" + "="*80)
print("JUNE 26 - EXPERIMENTAL (lux)")
print("="*80)
print(exp_jun26_table.round(0).to_string(index=False))

print("\n" + "="*80)
print("JUNE 26 - RADIANCE (lux)")
print("="*80)
print(rad_jun26_table.round(0).to_string(index=False))

print("\n" + "="*80)
print("JUNE 26 - DIFFERENCE (Radiance - Experimental) (lux)")
print("="*80)
print(diff_jun26_table.round(0).to_string(index=False))

print("\n" + "="*80)
print("NOVEMBER 20 - EXPERIMENTAL (lux)")
print("="*80)
print(exp_nov20_table.round(0).to_string(index=False))

print("\n" + "="*80)
print("NOVEMBER 20 - RADIANCE (lux)")
print("="*80)
print(rad_nov20_table.round(0).to_string(index=False))

print("\n" + "="*80)
print("NOVEMBER 20 - DIFFERENCE (Radiance - Experimental) (lux)")
print("="*80)
print(diff_nov20_table.round(0).to_string(index=False))

# %%
