---
name: contour-frustum-volume
description: >-
  Calculate multi-layer volumetric capacity and earthwork quantities from 2D/3D contour shapefiles
  using the Prismoidal Frustum Method. Automatically detects CRS, elevation attributes, boundary
  topologies, and vertical spacing. Generates shapefiles, volumetric schedules, and stage-storage curves.
---

# Contour Frustum Volumetric Analysis Skill

This skill enforces project directory conventions and guides the automated calculation of volumetric capacity and earthwork quantities from contour survey shapefiles using `scripts/calculate_frustum_volume.py`.

---

## 1. Project Directory Architecture & Conventions

All files in this repository MUST strictly follow the organized directory structure:

```
mmd_frustum_volumetric_analysis/
├── inputs/                      # Source survey inputs grouped by site / block
│   ├── south/                   # e.g. Contours.shp, Contours.dbf, etc.
│   ├── north/                   # e.g. Clip_Contour_North.shp, etc.
│   └── <site_or_block_name>/    # e.g. inputs/hassan_abdal_10b/Hassan_Abdal_10B.shp
├── outputs/                     # Generated deliverables grouped by site / block
│   ├── south/                   # Shapefiles, CSV schedules, PNG plots, 3D models
│   ├── north/
│   └── <site_or_block_name>/    # e.g. outputs/hassan_abdal_10b/
├── scripts/                     # Production engines and visualizers
│   ├── calculate_frustum_volume.py  # Step 1 – Universal calculation engine
│   ├── export_viewer_data.py        # Step 2 – GeoJSON exporter + viewer deployer
│   ├── viewer/
│   │   └── 3d_viewer.html           # Reusable static CesiumJS 3D viewer template
│   └── retired/                 # Archived legacy scripts
├── docs/                        # Project briefs and mathematical specifications
│   ├── METHODOLOGY_SIMPLE.md
│   ├── METHODOLOGY_TECHNICAL.md
│   └── PROJECT_OVERVIEW.md
└── reference_sketches/          # Concept drawings and survey diagrams
```

> [!IMPORTANT]
> **Strict Organization Rule:** Never write new shapefiles, CSVs, or plots to the repository root.
> - New input shapefiles must always be placed into `inputs/<site_name>/`.
> - Deliverables must always be written into `outputs/<site_name>/`.

---

## 2. Core Mathematical Formulation

### 1. Prismoidal Frustum Formula (Primary Engine)
Between two successive contour stages $Z_{\text{low}}$ and $Z_{\text{high}}$ separated by vertical interval $\Delta h = Z_{\text{high}} - Z_{\text{low}}$:

$$V_{\text{slice}} = \frac{\Delta h}{3} \left(A_{\text{low}} + A_{\text{high}} + \sqrt{A_{\text{low}} \cdot A_{\text{high}}}\right)$$

- $A_{\text{low}}$: Planimetric area of the lower stage footprint ($m^2$).
- $A_{\text{high}}$: Planimetric area of the higher stage footprint ($m^2$).
- $\sqrt{A_{\text{low}} \cdot A_{\text{high}}}$: Geometric mean capturing non-linear side-slope taper.

Cumulative Volume above base datum:
$$V_{\text{cumul}}(Z_m) = \sum_{k=1}^{m-1} V_{\text{slice}, k}$$

### 2. Average End-Area Formula (Independent Engineering Cross-Check)
$$V_{\text{endarea}} = \frac{\Delta h}{2} \left(A_{\text{low}} + A_{\text{high}}\right)$$

---

## 3. Standard Input Columns & Mapping Guide

The calculation engine requires standard column attributes to identify geometry, contour elevations, and boundary elements. If attributes differ across survey sources, use explicit CLI mapping flags or `--col-map`.

### Column Roles & Auto-Detection Hierarchy

