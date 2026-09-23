# Project Brief — Prismoidal Frustum Volumetric Analysis & 3D WebGIS Inspection Engine

**Author:** Abdul Rehman · Senior GIS Developer · Burewala, Pakistan  
**Stack:** Python · GeoPandas · Shapely · NumPy · Matplotlib · SciPy · Plotly · CesiumJS · PostGIS / GIS  
**Version:** 1.0  

---

## How to Use This Document

This is a single source-of-truth brief. Every section is tagged. When you need a specific format, extract only the tagged sections.

| Tag | Use Case |
|-----|----------|
| `[ALL]` | Every context |
| `[UPWORK]` | Upwork proposals and portfolio |
| `[LINKEDIN]` | LinkedIn posts and Featured section |
| `[CONTRACT]` | Client contracts and SOW |
| `[INTERVIEW]` | Resume, CV, and interviews |
| `[INTERNAL]` | Team handoffs and subcontractors |

**Quick extraction map** → see Section 11 at the end.

---

## Section 1 · Project Identity
> Tags: `[ALL]`

| Field | Value |
|-------|-------|
| **Project Title** | Multi-Layer Prismoidal Frustum Volumetric Analysis & 3D WebGIS Visualizer |
| **Project Type** | Geospatial Engineering Pipeline / Computational Geodesy / 3D WebGIS Application |
| **Version / Date** | v1.0 — September 2026 |
| **Prepared By** | Abdul Rehman — Senior GIS Developer |
| **Client / Company** | Mines and Minerals Department (MMD) / Earthwork Surveying & Excavation Analysis |
| **Platform / Channel** | Direct Engineering Engagement / Specialized Technical Deliverable |

---

## Section 2 · Executive Summary
> Tags: `[UPWORK]` `[LINKEDIN]` `[INTERVIEW]` `[CONTRACT]` (cover paragraph)

### 2.1 Project Overview

Designed and built an automated computational geospatial pipeline that calculates the multi-layer volumetric capacity and earthwork quantities of complex terrain corridors from high-resolution survey contour data ($\Delta h = 0.5\,\text{m}$ interval). The engine executes prismoidal frustum calculations across 40 discrete slice stages, generating stage-storage curves, multi-unit engineering reports, ESRI shapefiles, and an interactive, client-side 3D CesiumJS WebGIS explorer with real-time volumetric HUD telemetry and depth-fill simulation.

### 2.2 Problem Statement

Accurate volume estimation for open-pit mining, quarrying, embankment construction, and water retention basins is notoriously difficult when working with complex terrain:
- **Topological Inconsistency:** Field survey datasets frequently mix closed contours with open polylines lacking explicit boundary envelopes, causing standard GIS tools to fail or produce distorted polygon boundaries.
- **Overestimation from Crude Approximations:** Traditional Average End-Area methods model terrain as straight-sided prisms, introducing systematic upward volume bias where side slopes taper non-linearly.
- **TIN/Raster Interpolation Artifacts:** Generating intermediate Digital Elevation Models (DEMs) or Triangulated Irregular Networks (TINs) often fabricates artificial volume across unsurveyed flat plains and introduces grid resolution rounding errors.
- **Lack of Stakeholder Inspection Tools:** Decision-makers, surveyors, and inspectors require intuitive, multi-angle 3D visual verification without needing desktop CAD or GIS software installations.

### 2.3 Solution Summary

Engineered a dataset-agnostic Python pipeline using GeoPandas, Shapely, and NumPy that processes both bounded (closed outer loop) and unbounded (open polyline) contour topologies in metric UTM coordinates (UTM Zone 43N, EPSG:32643):
- **Pure Vector Footprint Reconstruction:** For open-contour surveys, implemented a 25-meter morphological buffer closure (`buffer(+d)` followed by `buffer(-d)`), topological line noding, and corridor polygonization to construct exact surveyed stage footprints without raster/TIN interpolation.
- **Strict Downward Nesting:** Enforced geometric containment ($A(Z_k) \ge A(Z_{k+1})$) from crest down to base, guaranteeing monotonic area schedules and zero volumetric fabrication over unsurveyed terrain.
- **Prismoidal Frustum Volume Model:** Implemented $V_{\text{slice}} = \frac{\Delta h}{3}\left(A_k + A_{k+1} + \sqrt{A_k A_{k+1}}\right)$, where the geometric mean term $\sqrt{A_k A_{k+1}}$ precisely captures side-slope wall taper.
- **Dual-Method Engineering Validation:** Cross-checked every stage against the classical Average End-Area method $V_{\text{end}} = \frac{\Delta h}{2}\left(A_k + A_{k+1}\right)$, outputting slice-by-slice and cumulative divergence metrics.
- **Zero-CORS 3D CesiumJS Web Application:** Created an interactive, standalone browser-based 3D digital twin embedding extruded polygonal slices, bathymetric/magma depth colormaps, vertical exaggeration sliders (1x–20x), an interactive material/water fill simulator, and real-time volumetric HUD cards.

