#!/usr/bin/env python3
"""
Generate validation sensor grid for Radiance daylighting simulation
Based on physical luxmeter measurement grid specifications:
- 9 points in direction between windows (north-south)
- 7 points from front to back (east-west)
- 1.08m uniform spacing
- 0.71m from east wall (front)
- 0.68m to west wall
- 0.51m to north and south walls
- Sensor height: 0.75m
"""

# Main room dimensions (from PISO-CONCRETO-PULIDOIER floor polygon)
# Floor corners: (0.459, -9.653) to (8.319, -0.083)
room_min_x = 0.458644626504064   # East wall
room_max_x = 8.31864462650407    # West wall
room_min_y = -9.65327504952668   # South wall (windows)
room_max_y = -0.0832750495266698 # North wall (windows)

# Validation grid specifications from luxmeter measurements
nx = 7   # Points in X direction (east to west, front to back)
ny = 9   # Points in Y direction (between windows, north-south)
spacing = 1.08  # Uniform spacing in both directions [m]

# Wall offsets
offset_east = 0.71   # Distance from east wall (front) to first row
offset_west = 0.68   # Distance from west wall to last row
offset_north = 0.51  # Distance from north wall to nearest row
offset_south = 0.51  # Distance from south wall to nearest row

# Calculate start positions
start_x = room_min_x + offset_east  # First column (near east wall)
start_y = room_min_y + offset_south # First row (near south wall)

# Work plane height
work_plane_z = 0.750

# Print grid information
print("Validation Sensor Grid (Luxmeter Measurement Points)")
print("=" * 55)
print(f"\nRoom dimensions:")
print(f"  Width (X, E-W): {room_max_x - room_min_x:.3f} m")
print(f"  Depth (Y, N-S): {room_max_y - room_min_y:.3f} m")

print(f"\nGrid specifications:")
print(f"  Points in X (front-back): {nx}")
print(f"  Points in Y (between windows): {ny}")
print(f"  Total sensors: {nx * ny}")
print(f"  Spacing: {spacing:.2f} m (uniform)")

print(f"\nWall offsets:")
print(f"  From east wall (front): {offset_east:.2f} m")
print(f"  To west wall: {offset_west:.2f} m")
print(f"  From north wall: {offset_north:.2f} m")
print(f"  From south wall: {offset_south:.2f} m")

# Calculate actual positions
end_x = start_x + (nx - 1) * spacing
end_y = start_y + (ny - 1) * spacing

print(f"\nGrid coordinates:")
print(f"  X range: {start_x:.3f} to {end_x:.3f} m")
print(f"  Y range: {start_y:.3f} to {end_y:.3f} m")

# Verify against room dimensions
actual_west_offset = room_max_x - end_x
actual_north_offset = room_max_y - end_y

print(f"\nVerification:")
print(f"  Calculated west offset: {actual_west_offset:.3f} m (specified: {offset_west:.2f} m)")
print(f"  Calculated north offset: {actual_north_offset:.3f} m (specified: {offset_north:.2f} m)")

# Generate grid points
# Order: iterate X first, then Y (same as original script)
grid_points = []

for ix in range(nx):
    x = start_x + ix * spacing
    for iy in range(ny):
        y = start_y + iy * spacing
        # Format: x y z dx dy dz (direction vector pointing up)
        grid_points.append(f"{x:.6f} {y:.6f} {work_plane_z:.4f} 0 0 1")

# Write to points_validation.txt
output_file = "points_validation.txt"
with open(output_file, 'w') as f:
    for point in grid_points:
        f.write(point + '\n')

print(f"\n✓ Generated {len(grid_points)} sensor points")
print(f"✓ Work plane height: {work_plane_z} m")
print(f"✓ Output file: {output_file}")

# Also output sensor positions as a summary table
print(f"\nSensor positions (row, col) -> (x, y):")
print("-" * 45)
for iy in range(ny):
    y = start_y + iy * spacing
    row_info = f"Row {iy+1} (Y={y:.2f}m): "
    positions = []
    for ix in range(nx):
        x = start_x + ix * spacing
        positions.append(f"({x:.2f}, {y:.2f})")
    # Just print first and last of each row
    print(f"  Row {iy+1}: X = {start_x:.2f} to {end_x:.2f} m, Y = {y:.2f} m")
