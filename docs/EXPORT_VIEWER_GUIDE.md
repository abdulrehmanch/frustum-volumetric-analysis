# `export_viewer_data.py` — User Guide

Exports a viewer-compatible GeoJSON from frustum analysis outputs and deploys the static 3D CesiumJS viewer alongside it.

> [!IMPORTANT]
> **Run `calculate_frustum_volume.py` first.**  
> This script reads the shapefiles and CSV that `calculate_frustum_volume.py` produces.  
> If those outputs are missing the script will fail with a clear error.

---

## Prerequisites

```
outputs/<site_name>/
  <prefix>_frustum_slice_polygons.shp       ← required
  <prefix>_frustum_cumulative_polygons.shp  ← required
  <prefix>_frustum_volumetric_report.csv    ← required
```

---

## Basic Usage

```bash
uv run python scripts/export_viewer_data.py --input inputs/<site_name>/<shapefile>.shp
```

The script auto-derives the output directory and filename prefix from the input path using the same convention as `calculate_frustum_volume.py`:

| Input path | Output directory | Prefix |
|---|---|---|
| `inputs/south/Contours.shp` | `outputs/south/` | `south` |
| `inputs/hassan_abdal_10b/Hassan_Abdal_10B.shp` | `outputs/hassan_abdal_10b/` | `hassan_abdal_10b` |

---

## Outputs

Two files are written to `outputs/<site_name>/`:

| File | Description |
|---|---|
| `viewer_data.geojson` | GeoJSON with hollow slice polygons, solid cumulative polygons, and original contour lines |
| `<prefix>_3d_viewer.html` | Static CesiumJS viewer — copy of `scripts/viewer/3d_viewer.html` |

---

## Opening the Viewer

The viewer uses `fetch()` to load `viewer_data.geojson`, which requires a local HTTP server (browser CORS restriction on `file://`):

```bash
python3 -m http.server 8080 --directory outputs/<site_name>/
# then open:  http://localhost:8080/<prefix>_3d_viewer.html
```

---

## Required Shapefile Columns

The script reads from `<prefix>_frustum_slice_polygons.shp`. The columns it needs and their default names are:

| `--col-*` flag | Default name | Meaning |
|---|---|---|
| `--col-stage` | `STAGE_ID` | Integer stage / layer ID |
| `--col-z-low` | `Z_LOW` | Bottom elevation of the slice (m) |
| `--col-z-high` | `Z_HIGH` | Top elevation of the slice (m) |
| `--col-delta-h` | `DELTA_H` | Vertical interval of the slice (m) |
| `--col-area` | `AREA_M2` | Planimetric area of the slice (m²) |
| `--col-vol` | `VOL_M3` | Frustum slice volume (m³) |
| `--col-vol-cuft` | `VOL_CUFT` | Frustum slice volume (ft³) |
| `--col-cumul` | `CUMUL_M3` | Cumulative frustum volume (m³) |
| `--col-cum-cuft` | `CUM_CUFT` | Cumulative frustum volume (ft³) |

The input contour shapefile also needs one column:

| `--col-*` flag | Default name | Meaning |
|---|---|---|
| `--col-elev` | `ELEVATION` | Contour elevation value (m) |

> [!NOTE]
> If any column is missing the script stops immediately and prints the list of columns that **are** available in the file — no silent fallbacks.

---

## Column Schemas by Site

Different sites produced by `calculate_frustum_volume.py` may use different column names. The actual schemas observed in this project are:

### `south`

```
_frustum_slice_polygons.shp columns:
  STAGE_ID  Z_LOW  Z_HIGH  DELTA_H  AREA_M2  VOL_M3  VOL_CUFT  CUMUL_M3  CUM_CUFT

input shapefile (Contours.shp) columns:
  OBJECTID  FID_1  ELEVATION  LAYER  NAME  Shape_Leng
```

All defaults match → **no overrides needed**.