### 2.4 Outcome / Impact

- **Accurately Modeled 498,165.71 m³ Across Two Mining Corridors:**
  - **North Corridor:** Evaluated 24 elevation stages (157.0 m to 168.5 m; 11.5 m relief) across 23 slices. Footprint narrowed from 50,916.27 m² (5.09 ha) at base to 614.56 m² (0.06 ha) at crest, computing **294,079.65 m³** ($10.39\times 10^6\,\text{ft}^3$ / $238.41\,\text{acre-ft}$) of frustum volume.
  - **South Corridor:** Evaluated 18 elevation stages (157.0 m to 165.5 m; 8.5 m relief) across 17 slices. Footprint narrowed from 39,652.74 m² (3.97 ha) at base to 2,526.29 m² (0.25 ha) at crest, computing **204,086.06 m³** ($7.21\times 10^6\,\text{ft}^3$ / $165.46\,\text{acre-ft}$) of frustum volume.
- **Rigorous Verification Bracket:** Quantified Average End-Area overestimation at just +195.06 m³ (+0.07%) on North and +167.14 m³ (+0.08%) on South, demonstrating exceptionally tight convergence and giving engineering leadership audit-grade confidence in the results.
- **Full Deliverable Suite:** Automatically exported production-ready ESRI shapefiles (slices and solid cumulative stages), publication-quality dual-axis stage-storage curve plots, 2D planimetric slice maps, and standalone 3D CesiumJS visualizers.

---

## Section 3 · Scope of Work
> Tags: `[CONTRACT]` (full) · `[UPWORK]` (summary) · `[INTERNAL]` (full)

### 3.1 In Scope

- **Coordinate Transformation & Preprocessing:** Automatic UTM projection detection and reprojection to UTM Zone 43N (EPSG:32643); flattening 3D contour vertices to strict 2D geometry to prevent coordinate z-leakage into planar area math.
- **Multi-Topology Boundary Delineation:**
  - *Explicit Boundary Mode (South-style):* Extraction of zero-elevation perimeter loop, nested internal rings, and progressive union.
  - *Open Contour Mode (North-style):* Morphological closing (25.0 m outward/inward buffer) of contour lines, line noding via `shapely.ops.unary_union`, polyline closing against corridor limits, and polygonization.
- **Geometric Nesting Enforcement:** Downward spatial accumulation from crest to base ensuring lower contour footprints strictly contain higher footprints ($A_k \ge A_{k+1}$).
- **Multi-Method Volumetric Computation:**
  - Slice-level and cumulative prismoidal frustum calculations ($\Delta h = 0.5\,\text{m}$).
  - Slice-level and cumulative average end-area calculations.
  - Absolute ($\Delta V$ in m³) and percentage relative error tracking per stage.
- **Multi-Unit Engineering Schedule Generation:** Production of formatted CSV reporting tables including stage ID, elevation (m), stage depth (m), contour area (m² and ha), slice frustum volume (m³, $\text{ft}^3$), cumulative volume (m³, $1000\,\text{m}^3$, acre-feet, $\text{ft}^3$), end-area volumes, and delta variance.
- **GIS Cartographic & Vector Outputs:**
  - ESRI Shapefiles (`.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`) for individual horizontal slice layers.
  - ESRI Shapefiles for solid cumulative stage footprints.
  - Dual-axis stage-area ($A$ vs $Z$) and stage-storage ($V$ vs $Z$) curve plots (.png).
  - Planimetric 2D contour slice choropleth maps (.png).
- **Interactive 3D Digital Twin Viewer (CesiumJS):**
  - Standalone HTML application with pre-embedded GeoJSON (no web server / zero CORS barriers).
  - Extruded 3D polygonal geometry toggleable between hollow ring slices and solid accumulated volumes.
  - Real-time vertical exaggeration control (1.0x to 20.0x).
  - 4 depth-adaptive colormaps: Bathymetric (Pit Depth), Magma, Viridis, and Rainbow.
  - Interactive stage fill slider simulating pit filling with material or water.
  - Dynamic Heads-Up Display (HUD) card displaying real-time metrics on hover and click.
  - Orthographic and perspective camera presets (Isometric, Top-Down, Front, Side).
