---
name: fr-generate-3d-viewer
description: >-
  Generate, configure, and serve interactive 3D WebGIS CesiumJS viewers for contour frustum volumetric
  analysis. Exports multi-layer extruded 3D polygons, cumulative solids, and survey contour lines into
  viewer-compatible GeoJSON, and deploys a standalone HTML visualizer with satellite base layers, ground
  anchoring, vertical exaggeration, and volumetric HUD inspection.
---

# CesiumJS 3D Volumetric Viewer & Local Visualizer Skill

This skill guides the compilation of interactive 3D WebGIS models from frustum volumetric deliverables using `scripts/export_viewer_data.py`, and serving the dynamic local portal using `scripts/serve_portal.py`.

---

## 1. System Architecture

```text
outputs/<assignment_name>/<unit_name>/
├── viewer_data.geojson           # Standalone GeoJSON layers (hollow, solid, contour vectors)
├── <prefix>_3d_viewer.html       # Deployed standalone CesiumJS 3D visualizer
└── <prefix>_frustum_report.csv   # Schedule consumed by viewer & dashboards
```

---

## 2. Generate 3D Viewer & GeoJSON

Run the export engine pointing to the survey shapefile or output directory:
```bash
uv run python scripts/export_viewer_data.py \
  --input inputs/<assignment_name>/<unit_name>/<shapefile>.shp \
  --output-dir outputs/<assignment_name>/<unit_name>
```

**What this step produces:**
1. Validates all 5 standardized output deliverables produced by Step 1.
2. Flattens geometries to 2D and converts to WGS84 coordinates.
3. Compiles `viewer_data.geojson` with hollow slice rings, cumulative solids, contour polylines, and bounding volume metadata.
4. Deploys `<prefix>_3d_viewer.html` customized with site prefix, rainbow elevation palette by default, contours toggled off by default, and cubic feet ($ft^3$) + metric ($m^3$) HUD inspection.

---

## 3. Visualize & Serve Locally

Start the local dynamic WebGIS portal server:
```bash
python3 scripts/serve_portal.py --port 8080
```

- **Portfolio Command Center:** Open `http://localhost:8080/`
- **Assignment Landing Page:** Open `http://localhost:8080/<assignment_name>/`
- **Interactive 3D Viewer:** Open `http://localhost:8080/<assignment_name>/<unit_name>/<prefix>_3d_viewer.html`

*The server automatically detects any new assignment folder, generates site dashboards on the fly, and updates table metrics on page load or when clicking `↻ Refresh Data`.*
