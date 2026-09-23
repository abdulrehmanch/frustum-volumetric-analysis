---
name: contour-frustum-volume
description: >-
  Calculate multi-layer volumetric capacity and earthwork quantities from 2D/3D contour shapefiles
  using the Prismoidal Frustum Method. Automatically detects CRS, elevation attributes, boundary
  topologies, and vertical spacing. Generates shapefiles, volumetric schedules, and stage-storage curves.
---

# Contour Frustum Volumetric Analysis Skill

This skill guides the automated calculation of volumetric capacity and earthwork quantities from contour survey shapefiles using `calculate_frustum_volume.py`.

## Core Mathematical Formulation

### 1. Prismoidal Frustum Formula (Primary Engine)
Between two successive contour stages $Z_{\text{low}}$ and $Z_{\text{high}}$ separated by vertical interval $\Delta h = Z_{\text{high}} - Z_{\text{low}}$:

$$V_{\text{slice}} = \frac{\Delta h}{3} \left(A_{\text{low}} + A_{\text{high}} + \sqrt{A_{\text{low}} \cdot A_{\text{high}}}\right)$$

- $A_{\text{low}}$: Planimetric area of the lower stage footprint ($m^2$).
- $A_{\text{high}}$: Planimetric area of the higher stage footprint ($m^2$).
- $\sqrt{A_{\text{low}} \cdot A_{\text{high}}}$: Geometric mean capturing non-linear wall taper.

Cumulative Volume above base datum:
$$V_{\text{cumul}}(Z_m) = \sum_{k=1}^{m-1} V_{\text{slice}, k}$$

### 2. Average End-Area Formula (Cross-Check)
$$V_{\text{endarea}} = \frac{\Delta h}{2} \left(A_{\text{low}} + A_{\text{high}}\right)$$

---

## Universal CLI Usage

Run the single, dataset-agnostic volumetric script:

```bash
uv run python calculate_frustum_volume.py --input <path/to/contours.shp> [options]
```

### CLI Options

| Flag | Full Name | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `-i` | `--input` | **Yes** | — | Path to the input contour shapefile (`.shp`). |
| `-b` | `--boundary` | No | Auto | Path to an external boundary polygon shapefile. |
| `-o` | `--output-dir` | No | Auto | Directory to write deliverables (defaults to `<input_parent>/output`). |
| `-p` | `--prefix` | No | Auto | Output filename prefix (defaults to input filename stem in lowercase). |
| `-e` | `--elev-col` | No | Auto | Elevation attribute column name (auto-detected if omitted). |
| `--target-epsg` | `--target-epsg` | No | Auto | Projected metric CRS (e.g. `EPSG:32643`). Dynamically estimated if omitted. |
| `--snap-tol` | `--snap-tol` | No | Auto | Geometry snap/extension tolerance in meters. |

---

## How It Works Under the Hood

The script uses a self-configuring, level-set geometric solver:
1. **Dynamic Metric Projection:** Inspects the input CRS. If geographic (lat/long in degrees), it automatically reprojects the dataset to the local UTM zone based on its centroid.
2. **Dynamic Boundary Detection:**
   - Detects explicit boundary features (`ELEVATION == 0.0` or minimum elevation polygon).
   - If no boundary feature exists, derives a convex/envelope boundary.
3. **Universal Level-Set Slicing:**
   - Evaluates contours in descending elevation order from crest down to base.
   - For closed contour rings (e.g. South basin), extracts the enclosed ring areas.
   - For open contours intersecting the boundary (e.g. Hassan Abdal mining blocks), extends line ends slightly across the boundary and splits the domain, retaining the piece containing the higher terrain.
   - Guarantees strictly monotonic stage containment: $A(Z_{\text{low}}) \ge A(Z_{\text{high}})$.
4. **Dynamic $\Delta h$ Handling:**
   - Dynamically calculates the height step $\Delta h_k$ between each stage, supporting $0.5\text{ m}$, $1.0\text{ m}$, or irregular contour spacing.

---

## Standard Engineering Deliverables

The script produces 5 standardized deliverables in the output folder:

1. `<prefix>_frustum_slice_polygons.shp`: Horizontal polygonal slice layers between successive contours with slice volume attributes.
2. `<prefix>_frustum_cumulative_polygons.shp`: Solid stage footprint polygons for each elevation stage.
3. `<prefix>_frustum_volumetric_report.csv`: Complete engineering schedule with elevations, depths, slice volumes, cumulative volumes ($m^3$, cu ft, acre-ft), and End-Area cross-check variances.
4. `<prefix>_stage_storage_curves.png`: High-resolution dual-axis plot of Stage vs. Footprint Area and Stage vs. Cumulative Volume.
5. `<prefix>_contour_slices_map.png`: 2D planimetric color-coded map of all discrete contour slice layers with colorbar.