### `hassan_abdal_10b`

```
_frustum_slice_polygons.shp columns:
  STAGE_ID  Z_LOW  Z_HIGH  DELTA_H  A_LOW_M2  A_HIGH_M2  VOL_M3  VOL_CUFT  CUMUL_M3  CUM_CUFT

input shapefile (Hassan_Abdal_10B.shp) columns:
  ELEVATION  LAYER  Shape_Leng  Shape_Le_1
```

`AREA_M2` does not exist — use `A_LOW_M2` (lower stage area) → **one override needed**.

---

## Per-Site Commands

### South

```bash
uv run python scripts/export_viewer_data.py \
  --input inputs/south/Contours.shp
```

### Hassan Abdal 10B

```bash
uv run python scripts/export_viewer_data.py \
  --input inputs/hassan_abdal_10b/Hassan_Abdal_10B.shp \
  --col-area A_LOW_M2
```

### North (when available)

```bash
# Run --help first to confirm column names after analysis is generated:
uv run python scripts/export_viewer_data.py --help

uv run python scripts/export_viewer_data.py \
  --input inputs/north/Clip_Contour_North.shp \
  [--col-* overrides if needed]
```

---

## All CLI Flags

```
usage: export_viewer_data.py [-h]
       --input INPUT
       [--output-dir OUTPUT_DIR]
       [--prefix PREFIX]
       [--col-stage COL]
       [--col-z-low COL]
       [--col-z-high COL]
       [--col-delta-h COL]
       [--col-area COL]
       [--col-vol COL]
       [--col-vol-cuft COL]
       [--col-cumul COL]
       [--col-cum-cuft COL]
       [--col-elev COL]
```

| Flag | Required | Default | Description |
|---|---|---|---|
| `--input` / `-i` | **Yes** | — | Path to the original input contour shapefile |
| `--output-dir` / `-o` | No | Auto | Output folder (auto-derived from input path) |
| `--prefix` / `-p` | No | Auto | Output filename prefix (auto-detected from output folder) |
| `--col-stage` | No | `STAGE_ID` | Stage ID column in slice shapefile |
| `--col-z-low` | No | `Z_LOW` | Bottom elevation column |
| `--col-z-high` | No | `Z_HIGH` | Top elevation column |
| `--col-delta-h` | No | `DELTA_H` | Vertical interval column |
| `--col-area` | No | `AREA_M2` | Slice area column (m²) |
| `--col-vol` | No | `VOL_M3` | Slice volume column (m³) |
| `--col-vol-cuft` | No | `VOL_CUFT` | Slice volume column (ft³) |
| `--col-cumul` | No | `CUMUL_M3` | Cumulative volume column (m³) |
| `--col-cum-cuft` | No | `CUM_CUFT` | Cumulative volume column (ft³) |
| `--col-elev` | No | `ELEVATION` | Elevation column in input contour shapefile |

---

## Diagnosing Column Errors

If you get a column error, the script shows exactly what went wrong:

```
ERROR: Missing columns in outputs/hassan_abdal_10b/hassan_abdal_10b_frustum_slice_polygons.shp:
  --col-area  →  'AREA_M2'  (not found)
  Available columns: ['STAGE_ID', 'Z_LOW', 'Z_HIGH', 'DELTA_H', 'A_LOW_M2', 'A_HIGH_M2', ...]
```

Pick the right column from the `Available columns` list and pass it as a `--col-*` flag.

---

## Full Two-Step Workflow

```bash
# Step 1: Calculate volumes
uv run python scripts/calculate_frustum_volume.py --input inputs/<site>/<file>.shp

# Step 2: Export viewer data (add --col-* overrides if needed)
uv run python scripts/export_viewer_data.py --input inputs/<site>/<file>.shp

# Step 3: Serve and open
python3 -m http.server 8080 --directory outputs/<site>/
# → http://localhost:8080/<prefix>_3d_viewer.html
```
