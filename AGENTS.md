# Project Guidelines & Directory Organization Rules

## 1. Directory Structure Standards
All work in this repository must strictly adhere to the following directory layout:

- **`inputs/<site_name>/`**: Raw survey shapefiles and GIS inputs (e.g. `inputs/south/`, `inputs/north/`, `inputs/hassan_abdal_10b/`).
- **`outputs/<site_name>/`**: All generated engineering outputs, reports, shapefiles, PNG curves, and 3D viewers (e.g. `outputs/south/`, `outputs/north/`, `outputs/hassan_abdal_10b/`).
- **`scripts/`**: Executable calculation and processing scripts (`scripts/calculate_frustum_volume.py`, `scripts/generate_3d_model.py`, etc.). Legacy scripts live in `scripts/retired/`.
- **`docs/`**: Technical methodology guides and project documentation (`docs/METHODOLOGY_TECHNICAL.md`, etc.).
- **`reference_sketches/`**: Project concept sketches and survey drawings.

> **CRITICAL RULE:** Never write raw input files, shapefiles, reports, or plot images to the repository root directory. Always place them in their respective `inputs/<site_name>/` or `outputs/<site_name>/` folder.

---

## 2. Volumetric Calculation & 3D Viewer Commands

**Step 1 — Calculate Volumes:**
```bash
uv run python scripts/calculate_frustum_volume.py --input inputs/<site_name>/<shapefile>.shp
```

**Step 2 — Export 3D Viewer Data & Deploy HTML:**
```bash
uv run python scripts/export_viewer_data.py --input inputs/<site_name>/<shapefile>.shp
```

*Both scripts automatically derive `--output-dir outputs/<site_name>/` and `<site_name>_` prefixing from the input path.*

---

## 3. Skill Reference
- **Volumetric Engine & Mathematics:** Refer to `.agents/skills/contour-frustum-volume/SKILL.md`.
- **3D CesiumJS WebGIS Viewer:** Refer to `.agents/skills/cesium-3d-volumetric-viewer/SKILL.md`.

---

## 4. Engineering Code & Execution Principles

> **CRITICAL RULE — NEVER WRITE FALLBACK LOGIC:**
> Never write automatic fallbacks, silent defaults, or heuristic guessing logic into scripts, pipelines, or codebase tools. If an expected column, attribute, file, or parameter is missing or invalid:
> - **Fail loudly and immediately** with a clear, actionable error message.
> - Display the exact missing item and list all available valid candidates.
> - Require explicit CLI arguments or user configuration instead of silently guessing or falling back.

