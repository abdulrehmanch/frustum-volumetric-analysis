# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-09-26

### Added
- **Core Computational Engine (`scripts/calculate_frustum_volume.py`)**:
  - Prismoidal Frustum Volume calculation ($V_{\text{slice}} = \frac{\Delta h}{3}(A_k + A_{k+1} + \sqrt{A_k A_{k+1}})$).
  - Average End-Area validation and divergence metric tracking.
  - Three solver modes: `ring` (topological ring closure), `split` (boundary-cut partition), and `band` (morphological corridor buffering).
  - Downward spatial nesting enforcement ($A(Z_k) \ge A(Z_{k+1})$).
  - Automated export of 5 engineering deliverables: Slice shapefiles, Cumulative shapefiles, Tabular CSV schedule, Stage-Storage curves, and 2D Choropleth maps.
- **CesiumJS 3D WebGIS Inspection Engine (`scripts/export_viewer_data.py`, `scripts/viewer/3d_viewer.html`)**:
  - Zero-CORS, standalone interactive 3D WebGIS digital twin visualizer.
  - Real-time vertical exaggeration slider ($1\times$ to $20\times$), depth colormaps (Bathymetric, Magma, Viridis, Rainbow), and simulated material fill animation.
  - Dynamic Heads-Up Display (HUD) telemetry.
- **Automated Test Suite (`tests/test_frustum_math.py`)**:
  - Analytical validation against geometric truncated cone and pyramid benchmarks.
  - AM-GM inequality divergence proofs and monotonic containment constraints.
- **Open Source Infrastructure**:
  - Sample dataset (`examples/sample_heap_south/`).
  - GitHub Actions CI matrix testing across Python 3.10, 3.11, and 3.12.
  - MIT License with Engineering and Surveying Liability Disclaimer.