- **3D Terrain Surface Modeling:** Scripted generation of 3D Delaunay/grid surfaces and longitudinal profile slices using SciPy, Plotly, and Matplotlib.

### 3.2 Out of Scope ⚠

- On-site field survey data acquisition or drone/LiDAR flight execution.
- Geotechnical slope stability or soil mechanics analysis (e.g., angle of repose, shear strength).
- Environmental runoff or hydrogeological seepage modeling beyond geometric stage-storage capacity.
- Continuous cloud hosting or live database synchronization (deliverables are self-contained files and offline-capable HTML apps).

---

## Section 4 · Technical Stack
> Tags: `[ALL]`

| Layer | Technologies |
|-------|-------------|
| **Core Language** | Python 3.10+ |
| **Geospatial Processing** | GeoPandas, Shapely 2.0+ (`unary_union`, `polygonize`, `buffer`), Fiona, PyProj |
| **Math & Data Analysis** | NumPy, Pandas, SciPy (`griddata`, `Delaunay`) |
| **Cartography & Plotting** | Matplotlib (dual-axis engineering curves, choropleths), Plotly (3D interactive surfaces) |
| **3D WebGIS Visualization** | CesiumJS (WebGL 3D globe/scene), HTML5, CSS3, JavaScript (ES6+), Font Awesome |
| **Coordinate Reference Systems** | WGS 84 (EPSG:4326), UTM Zone 43N (EPSG:32643) |
| **Data Formats** | ESRI Shapefile suite (.shp, .shx, .dbf, .prj, .cpg), CSV, GeoJSON, HTML5, PNG |

**Keyword line:**  
`Python · GeoPandas · Shapely · PostGIS · GIS · Volumetric Analysis · CesiumJS · 3D WebGIS · Stage-Storage Curve · Earthwork Calculation · Prismoidal Frustum · UTM Reprojection · Spatial Analysis`

---

## Section 5 · Role & Team
> Tags: `[UPWORK]` `[LINKEDIN]` `[INTERVIEW]` `[INTERNAL]`

| Field | Value |
|-------|-------|
| **Your Role** | Lead Geospatial Computational Developer & 3D WebGIS Specialist |
| **Team Size** | Solo Architecture & Engineering Implementation |
| **Client Contact** | Project Managers, Survey Engineers, Mines & Minerals Department Stakeholders |
| **Responsibilities** | Mathematical algorithm formulation, vector polygonization pipeline design, open-contour morphology resolution, multi-unit report automation, cartographic visualization, and CesiumJS 3D Web viewer development |

---

## Section 6 · Deliverables & Milestones
> Tags: `[CONTRACT]` (full) · `[UPWORK]` (milestone table) · `[INTERNAL]`

### 6.1 Deliverables Checklist

- [x] Python calculation engines (`calculate_frustum_volume_north.py`, `calculate_frustum_volume_south.py`)
- [x] 3D CesiumJS application generator (`generate_cesium_3d_viewer.py`)
- [x] 3D mesh and surface profile modeler (`generate_3d_model.py`)
- [x] ESRI Shapefiles for horizontal slices (`<region>_frustum_slice_polygons.shp`)
- [x] ESRI Shapefiles for cumulative stage footprints (`<region>_frustum_cumulative_polygons.shp`)
- [x] Tabular engineering schedules (`<region>_frustum_volumetric_report.csv`) in m³, $\text{ft}^3$, and acre-feet
- [x] High-resolution Stage-Storage & Stage-Area curve charts (`<region>_stage_storage_curves.png`)
- [x] Planimetric slice maps (`<region>_contour_slices_map.png`)
- [x] Standalone 3D CesiumJS interactive viewers (`north_3d_cesium_viewer.html`, `south_3d_cesium_viewer.html`)
- [x] Plain-language methodology guide (`METHODOLOGY_SIMPLE.md`)
- [x] Rigorous civil engineering technical methodology specification (`METHODOLOGY_TECHNICAL.md`)

### 6.2 Key Milestones

| Milestone | Deliverables | Verification Standard |
|-----------|--------------|-----------------------|
| **M1: Coordinate & Geometric Ingestion** | Reprojection engine & boundary delineation | Metric UTM Zone 43N conversion; 2D flattening; successful topological polygonization of open contour polylines |
| **M2: Volumetric Engine & Cross-Validation** | Multi-method slice calculations & nesting | Monotonic footprint shrinking; Frustum vs Average End-Area validation table showing <0.1% divergence |
| **M3: Geospatial & Cartographic Reporting** | Shapefiles, CSV schedules, and storage curves | Strict ESRI shapefile compliance; dual-axis stage-storage plots; multi-unit reporting |
| **M4: 3D CesiumJS Digital Twin Application** | Zero-CORS interactive web viewer | Extruded 3D slices, real-time vertical exaggeration, fill simulation, dynamic HUD inspection card |

