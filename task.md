# 3D Viewer Overhaul — Task List

- [x] **1. Write `scripts/export_viewer_data.py`** — data exporter (shapefiles → GeoJSON + copy viewer HTML)
- [x] **2. Write `scripts/viewer/3d_viewer.html`** — static CesiumJS viewer
- [x] **3. Move legacy scripts to `scripts/retired/`**
  - [x] `generate_cesium_3d_viewer.py` → `scripts/retired/`
  - [x] `generate_3d_model.py` → `scripts/retired/`
- [x] **4. Update `SKILL.md`** — directory tree + deliverables + workflow section
- [x] **5. Verify** — ran exporter on south site ✓ valid JSON, 212 features, 1.6 MB