| Role | Auto-Detected Candidate Names | Mapping CLI Flags | Generic `--col-map` Key |
| :--- | :--- | :--- | :--- |
| **Elevation** | `elevation`, `elev`, `contour`, `z`, `height`, `level` | `--elevation-col`, `--elev-col`, `-e` | `elevation=<col>` or `elev=<col>` |
| **Geometry** | Active geometry, `geometry`, `geom`, `shape`, `the_geom` | `--geometry-col`, `--geom-col`, `-g` | `geometry=<col>` or `geom=<col>` |
| **Embedded Boundary** | Features with `elevation == 0.0` or user-defined value | `--boundary-col`, `--bnd-col` <br> `--boundary-val`, `--bnd-val` | `boundary=<col>,boundary_val=<val>` |

### Error Diagnostics for Missing Columns
If a required column cannot be resolved or is invalid, the script halts immediately with an actionable error block:
- Highlights the missing/invalid column.
- Lists all columns physically present in the shapefile.
- Displays the exact CLI flags and syntax to map the column.

---

## 4. Universal CLI Reference

```bash
uv run python scripts/calculate_frustum_volume.py --input inputs/<site_name>/<shapefile>.shp [OPTIONS]
```

### Complete CLI Options Reference

| Flag | Full Name | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `-i` | `--input` | **Yes** | — | Path to the input contour shapefile (`.shp`). |
| `-o` | `--output-dir` | No | Auto | Output directory. Auto-defaults to `outputs/<site_name>/`. |
| `-p` | `--prefix` | No | Auto | Output filename prefix (defaults to shapefile stem in lowercase). |
| `-e` | `--elevation-col`, `--elev-col` | No | Auto | Elevation column name (`elevation`, `elev`, `contour`, `z`, `height`, `level`). |
| `-g` | `--geometry-col`, `--geom-col` | No | Auto | Geometry column name (`geometry`, `geom`, `shape`, `the_geom`). |
| — | `--boundary-col`, `--bnd-col` | No | Auto | Column identifying embedded boundary features. |
| — | `--boundary-val`, `--bnd-val` | No | `0.0` | Value identifying boundary feature in `--boundary-col`. |
| — | `--col-map`, `--column-map` | No | Auto | Generic mapping string (e.g. `'elevation=Z,geom=the_geom,boundary=TYPE'`). |
| `-b` | `--boundary` | No | Auto | Path to an external boundary polygon shapefile (if separate). |
| `-m` | `--method` | No | `auto` | Solver choice: `auto`, `ring` (closed loops), `split` (boundary-cut block), or `band` (open bund corridor). |
| `--close-dist`| `--close-dist` | No | `25.0` | Morphological closing distance (m) for `band` solver. |
| `--target-epsg`| `--target-epsg` | No | Auto | Target metric CRS (e.g. `EPSG:32643`). Estimated dynamically if omitted. |
| `--snap-tol` | `--snap-tol` | No | `1.0` | Geometry snap/extension tolerance in meters. |

---

## 5. Efficient Command Recipes

### Case 1: Standard Auto-Detection (Most Common)
Runs the unified calculation engine with automatic site detection, CRS projection, and solver selection:
```bash
uv run python scripts/calculate_frustum_volume.py --input inputs/south/Contours.shp
```

### Case 2: Explicit Elevation Column Mapping
When the shapefile uses a non-standard elevation attribute (e.g. `CONTOUR_Z` or `Z_VALUE`):
```bash
uv run python scripts/calculate_frustum_volume.py \
  --input inputs/custom_site/Survey.shp \
  --elevation-col CONTOUR_Z
```

### Case 3: Comprehensive Multi-Column Mapping (`--col-map`)
Map geometry, elevation, and boundary indicator in a single flag:
```bash
uv run python scripts/calculate_frustum_volume.py \
  --input inputs/custom_site/Survey.shp \
  --col-map "elevation=Z_FIELD, geometry=the_geom, boundary=TYPE, boundary_val=EXT_BND"
```

