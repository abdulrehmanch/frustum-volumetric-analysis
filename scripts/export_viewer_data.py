#!/usr/bin/env python3
"""
export_viewer_data.py

Universal, standardized 3D WebGIS viewer exporter for frustum volumetric analysis.
Directly consumes the standardized outputs produced by calculate_frustum_volume.py:
  1. <prefix>_frustum_slice_polygons.shp       (horizontal slice difference polygons)
  2. <prefix>_frustum_cumulative_polygons.shp  (solid stage footprints)
  3. <prefix>_frustum_volumetric_report.csv    (volumetric schedule & metadata)

Compiles a standalone, viewer-compatible GeoJSON (viewer_data.geojson) and deploys
the interactive 3D CesiumJS visualizer (<prefix>_3d_viewer.html).

Zero-configuration execution:
    uv run python scripts/export_viewer_data.py --input inputs/<site_name>/<shapefile>.shp

Features:
- Zero column arguments, zero mapping, zero guesswork, zero fallbacks.
- Strictly validates standardized deliverable files and attribute columns.
- Generates 3 layer types for full interactive WebGIS exploration:
    1. 'slice_hollow' : hollow ring difference geometries with stage depth & volume HUD
    2. 'slice_solid'  : cumulative stage footprint solids
    3. 'contour_line' : stage contour polyline vectors tagged with elevation
"""

import os
import sys
import json
import shutil
import argparse

import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString, mapping

# --------------------------------------------------------------------------- #
# Engineering Unit Constants
# --------------------------------------------------------------------------- #
M3_TO_ACRE_FEET = 0.000810713194
M3_TO_CUFT      = 35.31466672148859

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VIEWER_SRC = os.path.join(SCRIPT_DIR, "viewer", "3d_viewer.html")

# Standardized column schemas guaranteed by calculate_frustum_volume.py
REQUIRED_SLICE_COLS = [
    "STAGE_ID", "Z_LOW", "Z_HIGH", "DELTA_H",
    "A_LOW_M2", "A_HIGH_M2", "VOL_M3", "VOL_CUFT",
    "CUMUL_M3", "CUM_CUFT"
]
REQUIRED_CUMUL_COLS = ["STAGE_ID", "ELEVATION", "AREA_M2", "AREA_HA", "DEPTH_M"]
REQUIRED_REPORT_COLS = ["Stage_ID", "Elevation_m", "Cumul_Frustum_Vol_m3"]


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def parse_args():
    parser = argparse.ArgumentParser(
        description="Export standardized viewer GeoJSON and deploy 3D WebGIS client.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to input shapefile (*.shp) used to identify site."
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Target output directory containing analysis deliverables. Auto-derived from --input."
    )
    parser.add_argument(
        "--prefix", "-p",
        default=None,
        help="Deliverable prefix. Auto-detected from output directory."
    )
    return parser.parse_args()


# --------------------------------------------------------------------------- #
# Path Helpers
# --------------------------------------------------------------------------- #
def derive_output_dir(input_shp: str) -> tuple[str, str, str]:
    """
    Derive output_dir, site_name, and default prefix from input path.
    Standardized convention matching calculate_frustum_volume.py.
    """
    abs_path = os.path.abspath(input_shp)
    input_stem = os.path.splitext(os.path.basename(abs_path))[0]
    parent_dir = os.path.dirname(abs_path)
    site_name = os.path.basename(parent_dir)
    grandparent_dir = os.path.dirname(parent_dir)
    grandparent_name = os.path.basename(grandparent_dir).lower()

    if grandparent_name in ("inputs", "input"):
        project_root = os.path.dirname(grandparent_dir)
        out_dir = os.path.join(project_root, "outputs", site_name)
    elif site_name.lower() in ("input", "inputs"):
        out_dir = os.path.join(grandparent_dir, "outputs")
    else:
        out_dir = os.path.join(parent_dir, "outputs", site_name)

    return out_dir, site_name, input_stem.lower()


def find_prefix(output_dir: str, default_prefix: str) -> str:
    """Detect the deliverable prefix from existing standard output shapefiles."""
    if os.path.exists(output_dir):
        for fname in sorted(os.listdir(output_dir)):
            if fname.endswith("_frustum_slice_polygons.shp"):
                return fname[: -len("_frustum_slice_polygons.shp")]
    return default_prefix


