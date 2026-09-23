#!/usr/bin/env python3
"""
generate_cesium_3d_viewer.py

Generates an interactive, standalone 3D CesiumJS application for the South area:
- 3D extruded polygon pit slices colored by depth
- Interactive depth color scales (Bathymetric / Pit Depth, Magma, Viridis, Rainbow)
- Real-time Vertical Exaggeration Slider (1x to 20x)
- Interactive Pit Water / Material Fill Simulation Slider
- Hover and click feature inspection HUD card with volumes in m³, ft³, and acre-feet
- Camera perspective view presets
- Fully self-contained with embedded GeoJSON data (zero CORS restrictions)
"""

import os
import json
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.geometry import Polygon, MultiPolygon, mapping

def generate_cesium_viewer(default_geometry_mode="hollow", region="south"):
    region = region.strip().lower()
    region_title = region.capitalize()
    base_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(base_dir, region, "output")
    slice_shp = os.path.join(out_dir, f"{region}_frustum_slice_polygons.shp")
    cumul_shp = os.path.join(out_dir, f"{region}_frustum_cumulative_polygons.shp")
    csv_report = os.path.join(out_dir, f"{region}_frustum_volumetric_report.csv")
    out_html = os.path.join(out_dir, f"{region}_3d_cesium_viewer.html")

    # Input contour shapefile filename differs per region.
    input_dir = os.path.join(base_dir, region, "input")
    candidate_inputs = [
        os.path.join(input_dir, "Contours.shp"),
        os.path.join(input_dir, "Clip_Contour_North.shp"),
    ]
    input_shp = next((p for p in candidate_inputs if os.path.exists(p)), None)
    if input_shp is None:
        # Fall back to the first .shp found in the region's input folder.
        shps = [f for f in os.listdir(input_dir) if f.lower().endswith(".shp")] if os.path.isdir(input_dir) else []
        input_shp = os.path.join(input_dir, shps[0]) if shps else candidate_inputs[0]

    print(f"Loading shapefiles for CesiumJS generation (Region: {region}, Default Mode: {default_geometry_mode})...")
    gdf_slices = gpd.read_file(slice_shp).to_crs("EPSG:4326")
    gdf_cumul = gpd.read_file(cumul_shp).to_crs("EPSG:4326")
    gdf_input = gpd.read_file(input_shp).to_crs("EPSG:4326")
    df_report = pd.read_csv(csv_report)

    # Derive base (toe) and crest (peak) elevations from the data itself rather
    # than hardcoding 157.0 / 165.5. The base is the lowest slice bottom and the
    # crest is the highest slice top; total relief follows from these.
    base_elev = float(gdf_slices['Z_LOW'].min())
    crest_elev = float(gdf_slices['Z_HIGH'].max())
    total_depth = round(crest_elev - base_elev, 2)
    print(f"Derived base elevation:  {base_elev:.2f} m")
    print(f"Derived crest elevation: {crest_elev:.2f} m")
    print(f"Total relief (depth):    {total_depth:.2f} m")

    # Derive headline volume totals from the engineering report (data-driven,
    # not hardcoded), for the on-screen stats card.
    M3_TO_ACRE_FEET = 0.000810713194
    M3_TO_CUFT = 35.31466672148859
    total_frustum_m3 = float(df_report['Cumul_Frustum_Vol_m3'].max())
    total_endarea_m3 = float(df_report['Cumul_EndArea_Vol_m3'].max())
    variance_m3 = total_endarea_m3 - total_frustum_m3
    variance_pct = (variance_m3 / total_frustum_m3 * 100.0) if total_frustum_m3 else 0.0
    total_frustum_acft = total_frustum_m3 * M3_TO_ACRE_FEET
    total_frustum_cuft = total_frustum_m3 * M3_TO_CUFT
    total_endarea_acft = total_endarea_m3 * M3_TO_ACRE_FEET
    total_endarea_cuft = total_endarea_m3 * M3_TO_CUFT
    variance_cuft = variance_m3 * M3_TO_CUFT

    # Extract boundary. South data carries an explicit outer perimeter feature
    # (ELEVATION == 0.0). North data has no such feature, so use the base (lowest,
    # largest) cumulative footprint as the corridor outline instead.
    bnd_row = gdf_input[gdf_input['ELEVATION'] == 0.0] if 'ELEVATION' in gdf_input.columns else gdf_input.iloc[0:0]
    if len(bnd_row) > 0:
        bnd_geom = bnd_row.geometry.iloc[0]
    else:
        base_stage = gdf_cumul.sort_values('Z_HIGH').iloc[0]
        bnd_geom = base_stage.geometry.boundary
        print("  Boundary source: base cumulative footprint (no ELEVATION == 0.0 feature present)")
    bnd_geojson = mapping(bnd_geom)

    # Compute bounding box & center
    bounds = gdf_slices.total_bounds # [minx, miny, maxx, maxy]
    center_lon = (bounds[0] + bounds[2]) / 2.0
    center_lat = (bounds[1] + bounds[3]) / 2.0

    # Corridor extent in METERS (from the projected UTM slices) so camera framing
    # scales to each dataset instead of using offsets tuned for one region.
    slices_utm = gpd.read_file(slice_shp)  # native EPSG:32643 (meters)
    ub = slices_utm.total_bounds
    span_x_m = float(ub[2] - ub[0])
    span_y_m = float(ub[3] - ub[1])
    span_diag_m = float((span_x_m ** 2 + span_y_m ** 2) ** 0.5)
    print(f"Corridor Center: Lon = {center_lon:.6f}, Lat = {center_lat:.6f}")
    print(f"Corridor span: {span_x_m:.1f} m (E-W) x {span_y_m:.1f} m (N-S), diagonal {span_diag_m:.1f} m")

    # 1. Build Hollow Slice GeoJSON (Concentric difference rings with interior hollow voids)
    slices_hollow_features = []
    for idx, row in gdf_slices.iterrows():
        st_id = int(row['STAGE_ID'])
        z_low = float(row['Z_LOW'])
        z_high = float(row['Z_HIGH'])
        dh = float(row['DELTA_H'])
        area_m2 = float(row['AREA_M2'])
        vol_m3 = float(row['VOL_M3'])
        vol_cuft = float(row['VOL_CUFT'])
        cum_m3 = float(row['CUMUL_M3'])
        cum_cuft = float(row['CUM_CUFT'])

        depth_high = crest_elev - z_high
        depth_low = crest_elev - z_low
        depth_mean = (depth_high + depth_low) / 2.0

        # The top slice (z_high == crest) is the peak of the landform: there is
        # no layer above it. Its difference geometry carves the crest out as an
        # interior hole, which renders as an open/unpolygonized top. Fill it with
        # the solid cumulative footprint so the peak closes as a proper lid.
        hollow_geom = row.geometry
        if z_high >= crest_elev:
            cumul_row = gdf_cumul[gdf_cumul['STAGE_ID'] == st_id].iloc[0]
            c_geom = cumul_row.geometry
            if c_geom.geom_type == 'Polygon':
                hollow_geom = Polygon(c_geom.exterior)
            elif c_geom.geom_type == 'MultiPolygon':
                hollow_geom = MultiPolygon([Polygon(p.exterior) for p in c_geom.geoms])
            else:
                hollow_geom = c_geom

        feat = {
            "type": "Feature",
            "properties": {
                "stage_id": st_id,
                "z_low": z_low,
                "z_high": z_high,
                "delta_h": dh,
                "area_m2": area_m2,
                "area_ha": round(area_m2 / 10000.0, 4),
                "vol_m3": vol_m3,
                "vol_cuft": vol_cuft,
                "cum_m3": cum_m3,
                "cum_cuft": cum_cuft,
                "cum_acft": round(cum_m3 * 0.000810713, 2),
                "depth_mean_m": round(depth_mean, 2),
                "depth_range": f"{depth_high:.1f}m - {depth_low:.1f}m",
                "label": f"Layer {st_id}: {z_low:.1f}m - {z_high:.1f}m"
            },
            "geometry": mapping(hollow_geom)
        }
        slices_hollow_features.append(feat)

    slices_hollow_geojson = {
        "type": "FeatureCollection",
        "features": slices_hollow_features
    }

    # 2. Build Solid Embankment GeoJSON (Continuous solid stepped slabs + Crest Crown cap)
    slices_solid_features = []
    for idx, row in gdf_slices.iterrows():
        st_id = int(row['STAGE_ID'])
        z_low = float(row['Z_LOW'])
        z_high = float(row['Z_HIGH'])
        dh = float(row['DELTA_H'])
        area_m2 = float(row['AREA_M2'])
        vol_m3 = float(row['VOL_M3'])
        vol_cuft = float(row['VOL_CUFT'])
        cum_m3 = float(row['CUMUL_M3'])
        cum_cuft = float(row['CUM_CUFT'])

        depth_high = crest_elev - z_high
        depth_low = crest_elev - z_low
        depth_mean = (depth_high + depth_low) / 2.0

        cumul_row = gdf_cumul[gdf_cumul['STAGE_ID'] == st_id].iloc[0]
        c_geom = cumul_row.geometry
        if c_geom.geom_type == 'Polygon':
            solid_poly = Polygon(c_geom.exterior)
        elif c_geom.geom_type == 'MultiPolygon':
            solid_poly = MultiPolygon([Polygon(p.exterior) for p in c_geom.geoms])
        else:
            solid_poly = c_geom

        feat = {
            "type": "Feature",
            "properties": {
                "stage_id": st_id,
                "z_low": z_low,
                "z_high": z_high,
                "delta_h": dh,
                "area_m2": area_m2,
                "area_ha": round(area_m2 / 10000.0, 4),
                "vol_m3": vol_m3,
                "vol_cuft": vol_cuft,
                "cum_m3": cum_m3,
                "cum_cuft": cum_cuft,
                "cum_acft": round(cum_m3 * 0.000810713, 2),
                "depth_mean_m": round(depth_mean, 2),
                "depth_range": f"{depth_high:.1f}m - {depth_low:.1f}m",
                "label": f"Layer {st_id}: {z_low:.1f}m - {z_high:.1f}m"
            },
            "geometry": mapping(solid_poly)
        }
        slices_solid_features.append(feat)

    # NOTE: The 165.5 m crest is the peak of the landform. The top slice (Stage 17,
    # 165.0m -> 165.5m) already caps the model at the crest via its cumulative solid
    # footprint. Appending a separate zero-thickness "Crest Crown Plateau" here would
    # stack the crest footprint on top of itself (crest-on-crest), which is not
    # physically meaningful, so it is intentionally omitted.

    slices_solid_geojson = {
        "type": "FeatureCollection",
        "features": slices_solid_features
    }

    # Build Cumulative Stage GeoJSON data for water fill slider
    cumul_features = []
    for idx, row in gdf_cumul.iterrows():
        st_id = int(row['STAGE_ID'])
        z_high = float(row['Z_HIGH'])
        depth = float(row['DELTA_H'])
        area_m2 = float(row['AREA_M2'])
        cum_m3 = float(row['CUMUL_M3'])
        cum_cuft = float(row['CUM_CUFT'])

        c_geom = row.geometry
        if c_geom.geom_type == 'Polygon':
            c_solid = Polygon(c_geom.exterior)
        elif c_geom.geom_type == 'MultiPolygon':
            c_solid = MultiPolygon([Polygon(p.exterior) for p in c_geom.geoms])
        else:
            c_solid = c_geom

        feat = {
            "type": "Feature",
            "properties": {
                "stage_id": st_id,
                "elevation_m": z_high,
                "depth_from_base_m": depth,
                "area_m2": area_m2,
                "cum_m3": cum_m3,
                "cum_cuft": cum_cuft,
                "cum_acft": round(cum_m3 * 0.000810713, 2)
            },
            "geometry": mapping(c_solid)
        }
        cumul_features.append(feat)

    cumul_geojson = {
        "type": "FeatureCollection",
        "features": cumul_features
    }

    # HTML template with modern CesiumJS setup
    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{region_title} Area: 3D CesiumJS Pit & Frustum Volume Explorer</title>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, minimum-scale=1, user-scalable=no">
  
  <!-- CesiumJS CSS & JS from Official CDN -->
  <link href="https://cesium.com/downloads/cesiumjs/releases/1.119/Build/Cesium/Widgets/widgets.css" rel="stylesheet">
  <script src="https://cesium.com/downloads/cesiumjs/releases/1.119/Build/Cesium/Cesium.js"></script>

  <!-- Google Font & FontAwesome Icons -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">

  <style>
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    }}
    html, body, #cesiumContainer {{
      width: 100%;
      height: 100%;
      overflow: hidden;
      background-color: #0b0f19;
    }}

    /* Custom Floating Glassmorphism Panels */
    .glass-panel {{
      background: rgba(15, 23, 42, 0.82);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 12px;
      color: #f1f5f9;
      box-shadow: 0 10px 30px -5px rgba(0, 0, 0, 0.5);
      z-index: 999;
    }}

    /* Header Title Bar (Compact) */
    #headerPanel {{
      position: absolute;
      top: 14px;
      left: 14px;
      padding: 9px 13px;
      max-width: 320px;
    }}
    #headerPanel h1 {{
      font-size: 13.5px;
      font-weight: 700;
      letter-spacing: -0.01em;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 7px;
    }}
    #headerPanel h1 i {{
      color: #38bdf8;
      font-size: 12px;
    }}
    #headerPanel p {{
      font-size: 10px;
      color: #94a3b8;
      margin-top: 3px;
      line-height: 1.35;
    }}

    /* Floating Controls Panel (Right Side) */
    #controlsPanel {{
      position: absolute;
      top: 16px;
      right: 16px;
      width: 320px;
      padding: 18px;
      max-height: calc(100vh - 32px);
      overflow-y: auto;
    }}
    .control-group {{
      margin-bottom: 16px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding-bottom: 14px;
    }}
    .control-group:last-child {{
      border-bottom: none;
      margin-bottom: 0;
      padding-bottom: 0;
    }}
    .group-label {{
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #38bdf8;
      font-weight: 700;
      margin-bottom: 10px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}

    /* Sliders & Inputs */
    .slider-container {{
      margin: 8px 0;
    }}
    .slider-header {{
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      color: #cbd5e1;
      margin-bottom: 6px;
    }}
    .slider-val {{
      font-weight: 600;
      color: #38bdf8;
    }}
    input[type=range] {{
      width: 100%;
      height: 6px;
      background: #334155;
      border-radius: 3px;
      outline: none;
      -webkit-appearance: none;
      cursor: pointer;
    }}
    input[type=range]::-webkit-slider-thumb {{
      -webkit-appearance: none;
      appearance: none;
      width: 16px;
      height: 16px;
      border-radius: 50%;
      background: #38bdf8;
      cursor: pointer;
      box-shadow: 0 0 8px rgba(56, 189, 248, 0.7);
    }}

    /* Toggles */
    .toggle-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin: 8px 0;
      font-size: 12.5px;
      color: #e2e8f0;
      cursor: pointer;
    }}
    .toggle-row input[type=checkbox] {{
      cursor: pointer;
      width: 15px;
      height: 15px;
      accent-color: #38bdf8;
    }}

    /* View Buttons */
    .btn-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin-top: 6px;
    }}
    .btn {{
      background: #1e293b;
      border: 1px solid rgba(255, 255, 255, 0.1);
      color: #e2e8f0;
      padding: 7px 10px;
      border-radius: 6px;
      font-size: 11.5px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 5px;
    }}
    .btn:hover {{
      background: #334155;
      border-color: #38bdf8;
      color: #ffffff;
    }}

    /* Depth Color Legend (Bottom Left) */
    #legendPanel {{
      position: absolute;
      bottom: 24px;
      left: 16px;
      padding: 14px 18px;
      width: 320px;
    }}
    .legend-title {{
      font-size: 11.5px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .gradient-bar {{
      height: 12px;
      border-radius: 6px;
      margin: 8px 0 4px 0;
      box-shadow: inset 0 1px 2px rgba(0,0,0,0.4);
    }}
    .gradient-labels {{
      display: flex;
      justify-content: space-between;
      font-size: 10px;
      color: #94a3b8;
      font-weight: 600;
    }}

    /* Inspection HUD Card */
    #inspectHUD {{
      position: absolute;
      bottom: 24px;
      right: 16px;
      width: 340px;
      padding: 16px;
      display: none;
      animation: fadeIn 0.2s ease-in-out;
    }}
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(10px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .hud-title {{
      font-size: 13.5px;
      font-weight: 700;
      color: #38bdf8;
      margin-bottom: 8px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .hud-close {{
      cursor: pointer;
      color: #94a3b8;
      font-size: 14px;
    }}
    .hud-close:hover {{ color: #ffffff; }}
    .hud-table {{
      width: 100%;
      font-size: 11.5px;
      border-collapse: collapse;
      margin-top: 6px;
    }}
    .hud-table td {{
      padding: 3.5px 0;
      color: #cbd5e1;
    }}
    .hud-table td.val {{
      text-align: right;
      font-weight: 600;
      color: #ffffff;
    }}

    /* Floating Interactive Hover Tooltip */
    #mouseTooltip {{
      position: absolute;
      pointer-events: none;
      z-index: 10000;
      display: none;
      transform: translate(15px, 15px);
      background: rgba(15, 23, 42, 0.94);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      border: 1px solid rgba(56, 189, 248, 0.5);
      box-shadow: 0 12px 28px rgba(0, 0, 0, 0.65);
      border-radius: 8px;
      padding: 10px 14px;
      color: #ffffff;
      font-size: 11.5px;
      max-width: 280px;
    }}

    /* Stats Card (Left Side below Header - Compact) */
    #statsCard {{
      position: absolute;
      top: 78px;
      left: 14px;
      width: 320px;
      padding: 10px 12px;
    }}
    .stats-header {{
      font-size: 11px;
      font-weight: 700;
      color: #ffffff;
      margin-bottom: 7px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 1px solid rgba(255, 255, 255, 0.08);
      padding-bottom: 6px;
    }}
    .stats-header i {{ color: #38bdf8; }}
    .stat-box {{
      background: rgba(30, 41, 59, 0.7);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 6px;
      padding: 7px 10px;
      margin-bottom: 6px;
      transition: all 0.2s ease;
    }}
    .stat-box:last-child {{ margin-bottom: 0; }}
    .stat-box.primary {{
      border-left: 3px solid #38bdf8;
      background: rgba(56, 189, 248, 0.08);
    }}
    .stat-box.variance {{
      border-left: 3px solid #f59e0b;
      background: rgba(245, 158, 11, 0.08);
    }}
    .stat-title {{
      font-size: 9px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #94a3b8;
      font-weight: 600;
    }}
    .stat-number {{
      font-size: 13.5px;
      font-weight: 700;
      color: #ffffff;
      margin: 1px 0;
      display: flex;
      align-items: baseline;
      gap: 4px;
    }}
    .stat-number.delta {{ color: #fbbf24; }}
    .stat-unit {{ font-size: 11px; font-weight: 500; color: #38bdf8; }}
    .stat-pct {{ font-size: 11px; font-weight: 600; color: #fbbf24; }}
    .stat-sub {{
      font-size: 9.5px;
      color: #cbd5e1;
    }}
  </style>
</head>
<body>

  <div id="cesiumContainer"></div>

  <!-- Floating Interactive Hover Tooltip -->
  <div id="mouseTooltip">
    <div id="tooltipTitle" style="font-weight:700; color:#38bdf8; font-size:12px; margin-bottom:4px;"></div>
    <div id="tooltipContent" style="line-height:1.45; color:#cbd5e1;"></div>
  </div>

  <!-- Header Panel (Compact) -->
  <div id="headerPanel" class="glass-panel">
    <h1><i class="fa-solid fa-cube"></i> {region_title} Pit 3D Cesium Explorer</h1>
    <p>Solid embankment volumetric model from base {base_elev:.1f}m to crest {crest_elev:.1f}m.</p>
  </div>

  <!-- Engineering Volume Stats Panel -->
  <div id="statsCard" class="glass-panel">
    <div class="stats-header">
      <span><i class="fa-solid fa-chart-pie"></i> Volumetric Analysis Results</span>
      <span style="font-size:10px; font-weight:700; color:#38bdf8; background:rgba(56,189,248,0.12); padding:2px 7px; border-radius:4px; border:1px solid rgba(56,189,248,0.3);">Verified</span>
    </div>
    
    <div class="stat-box primary">
      <div class="stat-title">Total Prismoidal Frustum Volume</div>
      <div class="stat-number">{total_frustum_m3:,.2f} <span class="stat-unit">m³</span></div>
      <div class="stat-sub">{total_frustum_acft:.2f} acre-feet &nbsp;|&nbsp; <b>{total_frustum_cuft:,.2f} ft³</b></div>
    </div>

    <div class="stat-box">
      <div class="stat-title">Total Average End-Area Volume</div>
      <div class="stat-number">{total_endarea_m3:,.2f} <span class="stat-unit">m³</span></div>
      <div class="stat-sub">{total_endarea_acft:.2f} acre-feet &nbsp;|&nbsp; <b>{total_endarea_cuft:,.2f} ft³</b></div>
    </div>

    <div class="stat-box variance">
      <div class="stat-title">Volume Variance (End-Area vs Frustum)</div>
      <div class="stat-number delta">{variance_m3:+,.2f} <span class="stat-unit">m³</span> <span class="stat-pct">({variance_pct:+.2f}%)</span></div>
      <div class="stat-sub">{variance_cuft:+,.2f} ft³ &nbsp;|&nbsp; Convexity Overestimate</div>
    </div>
  </div>

  <!-- Controls Panel -->
  <div id="controlsPanel" class="glass-panel">
    
    <!-- 0. Base Map Selector -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-earth-americas"></i> Satellite Base Map</span>
      </div>
      <div class="btn-grid" style="grid-template-columns: 1fr;">
        <select id="basemapSelect" style="background:#1e293b; color:#e2e8f0; padding:8px; border-radius:6px; border:1px solid rgba(255,255,255,0.1); width:100%; font-size:12px;">
          <option value="satellite" selected>ESRI World Imagery (High-Res Satellite)</option>
          <option value="hybrid">ESRI Satellite + Labels (Hybrid)</option>
          <option value="dark">Dark Canvas (CartoDB Dark Matter)</option>
          <option value="osm">OpenStreetMap Standard</option>
        </select>
      </div>
    </div>

    <!-- 0b. Ground Contact Mode -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-arrows-down-to-line"></i> Ground Contact Mode</span>
      </div>
      <div class="btn-grid" style="grid-template-columns: 1fr;">
        <select id="groundModeSelect" style="background:#1e293b; color:#e2e8f0; padding:8px; border-radius:6px; border:1px solid rgba(255,255,255,0.1); width:100%; font-size:12px;">
          <option value="ground" selected>Anchored to Ground (0m - Touches Satellite Imagery)</option>
          <option value="absolute">Absolute Survey MSL ({base_elev:.1f}m above Ellipsoid)</option>
        </select>
      </div>
      <div style="font-size: 10.5px; color: #94a3b8; margin-top: 4px;">
        "Anchored to Ground" sets the base ({base_elev:.1f}m) to 0m elevation so the pit sits directly on the satellite terrain.
      </div>
    </div>

    <!-- 0c. Model Geometry Mode -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-shapes"></i> Model Geometry Mode</span>
      </div>
      <div class="btn-grid" style="grid-template-columns: 1fr;">
        <select id="geometryModeSelect" style="background:#1e293b; color:#e2e8f0; padding:8px; border-radius:6px; border:1px solid rgba(255,255,255,0.1); width:100%; font-size:12px;">
          <option value="hollow" {'selected' if default_geometry_mode == 'hollow' else ''}>Hollow Slices (Excavation Difference Rings)</option>
          <option value="solid" {'selected' if default_geometry_mode == 'solid' else ''}>Solid Embankment (Continuous Mass)</option>
        </select>
      </div>
      <div style="font-size: 10.5px; color: #94a3b8; margin-top: 4px;">
        Toggle between individual hollow slice rings (hollow inside) or continuous solid embankment mass.
      </div>
    </div>

    <!-- 1. Color Palette Selector -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-palette"></i> Depth Coloring Mode</span>
      </div>
      <div class="btn-grid" style="grid-template-columns: 1fr;">
        <select id="colorModeSelect" style="background:#1e293b; color:#e2e8f0; padding:8px; border-radius:6px; border:1px solid rgba(255,255,255,0.1); width:100%; font-size:12px;">
          <option value="pit_depth" selected>Pit Depth Gradient (Indigo Base → Red Crest)</option>
          <option value="bathymetry">Bathymetric Deep (Navy → Aqua → Coral)</option>
          <option value="magma">Magma (Dark Violet → Orange → Yellow)</option>
          <option value="viridis">Viridis (Purple → Teal → Lime)</option>
          <option value="rainbow">Spectral Rainbow (Blue → Green → Red)</option>
        </select>
      </div>
    </div>

    <!-- 2. Vertical Exaggeration -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-up-down"></i> 3D Vertical Relief</span>
      </div>
      <div class="slider-container">
        <div class="slider-header">
          <span>Vertical Exaggeration:</span>
          <span class="slider-val" id="exagVal">0.0x</span>
        </div>
        <input type="range" id="exagSlider" min="0" max="15" step="0.5" value="0">
      </div>
      <div style="font-size: 10.5px; color: #94a3b8; margin-top: 4px;">
        Exaggerates elevation & layer depth for 3D inspection (set to 0 for flat surface view).
      </div>
    </div>

    <!-- 3. Dynamic Water / Material Fill Simulator -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-water"></i> Pit Fill Simulator</span>
        <span class="status-badge" id="fillPctBadge">0% Full</span>
      </div>
      <div class="slider-container">
        <div class="slider-header">
          <span>Fill Stage Elevation:</span>
          <span class="slider-val" id="stageElevVal">{base_elev:.1f} m (Empty)</span>
        </div>
        <input type="range" id="stageSlider" min="{base_elev}" max="{crest_elev}" step="0.5" value="{base_elev}">
      </div>
      <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px;">
        Filled Volume: <b id="fillVolVal" style="color:#38bdf8;">0 m³ (0 ft³)</b>
      </div>
    </div>

    <!-- 4. Layers Visibility -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-layer-group"></i> Layer Display</span>
      </div>
      <label class="toggle-row">
        <span>Show 3D Depth Slices</span>
        <input type="checkbox" id="toggleSlices" checked>
      </label>
      <label class="toggle-row">
        <span>Show Pit Water Surface</span>
        <input type="checkbox" id="toggleWater" checked>
      </label>
      <label class="toggle-row">
        <span>Show Outer Perimeter Wall</span>
        <input type="checkbox" id="toggleBoundary">
      </label>
      <label class="toggle-row">
        <span>Show Crest Crown Rim ({crest_elev:.1f}m)</span>
        <input type="checkbox" id="toggleCrest">
      </label>
    </div>

    <!-- 5. Camera Presets -->
    <div class="control-group">
      <div class="group-label">
        <span><i class="fa-solid fa-camera"></i> Camera View Angles</span>
      </div>
      <div class="btn-grid">
        <button class="btn" id="btnIsoView"><i class="fa-solid fa-compass"></i> Oblique 3D</button>
        <button class="btn" id="btnSideView"><i class="fa-solid fa-arrows-left-right"></i> Side Profile</button>
        <button class="btn" id="btnFrontView"><i class="fa-solid fa-arrow-up"></i> North Toe</button>
        <button class="btn" id="btnTopView"><i class="fa-solid fa-map"></i> Top-Down</button>
      </div>
    </div>

  </div>

  <!-- Depth Color Legend Panel -->
  <div id="legendPanel" class="glass-panel">
    <div class="legend-title">
      <span><i class="fa-solid fa-chart-simple"></i> Depth from Crest (m)</span>
      <span style="font-size:10px; color:#38bdf8;">Total Depth: {total_depth:.1f}m</span>
    </div>
    <div class="gradient-bar" id="legendGradient"></div>
    <div class="gradient-labels">
      <span>0.0 m (Crest)</span>
      <span>{total_depth/3.0:.1f} m</span>
      <span>{2.0*total_depth/3.0:.1f} m</span>
      <span>{total_depth:.1f} m (Deepest Base)</span>
    </div>
  </div>

  <!-- Click Inspection HUD -->
  <div id="inspectHUD" class="glass-panel">
    <div class="hud-title">
      <span id="hudLayerName">Layer Details</span>
      <i class="fa-solid fa-xmark hud-close" id="closeHUD"></i>
    </div>
    <table class="hud-table">
      <tr><td>Elevation Interval:</td><td class="val" id="hudElev">-</td></tr>
      <tr><td>Depth from Crest:</td><td class="val" id="hudDepth">-</td></tr>
      <tr><td>Layer Area:</td><td class="val" id="hudArea">-</td></tr>
      <tr><td>Frustum Volume:</td><td class="val" id="hudVol">-</td></tr>
      <tr><td>Volume in Cu Ft:</td><td class="val" id="hudVolCuFt">-</td></tr>
      <tr><td>Cumulative Volume:</td><td class="val" id="hudCumVol">-</td></tr>
      <tr><td>Cumulative Cu Ft:</td><td class="val" id="hudCumCuFt">-</td></tr>
      <tr><td>Acre-Feet:</td><td class="val" id="hudAcFt">-</td></tr>
    </table>
  </div>

  <!-- Embedded Geospatial Data -->
  <script>
    const SLICES_HOLLOW_GEOJSON = {json.dumps(slices_hollow_geojson)};
    const SLICES_SOLID_GEOJSON = {json.dumps(slices_solid_geojson)};
    const CUMUL_GEOJSON = {json.dumps(cumul_geojson)};
    const BOUNDARY_GEOJSON = {json.dumps(bnd_geojson)};
    const CENTER_LON = {center_lon};
    const CENTER_LAT = {center_lat};
    const DEFAULT_GEOMETRY_MODE = "{default_geometry_mode}";
    // Base (toe), crest (peak) and relief derived from the data, not hardcoded.
    const BASE_ELEV = {base_elev};
    const CREST_ELEV = {crest_elev};
    const TOTAL_DEPTH = {total_depth};
    const TOTAL_CAPACITY_M3 = {total_frustum_m3};
    // Corridor extent (meters) for data-driven camera framing.
    const SPAN_X_M = {span_x_m};
    const SPAN_Y_M = {span_y_m};
    const SPAN_DIAG_M = {span_diag_m};
  </script>

  <!-- Application Logic -->
  <script>
    // Initialize Cesium Viewer
    const viewer = new Cesium.Viewer('cesiumContainer', {{
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      infoBox: false,
      sceneModePicker: false,
      selectionIndicator: false,
      navigationHelpButton: false,
      navigationInstructionsInitiallyVisible: false,
      timeline: false,
      animation: false,
      baseLayer: new Cesium.ImageryLayer(new Cesium.UrlTemplateImageryProvider({{
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
        maximumLevel: 19
      }}))
    }});

    function setBasemap(type) {{
      viewer.imageryLayers.removeAll();
      if (type === 'satellite') {{
        viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({{
          url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
          maximumLevel: 19
        }}));
      }} else if (type === 'hybrid') {{
        viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({{
          url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
          maximumLevel: 19
        }}));
        viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({{
          url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}',
          maximumLevel: 19
        }}));
      }} else if (type === 'dark') {{
        viewer.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({{
          url: 'https://a.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}.png',
          maximumLevel: 19
        }}));
      }} else if (type === 'osm') {{
        viewer.imageryLayers.addImageryProvider(new Cesium.OpenStreetMapImageryProvider({{
          url: 'https://tile.openstreetmap.org/'
        }}));
      }}
    }}

    viewer.scene.globe.depthTestAgainstTerrain = false;
    viewer.scene.globe.enableLighting = false;

    // Ensure full free-orbit interaction: rotate, tilt, zoom, pan and look are
    // all enabled so the model can be viewed from any angle (left-drag orbit,
    // right-drag / middle-drag tilt, wheel zoom).
    const camCtrl = viewer.scene.screenSpaceCameraController;
    camCtrl.enableRotate = true;
    camCtrl.enableTranslate = true;
    camCtrl.enableZoom = true;
    camCtrl.enableTilt = true;
    camCtrl.enableLook = true;
    // Let the camera dip below the base plane and orbit low around the model.
    camCtrl.minimumZoomDistance = 1.0;
    camCtrl.constrainedAxis = undefined;

    // References
    let verticalExaggeration = 0.0;
    let groundAnchorMode = 'ground'; // 'ground' (0m datum, touches ground) or 'absolute' (157m MSL)
    let currentColorMode = 'pit_depth';
    let currentGeometryMode = DEFAULT_GEOMETRY_MODE; // 'hollow' or 'solid'

    function getBaseAltitude() {{
      return groundAnchorMode === 'ground' ? 0.0 : BASE_ELEV;
    }}

    // Entities collections
    const sliceEntities = [];
    let waterEntity = null;
    let boundaryEntity = null;
    let crestEntity = null;

    // Color Maps Definition
    function getColorForDepth(depth, minDepth, maxDepth, mode) {{
      const t = Math.max(0, Math.min(1, (depth - minDepth) / (maxDepth - minDepth)));
      
      if (mode === 'pit_depth') {{
        // Deep Indigo/Navy (base) -> Cyan -> Green -> Yellow -> Red/Coral (crest)
        // t = 0 (crest, depth 0m), t = 1 (base, depth 8.5m)
        if (t > 0.8) return Cesium.Color.fromCssColorString('#03045e'); // Deepest
        if (t > 0.6) return Cesium.Color.fromCssColorString('#0077b6');
        if (t > 0.45) return Cesium.Color.fromCssColorString('#00b4d8');
        if (t > 0.3) return Cesium.Color.fromCssColorString('#52b788');
        if (t > 0.15) return Cesium.Color.fromCssColorString('#ffd166');
        return Cesium.Color.fromCssColorString('#e63946'); // Crest
      }} else if (mode === 'bathymetry') {{
        if (t > 0.75) return Cesium.Color.fromCssColorString('#0c2461');
        if (t > 0.5) return Cesium.Color.fromCssColorString('#1e3799');
        if (t > 0.3) return Cesium.Color.fromCssColorString('#4a69bd');
        if (t > 0.15) return Cesium.Color.fromCssColorString('#60a3bc');
        return Cesium.Color.fromCssColorString('#f8a5c2');
      }} else if (mode === 'magma') {{
        if (t > 0.8) return Cesium.Color.fromCssColorString('#000004');
        if (t > 0.6) return Cesium.Color.fromCssColorString('#3b0f70');
        if (t > 0.4) return Cesium.Color.fromCssColorString('#8c2981');
        if (t > 0.2) return Cesium.Color.fromCssColorString('#de4968');
        return Cesium.Color.fromCssColorString('#fcfdbf');
      }} else if (mode === 'viridis') {{
        if (t > 0.8) return Cesium.Color.fromCssColorString('#440154');
        if (t > 0.6) return Cesium.Color.fromCssColorString('#3b528b');
        if (t > 0.4) return Cesium.Color.fromCssColorString('#21918c');
        if (t > 0.2) return Cesium.Color.fromCssColorString('#5ec962');
        return Cesium.Color.fromCssColorString('#fde725');
      }} else {{ // Rainbow
        if (t > 0.8) return Cesium.Color.fromCssColorString('#2b5c8f');
        if (t > 0.6) return Cesium.Color.fromCssColorString('#2a9d8f');
        if (t > 0.4) return Cesium.Color.fromCssColorString('#e9c46a');
        if (t > 0.2) return Cesium.Color.fromCssColorString('#f4a261');
        return Cesium.Color.fromCssColorString('#e76f51');
      }}
    }}

    function updateLegendBar() {{
      const bar = document.getElementById('legendGradient');
      if (currentColorMode === 'pit_depth') {{
        bar.style.background = 'linear-gradient(to right, #e63946, #ffd166, #52b788, #00b4d8, #0077b6, #03045e)';
      }} else if (currentColorMode === 'bathymetry') {{
        bar.style.background = 'linear-gradient(to right, #f8a5c2, #60a3bc, #4a69bd, #1e3799, #0c2461)';
      }} else if (currentColorMode === 'magma') {{
        bar.style.background = 'linear-gradient(to right, #fcfdbf, #de4968, #8c2981, #3b0f70, #000004)';
      }} else if (currentColorMode === 'viridis') {{
        bar.style.background = 'linear-gradient(to right, #fde725, #5ec962, #21918c, #3b528b, #440154)';
      }} else {{
        bar.style.background = 'linear-gradient(to right, #e76f51, #f4a261, #e9c46a, #2a9d8f, #2b5c8f)';
      }}
    }}

    // Parse coordinates into Cartesian3 arrays
    function parsePolygonCoordinates(coords) {{
      const flat = [];
      for (let i = 0; i < coords.length; i++) {{
        flat.push(coords[i][0]);
        flat.push(coords[i][1]);
      }}
      return Cesium.Cartesian3.fromDegreesArray(flat);
    }}

    // Render Slices (Supports Hollow Difference Rings & Solid Embankment Mass)
    function buildSliceEntities() {{
      // Clear existing
      sliceEntities.forEach(e => viewer.entities.remove(e));
      sliceEntities.length = 0;

      const baseAlt = getBaseAltitude();
      const dataset = currentGeometryMode === 'solid' ? SLICES_SOLID_GEOJSON : SLICES_HOLLOW_GEOJSON;

      dataset.features.forEach(feat => {{
        const props = feat.properties;
        const geom = feat.geometry;
        const zLow = props.z_low;
        const zHigh = props.z_high;
        const depth = props.depth_mean_m;

        // Apply vertical relief anchored to base (BASE_ELEV -> baseAlt)
        const relLow = zLow - BASE_ELEV;
        const relHigh = zHigh - BASE_ELEV;

        let elevLow, elevHigh;
        if (verticalExaggeration > 0) {{
          elevLow = baseAlt + relLow * verticalExaggeration;
          elevHigh = baseAlt + (relHigh > relLow ? relHigh : relLow + 0.15) * verticalExaggeration;
        }} else {{
          // 0 Vertical Relief (Flat Ground): micro vertical offset to enforce exact top-down depth layering without z-fighting
          elevLow = baseAlt + relLow * 0.01;
          elevHigh = elevLow;
        }}

        const color = getColorForDepth(depth, 0.0, TOTAL_DEPTH, currentColorMode);
        const polygons = geom.type === 'Polygon' ? [geom.coordinates] : geom.coordinates;

        polygons.forEach((polyCoords) => {{
          const exterior = polyCoords[0];
          const holes = polyCoords.slice(1);

          // If in hollow mode, keep holes; if in solid mode, fill solid
          const hierarchy = (currentGeometryMode === 'hollow' && holes.length > 0)
            ? new Cesium.PolygonHierarchy(
                parsePolygonCoordinates(exterior),
                holes.map(h => new Cesium.PolygonHierarchy(parsePolygonCoordinates(h)))
              )
            : new Cesium.PolygonHierarchy(parsePolygonCoordinates(exterior));

          const entity = viewer.entities.add({{
            name: props.label,
            polygon: {{
              hierarchy: hierarchy,
              height: elevLow,
              extrudedHeight: (verticalExaggeration > 0 && elevHigh > elevLow ? elevHigh : undefined),
              material: color.withAlpha(0.92),
              outline: true,
              outlineColor: Cesium.Color.BLACK.withAlpha(0.7),
              outlineWidth: 1.5
            }},
            properties: props
          }});
          sliceEntities.push(entity);
        }});
      }});
    }}

    // Outer Boundary Wall
    function buildBoundaryEntity() {{
      if (boundaryEntity) viewer.entities.remove(boundaryEntity);

      const bndCoords = BOUNDARY_GEOJSON.coordinates;
      const flat = [];
      for (let pt of bndCoords) {{
        flat.push(pt[0]);
        flat.push(pt[1]);
      }}

      const baseAlt = getBaseAltitude();
      const topWall = baseAlt + (CREST_ELEV - BASE_ELEV) * verticalExaggeration + 1.0;

      boundaryEntity = viewer.entities.add({{
        name: "Corridor Boundary Wall",
        show: document.getElementById('toggleBoundary').checked,
        corridor: {{
          positions: Cesium.Cartesian3.fromDegreesArray(flat),
          width: 3.5,
          height: baseAlt,
          extrudedHeight: topWall,
          material: Cesium.Color.fromCssColorString('#64748b').withAlpha(0.35),
          outline: true,
          outlineColor: Cesium.Color.WHITE.withAlpha(0.5)
        }}
      }});
    }}

    // Crest Crown Rim
    function buildCrestEntity() {{
      if (crestEntity) viewer.entities.remove(crestEntity);

      // Find highest cumulative polygon (crest elevation)
      let topFeat = CUMUL_GEOJSON.features.find(f => f.properties.elevation_m === CREST_ELEV);
      if (!topFeat) {{
        // Fallback: pick the feature with the maximum elevation.
        topFeat = CUMUL_GEOJSON.features.reduce((a, b) =>
          (b.properties.elevation_m > a.properties.elevation_m ? b : a));
      }}
      if (!topFeat) return;

      const coords = topFeat.geometry.coordinates[0];
      const baseAlt = getBaseAltitude();
      const topElev = baseAlt + (CREST_ELEV - BASE_ELEV) * verticalExaggeration;

      crestEntity = viewer.entities.add({{
        name: `Crest Crown (${{CREST_ELEV.toFixed(1)}}m)`,
        show: document.getElementById('toggleCrest').checked,
        polyline: {{
          positions: Cesium.Cartesian3.fromDegreesArrayHeights(coords.map(c => [c[0], c[1], topElev + 0.5]).flat()),
          width: 4,
          material: new Cesium.PolylineGlowMaterialProperty({{
            glowPower: 0.25,
            color: Cesium.Color.RED
          }})
        }}
      }});
    }}

    // Dynamic Pit Water Fill Simulation
    function updateWaterFill(targetElev) {{
      if (waterEntity) {{
        viewer.entities.remove(waterEntity);
        waterEntity = null;
      }}

      if (targetElev <= BASE_ELEV) {{
        document.getElementById('stageElevVal').textContent = `${{BASE_ELEV.toFixed(1)}} m (Empty Base)`;
        document.getElementById('fillPctBadge').textContent = "0% Full";
        document.getElementById('fillVolVal').textContent = "0 m³ (0 ft³)";
        return;
      }}

      // Find closest stage feature in cumulative dataset
      const stageFeat = CUMUL_GEOJSON.features.reduce((prev, curr) => {{
        return Math.abs(curr.properties.elevation_m - targetElev) < Math.abs(prev.properties.elevation_m - targetElev) ? curr : prev;
      }});

      const props = stageFeat.properties;
      const actualElev = props.elevation_m;
      // Total capacity = maximum cumulative volume across all stages (data-driven).
      const totalCapacity = CUMUL_GEOJSON.features.reduce((m, f) => Math.max(m, f.properties.cum_m3), 0) || 1;
      const pct = Math.min(100, Math.round((props.cum_m3 / totalCapacity) * 100));

      document.getElementById('stageElevVal').textContent = `${{actualElev.toFixed(1)}} m (Depth: ${{props.depth_from_base_m.toFixed(1)}}m)`;
      document.getElementById('fillPctBadge').textContent = `${{pct}}% Full`;
      document.getElementById('fillVolVal').textContent = `${{props.cum_m3.toLocaleString()}} m³ (${{props.cum_cuft.toLocaleString()}} ft³)`;

      if (!document.getElementById('toggleWater').checked) return;

      const baseAlt = getBaseAltitude();
      const waterElev = baseAlt + (actualElev - BASE_ELEV) * verticalExaggeration;
      const coords = stageFeat.geometry.type === 'Polygon' ? [stageFeat.geometry.coordinates] : stageFeat.geometry.coordinates;

      const entities = [];
      coords.forEach(polyCoords => {{
        const exterior = polyCoords[0];
        const hierarchy = new Cesium.PolygonHierarchy(parsePolygonCoordinates(exterior));

        waterEntity = viewer.entities.add({{
          name: `Water Surface (${{actualElev.toFixed(1)}}m)`,
          polygon: {{
            hierarchy: hierarchy,
            height: baseAlt,
            extrudedHeight: (verticalExaggeration > 0 && waterElev > baseAlt ? waterElev : undefined),
            material: Cesium.Color.fromCssColorString('#0ea5e9').withAlpha(0.6),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString('#38bdf8')
          }}
        }});
      }});
    }}

    // Camera Views — all framing is derived from the corridor's real extent
    // (SPAN_*_M) so any dataset (small south corridor or large north corridor)
    // is fit on screen without manual per-region offsets.
    const METERS_PER_DEG_LAT = 111320.0;
    function metersToLat(m) {{ return m / METERS_PER_DEG_LAT; }}
    function metersToLon(m) {{
      return m / (METERS_PER_DEG_LAT * Math.cos(CENTER_LAT * Math.PI / 180.0));
    }}

    function setCameraView(preset, duration) {{
      const baseAlt = getBaseAltitude();
      // Viewing distance scales with the corridor diagonal; the 0.9 factor and
      // pitch keep the whole footprint comfortably inside the viewport.
      const reach = Math.max(SPAN_DIAG_M * 0.9, 150.0);
      const dur = (duration === undefined) ? 1.2 : duration;

      if (preset === 'iso') {{
        // Oblique 3D: pull back to the south and up.
        viewer.camera.flyTo({{
          destination: Cesium.Cartesian3.fromDegrees(
            CENTER_LON, CENTER_LAT - metersToLat(reach * 0.7), baseAlt + reach * 0.75),
          orientation: {{
            heading: Cesium.Math.toRadians(0.0),
            pitch: Cesium.Math.toRadians(-35.0),
            roll: 0.0
          }},
          duration: dur
        }});
      }} else if (preset === 'side') {{
        viewer.camera.flyTo({{
          destination: Cesium.Cartesian3.fromDegrees(
            CENTER_LON - metersToLon(reach * 0.8), CENTER_LAT, baseAlt + reach * 0.5),
          orientation: {{
            heading: Cesium.Math.toRadians(90.0),
            pitch: Cesium.Math.toRadians(-22.0),
            roll: 0.0
          }},
          duration: dur
        }});
      }} else if (preset === 'front') {{
        viewer.camera.flyTo({{
          destination: Cesium.Cartesian3.fromDegrees(
            CENTER_LON, CENTER_LAT - metersToLat(reach * 0.6), baseAlt + reach * 0.4),
          orientation: {{
            heading: Cesium.Math.toRadians(0.0),
            pitch: Cesium.Math.toRadians(-18.0),
            roll: 0.0
          }},
          duration: dur
        }});
      }} else if (preset === 'top') {{
        viewer.camera.flyTo({{
          destination: Cesium.Cartesian3.fromDegrees(CENTER_LON, CENTER_LAT, baseAlt + reach * 1.4),
          orientation: {{
            heading: Cesium.Math.toRadians(0.0),
            pitch: Cesium.Math.toRadians(-90.0),
            roll: 0.0
          }},
          duration: dur
        }});
      }}
    }}

    // Robustly frame the actual geometry on screen. flyTo on the entities uses
    // their real bounding sphere, so the data is guaranteed to be in view; we
    // then nudge to the oblique preset for a pleasant default angle.
    function frameInitialView() {{
      const target = (sliceEntities && sliceEntities.length)
        ? sliceEntities
        : viewer.entities;
      viewer.flyTo(target, {{ duration: 0.0 }}).then(() => {{
        setCameraView('iso', 1.0);
      }}).otherwise(() => {{
        setCameraView('iso', 1.0);
      }});
    }}

    // Click to Inspect Entity
    const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(function(movement) {{
      const pickedObject = viewer.scene.pick(movement.position);
      if (Cesium.defined(pickedObject) && pickedObject.id && pickedObject.id.properties) {{
        const props = pickedObject.id.properties;
        const hud = document.getElementById('inspectHUD');
        
        document.getElementById('hudLayerName').textContent = props.label ? props.label.getValue() : pickedObject.id.name;
        document.getElementById('hudElev').textContent = `${{props.z_low.getValue().toFixed(1)}} m - ${{props.z_high.getValue().toFixed(1)}} m`;
        document.getElementById('hudDepth').textContent = `${{props.depth_range.getValue()}} (${{props.depth_mean_m.getValue().toFixed(1)}}m mean)`;
        document.getElementById('hudArea').textContent = `${{props.area_m2.getValue().toLocaleString()}} m² (${{props.area_ha.getValue().toFixed(3)}} ha)`;
        document.getElementById('hudVol').textContent = `${{props.vol_m3.getValue().toLocaleString()}} m³`;
        document.getElementById('hudVolCuFt').textContent = `${{props.vol_cuft.getValue().toLocaleString()}} ft³`;
        document.getElementById('hudCumVol').textContent = `${{props.cum_m3.getValue().toLocaleString()}} m³`;
        document.getElementById('hudCumCuFt').textContent = `${{props.cum_cuft.getValue().toLocaleString()}} ft³`;
        document.getElementById('hudAcFt').textContent = `${{props.cum_acft.getValue().toFixed(1)}} ac-ft`;

        hud.style.display = 'block';
      }}
    }}, Cesium.ScreenSpaceEventType.LEFT_CLICK);

    document.getElementById('closeHUD').onclick = () => {{
      document.getElementById('inspectHUD').style.display = 'none';
    }};

    // Interactive Mouse Hover Tooltip & Outline Highlight
    const tooltip = document.getElementById('mouseTooltip');
    const tooltipTitle = document.getElementById('tooltipTitle');
    const tooltipContent = document.getElementById('tooltipContent');
    let highlightedEntity = null;
    let originalOutlineColor = null;
    let originalOutlineWidth = null;

    const hoverHandler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
    hoverHandler.setInputAction(function(movement) {{
      const pickedObject = viewer.scene.pick(movement.endPosition);
      if (Cesium.defined(pickedObject) && pickedObject.id && pickedObject.id.properties && pickedObject.id.properties.stage_id) {{
        const entity = pickedObject.id;
        const props = entity.properties;

        // Visual outline highlight
        if (highlightedEntity !== entity) {{
          if (highlightedEntity && highlightedEntity.polygon) {{
            highlightedEntity.polygon.outlineColor = originalOutlineColor;
            highlightedEntity.polygon.outlineWidth = originalOutlineWidth;
          }}
          highlightedEntity = entity;
          if (entity.polygon) {{
            originalOutlineColor = entity.polygon.outlineColor;
            originalOutlineWidth = entity.polygon.outlineWidth;
            entity.polygon.outlineColor = Cesium.Color.fromCssColorString('#38bdf8');
            entity.polygon.outlineWidth = 3.0;
          }}
        }}

        const layerName = props.label ? props.label.getValue() : entity.name;
        const zLow = props.z_low.getValue().toFixed(1);
        const zHigh = props.z_high.getValue().toFixed(1);
        const depth = props.depth_range.getValue();
        const volM3 = props.vol_m3.getValue().toLocaleString();
        const volCuFt = props.vol_cuft.getValue().toLocaleString();
        const cumM3 = props.cum_m3.getValue().toLocaleString();
        const pctTotal = ((props.cum_m3.getValue() / TOTAL_CAPACITY_M3) * 100).toFixed(1);
        const areaM2 = props.area_m2.getValue().toLocaleString();

        tooltipTitle.innerHTML = `<i class="fa-solid fa-layer-group"></i> ${{layerName}}`;
        tooltipContent.innerHTML = `
          <div style="margin-bottom:3px;"><b>Elevation:</b> ${{zLow}}m – ${{zHigh}}m &nbsp;|&nbsp; <b>Depth:</b> ${{depth}}</div>
          <div style="margin-bottom:3px;"><b>Slice Volume:</b> <span style="color:#38bdf8; font-weight:600;">${{volM3}} m³</span> (${{volCuFt}} ft³)</div>
          <div style="margin-bottom:3px;"><b>Cumulative:</b> ${{cumM3}} m³ (${{pctTotal}}% of Total)</div>
          <div><b>Slice Area:</b> ${{areaM2}} m²</div>
        `;

        tooltip.style.left = (movement.endPosition.x + 12) + 'px';
        tooltip.style.top = (movement.endPosition.y + 12) + 'px';
        tooltip.style.display = 'block';
        viewer.canvas.style.cursor = 'pointer';
      }} else {{
        if (highlightedEntity && highlightedEntity.polygon) {{
          highlightedEntity.polygon.outlineColor = originalOutlineColor;
          highlightedEntity.polygon.outlineWidth = originalOutlineWidth;
          highlightedEntity = null;
        }}
        tooltip.style.display = 'none';
        viewer.canvas.style.cursor = 'default';
      }}
    }}, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

    // Event Listeners
    document.getElementById('basemapSelect').onchange = (e) => {{
      setBasemap(e.target.value);
    }};

    document.getElementById('groundModeSelect').onchange = (e) => {{
      groundAnchorMode = e.target.value;
      buildSliceEntities();
      buildBoundaryEntity();
      buildCrestEntity();
      const currentFill = parseFloat(document.getElementById('stageSlider').value);
      updateWaterFill(currentFill);
      setCameraView('iso');
    }};

    document.getElementById('geometryModeSelect').onchange = (e) => {{
      currentGeometryMode = e.target.value;
      buildSliceEntities();
    }};

    document.getElementById('colorModeSelect').onchange = (e) => {{
      currentColorMode = e.target.value;
      updateLegendBar();
      buildSliceEntities();
    }};

    document.getElementById('exagSlider').oninput = (e) => {{
      verticalExaggeration = parseFloat(e.target.value);
      document.getElementById('exagVal').textContent = `${{verticalExaggeration.toFixed(1)}}x`;
      buildSliceEntities();
      buildBoundaryEntity();
      buildCrestEntity();
      const currentFill = parseFloat(document.getElementById('stageSlider').value);
      updateWaterFill(currentFill);
    }};

    document.getElementById('stageSlider').oninput = (e) => {{
      updateWaterFill(parseFloat(e.target.value));
    }};

    document.getElementById('toggleSlices').onchange = (e) => {{
      sliceEntities.forEach(ent => ent.show = e.target.checked);
    }};

    document.getElementById('toggleWater').onchange = (e) => {{
      if (waterEntity) waterEntity.show = e.target.checked;
    }};

    document.getElementById('toggleBoundary').onchange = (e) => {{
      if (boundaryEntity) boundaryEntity.show = e.target.checked;
    }};

    document.getElementById('toggleCrest').onchange = (e) => {{
      if (crestEntity) crestEntity.show = e.target.checked;
    }};

    document.getElementById('btnIsoView').onclick = () => setCameraView('iso');
    document.getElementById('btnSideView').onclick = () => setCameraView('side');
    document.getElementById('btnFrontView').onclick = () => setCameraView('front');
    document.getElementById('btnTopView').onclick = () => setCameraView('top');

    // Initial Setup
    updateLegendBar();
    buildSliceEntities();
    buildBoundaryEntity();
    buildCrestEntity();
    // Frame the actual geometry on load so the data is always on screen
    // regardless of corridor size or location (no manual panning needed).
    frameInitialView();

  </script>
</body>
</html>
"""

    with open(out_html, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f"✓ Saved 3D CesiumJS Interactive Viewer: {out_html} ({os.path.getsize(out_html):,} bytes)")
    return out_html

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Generate 3D CesiumJS Viewer for a corridor region")
    parser.add_argument("--mode", choices=["hollow", "solid"], default="hollow", help="Default geometry mode: hollow (default) or solid")
    parser.add_argument("--region", "-r", default="south", help="Region to build the viewer for (e.g. 'south' or 'north').")
    args = parser.parse_args()
    generate_cesium_viewer(default_geometry_mode=args.mode, region=args.region)