### Case 4: Separate External Boundary Polygon
For sites with a standalone boundary shapefile (e.g. concession limit):
```bash
uv run python scripts/calculate_frustum_volume.py \
  --input inputs/hassan_abdal_10b/Hassan_Abdal_10B.shp \
  --boundary inputs/hassan_abdal_10b/boundary.shp
```

### Case 5: Forcing a Specific Solver Mode
Override automatic solver detection when specific morphology is required:
```bash
# Closed pit/basin solver
uv run python scripts/calculate_frustum_volume.py --input inputs/south/Contours.shp --method ring

# Bounded planar partition solver (mining blocks)
uv run python scripts/calculate_frustum_volume.py --input inputs/hassan_abdal_10b/Hassan_Abdal_10B.shp --method split

# Open embankment corridor solver (dams/bunds)
uv run python scripts/calculate_frustum_volume.py --input inputs/north/Clip_Contour_North.shp --method band --close-dist 25.0
```

---

## 6. Automatic Solver Detection (`--method auto`)

The script dynamically inspects the shapefile geometry and chooses the exact solver:

1. **`ring` Solver (Closed Basin / Pit Model):**
   - Triggered when standalone closed contour rings are detected at the crest.
   - Slices terrain via topological ring containment.
   - *Example: `inputs/south/Contours.shp` ($204,086.06\text{ m}^3$).*

2. **`split` Solver (Bounded Mining Concession Block Model):**
   - Triggered when contours cut across the perimeter of a compact block (compactness $\ge 0.1$).
   - Slices terrain via line-extended planar boundary partitioning with crest containment.
   - *Example: `inputs/hassan_abdal_10b/Hassan_Abdal_10B.shp` ($82,388.03\text{ m}^3$).*

3. **`band` Solver (Open Embankment Bund Model):**
   - Triggered for elongated corridor morphology (compactness $< 0.1$) with open polylines.
   - Slices terrain via morphological buffer closure (`buffer(+d).buffer(-d)`).
   - *Example: `inputs/north/Clip_Contour_North.shp` ($294,079.65\text{ m}^3$).*

---

## 7. Standard Deliverables Checklist

**Step 1 — `calculate_frustum_volume.py`** produces 5 deliverables in `outputs/<site_name>/`:

1. `<prefix>_frustum_slice_polygons.shp`: Horizontal polygonal slice layers between successive contours with slice volume attributes.
2. `<prefix>_frustum_cumulative_polygons.shp`: Solid stage footprint polygons for each elevation stage.
3. `<prefix>_frustum_volumetric_report.csv`: Complete engineering schedule with elevations, depths, slice volumes, cumulative volumes ($m^3$, cu ft, acre-ft), and End-Area cross-check variances.
4. `<prefix>_stage_storage_curves.png`: High-resolution dual-axis plot of Stage vs. Footprint Area and Stage vs. Cumulative Volume.
5. `<prefix>_contour_slices_map.png`: 2D planimetric color-coded map of all discrete contour slice layers with colorbar.

**Step 2 — `export_viewer_data.py`** produces 2 additional deliverables in `outputs/<site_name>/`:

6. `viewer_data.geojson`: Viewer-compatible GeoJSON FeatureCollection containing hollow slice polygons, solid cumulative polygons, and original contour lines — with a top-level `properties` block holding summary metadata.
7. `<prefix>_3d_viewer.html`: Copy of the static CesiumJS 3D viewer template, ready to open.

---

## 8. End-to-End Production Workflow

```bash
# Step 1: Run universal volumetric calculation (with optional column mapping)
uv run python scripts/calculate_frustum_volume.py --input inputs/<site_name>/<shapefile>.shp

# Step 2: Export viewer data + deploy viewer HTML
uv run python scripts/export_viewer_data.py --input inputs/<site_name>/<shapefile>.shp

# Step 3: Serve locally and inspect in browser
python -m http.server 8080 --directory outputs/<site_name>/
# → Open: http://localhost:8080/<prefix>_3d_viewer.html
```