---

## Section 7 · Assumptions & Client Dependencies
> Tags: `[CONTRACT]` `[INTERNAL]`

- **Contour Vertical Interval:** Input contours are assumed to have a consistent elevation step ($\Delta h = 0.5\,\text{m}$).
- **Elevation Attribute Integrity:** Contour geometries must contain a valid numeric elevation attribute (`ELEVATION` or similar) in meters.
- **Topological Continuity:** Open contour polylines must have gap spacings smaller than the 25.0 m morphological closing buffer to allow coherent corridor enclosure.
- **No Interpolated Voids:** Ground not surveyed or contoured is assumed to be unexcavated/external and is deliberately excluded from volumetric aggregation.

---

## Section 8 · Pricing & Payment Terms
> Tags: `[CONTRACT]`

| Scope Item | Model | Standard Allocation |
|------------|-------|---------------------|
| Custom Volumetric Scripting & Topology Cleaning | Fixed Price / Milestone | 40% upon successful vector polygonization and volume schedule |
| Deliverable Shapefiles, CSV Schedules & Curves | Milestone Delivery | 30% upon delivery of verified shapefiles, CSV reports, and charts |
| Interactive 3D CesiumJS Application & 3D Modeling | Milestone Delivery | 30% upon client review and acceptance of standalone 3D web viewer |

---

## Section 9 · IP, Confidentiality & Handoff
> Tags: `[CONTRACT]` `[INTERNAL]`

- **Source Code Ownership:** Full ownership of calculation scripts, 3D Cesium viewer templates, and documentation transferred upon project completion.
- **Data Confidentiality:** Survey contour coordinates, spatial lease boundaries, and exact mine lease locations remain proprietary to the client and are handled under strict confidentiality.
- **Self-Contained Deployment:** All HTML/JS deliverables are completely self-contained with embedded data strings, requiring no external GIS server, API keys, or database connections.

---

## Section 10 · Portfolio Entry
> Tags: `[UPWORK]` `[LINKEDIN]`

### 10.1 Short Blurb (Proposal / Profile Showcase)

> **Automated Earthwork & Pit Volumetric Analysis Engine (Python + CesiumJS)**  
> Developed an automated geospatial pipeline calculating multi-layer prismoidal frustum volumes from 0.5m survey contours across 40 elevation stages. The solution features pure vector polygonization for open contours (avoiding TIN/raster artifacts), dual-method validation against civil Average End-Area standards (<0.1% divergence), and an interactive 3D CesiumJS digital twin with dynamic vertical exaggeration and fill simulation. Total volume calculated: 498,165.71 m³ (403.87 acre-feet).

### 10.2 Upwork Project Catalog / Case Study Overview

- **Title:** Automated Multi-Layer Volumetric & Stage-Storage Analysis with 3D CesiumJS Viewer
- **Role:** Lead Geospatial Developer
- **Client Need:** Calculate exact excavation and impoundment capacity from complex survey contours across two mining corridors without introducing raster interpolation distortions, paired with a web-based 3D visual inspection tool for non-technical stakeholders.
- **Key Metrics:**
  - **498,165.71 m³** ($17.59\times 10^6\,\text{ft}^3$ / $403.87\,\text{acre-ft}$) total combined capacity computed.
  - **0.07% to 0.08%** error margin between Prismoidal Frustum and Average End-Area cross-validation.
  - **40 discrete 0.5m elevation slices** delineated, nested, and exported to ESRI shapefiles.
  - **Zero-CORS 3D CesiumJS Web Application** with real-time HUD telemetry, depth colormaps, and interactive fill simulation.

---

## Section 11 · Quick Extraction Reference
> Tags: `[INTERNAL]`

- **Upwork Proposal Hook:** Use Section 2.1 + Section 2.4. Emphasize mathematically rigorous frustum modeling, automated open-contour vector polygonization without raster artifacts, and the interactive 3D CesiumJS digital twin.
- **Resume Bullets:** Extract from Section 2.4, Section 3.1, and Section 4.
- **Technical Proposal / SOW:** Extract Section 3 (Scope), Section 6 (Milestones), and Section 7 (Assumptions).
