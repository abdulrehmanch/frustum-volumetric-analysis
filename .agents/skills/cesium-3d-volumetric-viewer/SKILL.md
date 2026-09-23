---
name: cesium-3d-volumetric-viewer
description: >-
  Generate, configure, and serve interactive 3D WebGIS CesiumJS viewers for contour frustum volumetric
  analysis. Exports multi-layer extruded 3D polygons, cumulative solids, and survey contour lines into
  viewer-compatible GeoJSON, and deploys a standalone HTML visualizer with satellite base layers, ground
  anchoring, vertical exaggeration, and volumetric HUD inspection.
---

# CesiumJS 3D Volumetric Viewer Skill

This skill guides the preparation, export, and deployment of interactive 3D WebGIS models from standardized frustum volumetric analysis outputs using `scripts/export_viewer_data.py` and the static CesiumJS viewer template `scripts/viewer/3d_viewer.html`.

---

## 1. System Architecture

The 3D visualizer is built on a decoupled architecture separating data compilation from client-side WebGL rendering:

```
mmd_frustum_volumetric_analysis/
├── scripts/
│   ├── calculate_frustum_volume.py   # Volumetric engine: produces standardized deliverables
│   ├── export_viewer_data.py         # Viewer compiler: standardized deliverables → GeoJSON + HTML
│   └── viewer/
│       └── 3d_viewer.html            # Static reusable CesiumJS WebGL viewer template
├── outputs/<site_name>/
│   ├── <prefix>_3d_viewer.html       # Deployed standalone HTML client
│   └── viewer_data.geojson           # Standalone GeoJSON layer (features + metadata)
```

---

## 2. Standardized Execution Workflow

### Step 1: Run Volumetric Analysis Engine
```bash
uv run python scripts/calculate_frustum_volume.py --input inputs/<site_name>/<shapefile>.shp
```

### Step 2: Export 3D Viewer & Deploy HTML Client
```bash
uv run python scripts/export_viewer_data.py --input inputs/<site_name>/<shapefile>.shp
```

*The exporter automatically resolves `--output-dir outputs/<site_name>/` and `<prefix>_` naming directly from the input path, strictly reading the standardized deliverables without requiring manual column mapping or guesswork.*

---

## 3. Standardized Output Schema Contract

The exporter directly validates and consumes the deliverables generated in `outputs/<site_name>/`:

| Deliverable File | Standardized Attributes Consumed |
| :--- | :--- |
| `<prefix>_frustum_slice_polygons.shp` | `STAGE_ID`, `Z_LOW`, `Z_HIGH`, `DELTA_H`, `A_LOW_M2`, `A_HIGH_M2`, `VOL_M3`, `VOL_CUFT`, `CUMUL_M3`, `CUM_CUFT`, `geometry` |
| `<prefix>_frustum_cumulative_polygons.shp` | `STAGE_ID`, `ELEVATION`, `AREA_M2`, `AREA_HA`, `DEPTH_M`, `geometry` |
| `<prefix>_frustum_volumetric_report.csv` | `Stage_ID`, `Elevation_m`, `Cumul_Frustum_Vol_m3` |

---

## 4. GeoJSON Specification (`viewer_data.geojson`)

The generated GeoJSON encapsulates all layers in WGS84 (`EPSG:4326`):

1. **Top-Level `properties` Block:**
   - `site_name`, `prefix`, `base_elev`, `crest_elev`, `total_depth_m`
   - `total_vol_m3`, `total_vol_acft`, `total_vol_cuft`
   - `center_lon`, `center_lat`, `bounds`
2. **Feature Collections (`layer_type`):**
   - `slice_hollow`: Concentric polygonal difference rings representing discrete horizontal excavation slices.
   - `slice_solid`: Cumulative footprint polygons representing continuous solid bodies.
   - `contour_line`: Survey contour polyline vectors with elevation tags.

---

## 5. Interactive 3D Viewer Capabilities

The CesiumJS visualizer (`<prefix>_3d_viewer.html`) provides:

- **Satellite Base Layer:** High-Resolution **ESRI World Imagery** loaded by default (toggleable to OpenStreetMap or CartoDB Dark).
- **Ground Clamping & Contact:** **Anchored to Ground (0m Datum)** by default so the pit touches the satellite terrain surface directly; toggleable to **Absolute MSL Elevation**.
- **Geometry Slicing:** Instant switching between **Hollow Ring Voids** and **Solid Embankment Slabs**.
- **Color Palettes:** Bathymetric Deep Blue, Magma, Viridis, Plasma, and Rainbow depth scales.
- **Vertical Exaggeration:** Dynamic client-side vertical multiplier slider ($1.0\times$ to $20.0\times$).
- **Water / Material Fill Simulation:** Adjustable fill level slider elevating a semi-transparent water plane.
- **Survey Contours:** Real-time polyline visibility toggle.
- **HUD Telemetry:** Real-time hover & click inspection reporting Layer ID, elevation span, surface area ($ha$ & $m^2$), slice volume ($m^3$), cumulative volume ($m^3$, $ft^3$, acre-ft).
- **Perspective Presets:** One-click camera framing for Plan, Oblique SE, Oblique NW, and Cross-Section.

---

## 6. Serving & Local Viewing

Due to browser CORS policies on `fetch('./viewer_data.geojson')`, serve the output folder via HTTP:

```bash
# 1. Start local HTTP server
python3 -m http.server 8080 --directory outputs/<site_name>/

# 2. Open viewer URL
# http://localhost:8080/<prefix>_3d_viewer.html
```