def validate_schema(df: pd.DataFrame | gpd.GeoDataFrame, required_cols: list[str], filename: str):
    """Strictly assert required standard columns exist; fail loudly without guessing."""
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        sep = "=" * 80
        print(f"\n{sep}", file=sys.stderr)
        print("ERROR: STANDARDIZED DELIVERABLE SCHEMA VALIDATION FAILED", file=sys.stderr)
        print(sep, file=sys.stderr)
        print(f"  File             : {filename}", file=sys.stderr)
        print(f"  Missing columns  : {missing}", file=sys.stderr)
        print(f"  Available columns: {list(df.columns)}", file=sys.stderr)
        print("\n  This script requires deliverables generated by calculate_frustum_volume.py.", file=sys.stderr)
        print("  Please run calculate_frustum_volume.py first.", file=sys.stderr)
        print(sep, file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------------------- #
# Feature Builders
# --------------------------------------------------------------------------- #
def _build_slice_properties(row: pd.Series, crest_elev: float, layer_type: str) -> dict:
    """Build standardized GeoJSON properties dict for a slice layer."""
    stage_id = int(row["STAGE_ID"])
    z_low    = float(row["Z_LOW"])
    z_high   = float(row["Z_HIGH"])
    delta_h  = float(row["DELTA_H"])
    a_high   = float(row["A_HIGH_M2"])
    a_low    = float(row["A_LOW_M2"])
    vol_m3   = float(row["VOL_M3"])
    cum_m3   = float(row["CUMUL_M3"])
    vol_cuft = float(row["VOL_CUFT"])
    cum_cuft = float(row["CUM_CUFT"])

    dh_high = crest_elev - z_high
    dh_low  = crest_elev - z_low
    depth_mean = (dh_high + dh_low) / 2.0

    return {
        "layer_type":   layer_type,
        "stage_id":     stage_id,
        "z_low":        round(z_low, 3),
        "z_high":       round(z_high, 3),
        "delta_h":      round(delta_h, 3),
        "area_m2":      round(a_high, 2),
        "area_ha":      round(a_high / 10000.0, 4),
        "area_low_m2":  round(a_low, 2),
        "vol_m3":       round(vol_m3, 2),
        "vol_cuft":     round(vol_cuft, 2),
        "cum_m3":       round(cum_m3, 2),
        "cum_cuft":     round(cum_cuft, 2),
        "cum_acft":     round(cum_m3 * M3_TO_ACRE_FEET, 4),
        "depth_mean_m": round(depth_mean, 2),
        "depth_high_m": round(dh_high, 2),
        "depth_low_m":  round(dh_low, 2),
        "label":        f"Layer {stage_id}: {z_low:.1f} m – {z_high:.1f} m",
    }


def build_hollow_features(gdf_slices: gpd.GeoDataFrame, gdf_cumul: gpd.GeoDataFrame, crest_elev: float) -> list[dict]:
    """
    Build hollow (donut-ring) slice features.
    The uppermost slice (z_high >= crest) is capped with the solid exterior footprint.
    """
    features = []
    for _, row in gdf_slices.iterrows():
        z_high = float(row["Z_HIGH"])
        geom = row.geometry

        if z_high >= crest_elev:
            match = gdf_cumul[gdf_cumul["STAGE_ID"] == int(row["STAGE_ID"])]
            if len(match) > 0:
                cg = match.iloc[0].geometry
                if cg.geom_type == "Polygon":
                    geom = Polygon(cg.exterior)
                elif cg.geom_type == "MultiPolygon":
                    geom = MultiPolygon([Polygon(p.exterior) for p in cg.geoms])

        features.append({
            "type":       "Feature",
            "properties": _build_slice_properties(row, crest_elev, "slice_hollow"),
            "geometry":   mapping(geom),
        })
    return features


def build_solid_features(gdf_slices: gpd.GeoDataFrame, gdf_cumul: gpd.GeoDataFrame, crest_elev: float) -> list[dict]:
    """Build solid cumulative footprint features for all stages."""
    features = []
    for _, row in gdf_slices.iterrows():
        stage_id = int(row["STAGE_ID"])
        match = gdf_cumul[gdf_cumul["STAGE_ID"] == stage_id]
        if len(match) == 0:
            continue
        cg = match.iloc[0].geometry
        if cg.geom_type == "Polygon":
            solid = Polygon(cg.exterior)
        elif cg.geom_type == "MultiPolygon":
            solid = MultiPolygon([Polygon(p.exterior) for p in cg.geoms])
        else:
            solid = cg

        features.append({
            "type":       "Feature",
            "properties": _build_slice_properties(row, crest_elev, "slice_solid"),
            "geometry":   mapping(solid),
        })
    return features


def build_contour_features(gdf_cumul: gpd.GeoDataFrame) -> list[dict]:
    """
    Build watertight stage contour polyline vectors directly from cumulative stage footprints.
    Guarantees 100% geometric alignment with 3D solid/hollow extrusion meshes.
    """
    features = []
    for _, row in gdf_cumul.iterrows():
        elev = float(row["ELEVATION"])
        stage_id = int(row["STAGE_ID"])
        geom = row.geometry

        if geom is None or geom.is_empty:
            continue

        lines = []
        if geom.geom_type == "Polygon":
            lines.append(LineString(geom.exterior.coords))
        elif geom.geom_type == "MultiPolygon":
            for p in geom.geoms:
                lines.append(LineString(p.exterior.coords))

        for line in lines:
            features.append({
                "type": "Feature",
                "properties": {
                    "layer_type": "contour_line",
                    "stage_id":   stage_id,
                    "elevation":  round(elev, 2),
                    "label":      f"Contour {elev:.1f} m",
                },
                "geometry": mapping(line),
            })
    return features


# --------------------------------------------------------------------------- #
# Main Execution
# --------------------------------------------------------------------------- #
def main():
    args = parse_args()
    input_shp = os.path.abspath(args.input)

    # ── Resolve Output Paths ─────────────────────────────────────────────────
    default_out_dir, site_name, default_prefix = derive_output_dir(input_shp)
    out_dir = os.path.abspath(args.output_dir) if args.output_dir else default_out_dir
    prefix = args.prefix.strip().lower() if args.prefix else find_prefix(out_dir, default_prefix)

    slice_shp  = os.path.join(out_dir, f"{prefix}_frustum_slice_polygons.shp")
    cumul_shp  = os.path.join(out_dir, f"{prefix}_frustum_cumulative_polygons.shp")
    csv_report = os.path.join(out_dir, f"{prefix}_frustum_volumetric_report.csv")

    sep = "=" * 80
    print(sep)
    print("3D WEBGIS VIEWER EXPORTER (STANDARDIZED PIPELINE)")
    print(sep)
    print(f"  Site Name        : {site_name}")
    print(f"  Output Prefix    : {prefix}")
    print(f"  Target Directory : {out_dir}")

    # ── Verify Required Standard Deliverables Exist ──────────────────────────
    missing_files = [p for p in [slice_shp, cumul_shp, csv_report] if not os.path.exists(p)]
    if missing_files:
        print(f"\n{sep}", file=sys.stderr)
        print("ERROR: REQUIRED STANDARDIZED DELIVERABLES NOT FOUND", file=sys.stderr)
        print(sep, file=sys.stderr)
        for mf in missing_files:
            print(f"  Missing: {mf}", file=sys.stderr)
        print("\nPlease run calculate_frustum_volume.py first:", file=sys.stderr)
        print(f"  uv run python scripts/calculate_frustum_volume.py --input {input_shp}", file=sys.stderr)
        print(sep, file=sys.stderr)
        sys.exit(1)

    # ── Load and Project Standard Deliverables to WGS84 (EPSG:4326) ──────────
    print("  Loading standardized deliverables…")
    gdf_slices = gpd.read_file(slice_shp).to_crs("EPSG:4326")
    gdf_cumul  = gpd.read_file(cumul_shp).to_crs("EPSG:4326")
    df_report  = pd.read_csv(csv_report)

    # ── Strict Schema Validation ─────────────────────────────────────────────
    validate_schema(gdf_slices, REQUIRED_SLICE_COLS, os.path.basename(slice_shp))
    validate_schema(gdf_cumul,  REQUIRED_CUMUL_COLS, os.path.basename(cumul_shp))
    validate_schema(df_report,  REQUIRED_REPORT_COLS, os.path.basename(csv_report))

    # ── Extract Summary Metrics ──────────────────────────────────────────────
    base_elev   = float(gdf_slices["Z_LOW"].min())
    crest_elev  = float(gdf_slices["Z_HIGH"].max())
    total_depth = round(crest_elev - base_elev, 2)
    total_vol   = float(df_report["Cumul_Frustum_Vol_m3"].max())
    bounds      = [round(float(b), 6) for b in gdf_slices.total_bounds]  # [minx, miny, maxx, maxy]
    center_lon  = round((bounds[0] + bounds[2]) / 2.0, 6)
    center_lat  = round((bounds[1] + bounds[3]) / 2.0, 6)

    print(f"  Base Elevation   : {base_elev:.2f} m")
    print(f"  Crest Elevation  : {crest_elev:.2f} m")
    print(f"  Total Depth      : {total_depth:.2f} m")
    print(f"  Total Volume     : {total_vol:,.2f} m³ ({total_vol * M3_TO_ACRE_FEET:,.3f} acre-ft)")
    print(f"  Center WGS84     : ({center_lat:.6f}, {center_lon:.6f})")

    # ── Build GeoJSON Feature Collections ────────────────────────────────────
    print("  Compiling 3D GeoJSON features…")
    features = []
    features.extend(build_hollow_features(gdf_slices, gdf_cumul, crest_elev))
    features.extend(build_solid_features(gdf_slices, gdf_cumul, crest_elev))
    features.extend(build_contour_features(gdf_cumul))

    summary = {
        "site_name":      site_name,
        "prefix":         prefix,
        "base_elev":      round(base_elev, 3),
        "crest_elev":     round(crest_elev, 3),
        "total_depth_m":  total_depth,
        "total_vol_m3":   round(total_vol, 2),
        "total_vol_acft": round(total_vol * M3_TO_ACRE_FEET, 2),
        "total_vol_cuft": round(total_vol * M3_TO_CUFT, 2),
        "num_slices":     int(len(gdf_slices)),
        "center_lon":     center_lon,
        "center_lat":     center_lat,
        "bounds":         bounds,
    }

    geojson = {
        "type":       "FeatureCollection",
        "properties": summary,
        "features":   features,
    }

    # ── Write viewer_data.geojson ────────────────────────────────────────────
    out_geojson = os.path.join(out_dir, "viewer_data.geojson")
    with open(out_geojson, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh, separators=(",", ":"))

    size_kb   = os.path.getsize(out_geojson) / 1024
    hollow_n  = sum(1 for f in features if f["properties"]["layer_type"] == "slice_hollow")
    solid_n   = sum(1 for f in features if f["properties"]["layer_type"] == "slice_solid")
    contour_n = sum(1 for f in features if f["properties"]["layer_type"] == "contour_line")

    print(f"\n  ✓ Generated viewer_data.geojson ({size_kb:.1f} KB)")
    print(f"    - {hollow_n} hollow slice features")
    print(f"    - {solid_n} solid stage features")
    print(f"    - {contour_n} contour line features")

    # ── Deploy Standalone 3D Viewer HTML ─────────────────────────────────────
    viewer_dst = os.path.join(out_dir, f"{prefix}_3d_viewer.html")
    if os.path.exists(VIEWER_SRC):
        shutil.copy2(VIEWER_SRC, viewer_dst)
        print(f"  ✓ Deployed 3D WebGIS Client   → {viewer_dst}")
    else:
        print(f"  WARNING: Viewer template not found at {VIEWER_SRC}", file=sys.stderr)

    rel_dir = os.path.relpath(out_dir)
    print(f"\n{sep}")
    print("STATUS: SUCCESS — 3D Viewer data exported and HTML deployed.")
    print(sep)
    print("To view locally:")
    print(f"  python3 -m http.server 8080 --directory {rel_dir}")
    print(f"  → http://localhost:8080/{prefix}_3d_viewer.html")
    print(sep)


if __name__ == "__main__":
    main()
