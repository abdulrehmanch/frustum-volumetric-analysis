---
name: fr-calculate-volume
description: >-
  Calculate multi-layer volumetric capacity and earthwork quantities from 2D/3D contour shapefiles
  using the Prismoidal Frustum Method. Automatically detects CRS, elevation attributes, boundary
  topologies, and vertical spacing. Generates shapefiles, volumetric schedules, and stage-storage curves.
---

# Contour Frustum Volumetric Analysis Skill

This skill guides the automated calculation of volumetric capacity and earthwork quantities from raw topographic contour survey shapefiles using `scripts/calculate_frustum_volume.py`.

---

## 1. Directory Conventions

All survey inputs and calculation outputs MUST follow the project directory layout:

- **Raw Inputs:** `inputs/<assignment_name>/<unit_name>/<shapefile>.shp`
  - Examples: `inputs/bund_calculations/north/`, `inputs/hassan_abdal/hassan_abdal_10c/`
- **Engine Deliverables:** `outputs/<assignment_name>/<unit_name>/`

> [!IMPORTANT]
> Never write raw survey shapefiles or calculation deliverables to the repository root.

---

## 2. Core Mathematical Formulation

### 1. Prismoidal Frustum Formula (Primary Engine)
Between two successive contour stages $Z_{\text{low}}$ and $Z_{\text{high}}$ separated by interval $\Delta h = Z_{\text{high}} - Z_{\text{low}}$:

$$V_{\text{slice}} = \frac{\Delta h}{3} \left(A_{\text{low}} + A_{\text{high}} + \sqrt{A_{\text{low}} \cdot A_{\text{high}}}\right)$$

- $A_{\text{low}}$: Planimetric area of the lower stage footprint ($m^2$).
- $A_{\text{high}}$: Planimetric area of the higher stage footprint ($m^2$).
- $\sqrt{A_{\text{low}} \cdot A_{\text{high}}}$: Geometric mean capturing non-linear side-slope taper.

Cumulative Volume above base datum:
$$V_{\text{cumul}}(Z_m) = \sum_{k=1}^{m-1} V_{\text{slice}, k}$$

### 2. Average End-Area Formula (Sanity Cross-Check)
$$V_{\text{endarea}} = \frac{\Delta h}{2} \left(A_{\text{low}} + A_{\text{high}}\right)$$

The method variance $\Delta\% = \frac{V_{\text{endarea}} - V_{\text{frustum}}}{V_{\text{frustum}}} \times 100$ is computed for quality assurance.

---

## 3. Execution Command

Run the calculation engine:
```bash
uv run python scripts/calculate_frustum_volume.py \
  --input inputs/<assignment_name>/<unit_name>/<shapefile>.shp
```

*The script auto-detects projection (UTM Zone 43N / metric), elevation columns (`ELEVATION`, `CONTOUR`, `Z`), vertical interval ($\Delta h = 0.5\text{m}$), and boundary topology.*

---

## 4. Standard Generated Deliverables

The engine outputs 5 standardized deliverables to `outputs/<assignment_name>/<unit_name>/`:
1. `<prefix>_frustum_slice_polygons.shp`: Hollow slice difference polygons for each 0.5m stage.
2. `<prefix>_frustum_cumulative_polygons.shp`: Solid stage footprint polygons from base to crest.
3. `<prefix>_frustum_volumetric_report.csv`: Complete engineering schedule with elevation, incremental volume, cumulative volume ($m^3$, $ft^3$, acre-ft), and variance.
4. `<prefix>_stage_storage_curves.png`: High-resolution dual-axis stage-storage and stage-area curves.
5. `<prefix>_contour_slices_map.png`: Planimetric survey map with color-coded elevation layers.
