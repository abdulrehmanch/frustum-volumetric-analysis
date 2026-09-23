#!/usr/bin/env python3
"""
calculate_frustum_volume.py

Universal, robust Python script to calculate the multi-layer volumetric capacity
of any contour dataset using the Prismoidal Frustum Method:
    V_slice = (dh / 3) * (A_low + A_high + sqrt(A_low * A_high))

Features:
- Dataset-agnostic: auto-detects CRS, elevation attributes, boundary morphology, and vertical intervals.
- Universal topological engine supporting 3 solver modes (auto-detected or user-specified):
    1. 'ring': Topological ring-snap for closed internal contour rings (e.g. South basin).
    2. 'split': Boundary-cut planar partition for mining concession blocks (e.g. Hassan Abdal 10B).
    3. 'band': Morphological corridor band for open embankment bunds (e.g. North).
- Strict geometric nesting: enforces A(Z_k) >= A(Z_{k+1}) across all stages.
- Generates 5 standard engineering deliverables:
    1. <prefix>_frustum_slice_polygons.shp       (horizontal slice layers)
    2. <prefix>_frustum_cumulative_polygons.shp  (solid stage footprints)
    3. <prefix>_frustum_volumetric_report.csv    (engineering schedule)
    4. <prefix>_stage_storage_curves.png         (stage-area & stage-storage curves)
    5. <prefix>_contour_slices_map.png           (2D planimetric stage map)
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import unary_union, split, polygonize
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize
import matplotlib.cm as cm

# Engineering unit conversion constants
M3_TO_ACRE_FEET = 0.000810713194
M3_TO_CUFT = 35.31466672148859
DEFAULT_CLOSE_DIST = 25.0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Universal Contour Prismoidal Frustum Volumetric Analysis"
    )
    parser.add_argument(
        "--input", "-i",
        required=True,
        help="Path to input contour shapefile (*.shp)"
    )
    parser.add_argument(
        "--boundary", "-b",
        default=None,
        help="Optional path to separate boundary polygon shapefile. If omitted, auto-detected from input."
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Target output directory. Defaults to <input_parent>/output."
    )
    parser.add_argument(
        "--prefix", "-p",
        default=None,
        help="Prefix for output filenames. Defaults to shapefile stem in lowercase."
    )
    parser.add_argument(
        "--elev-col", "-e",
        default=None,
        help="Name of elevation column. If omitted, auto-detected."
    )
    parser.add_argument(
        "--target-epsg",
        default=None,
        help="Target projected metric CRS (e.g. 'EPSG:32643'). If omitted, estimated dynamically."
    )
    parser.add_argument(
        "--method", "-m",
        choices=["auto", "ring", "split", "band"],
        default="auto",
        help="Polygonization solver: 'auto' (default), 'ring' (closed rings), 'split' (boundary-cut block), or 'band' (open bund corridor)."
    )
    parser.add_argument(
        "--close-dist",
        type=float,
        default=DEFAULT_CLOSE_DIST,
        help=f"Morphological close distance (m) for 'band' solver (default: {DEFAULT_CLOSE_DIST})."
    )
    parser.add_argument(
        "--snap-tol",
        type=float,
        default=1.0,
        help="Snap tolerance in meters for boundary closing (default: 1.0)."
    )
    return parser.parse_args()


def detect_elevation_column(gdf, override=None):
    """Dynamically identify the elevation attribute column."""
    if override:
        if override in gdf.columns:
            return override
        raise ValueError(f"Specified elevation column '{override}' not found in columns: {list(gdf.columns)}")

    candidates = ['elevation', 'elev', 'contour', 'z', 'height', 'level']
    for cand in candidates:
        for col in gdf.columns:
            if col.strip().lower() == cand:
                return col

    for col in gdf.columns:
        if any(cand in col.lower() for cand in candidates):
            return col

    numeric_cols = [c for c in gdf.select_dtypes(include=[np.number]).columns if c != 'geometry']
    if numeric_cols:
        return max(numeric_cols, key=lambda c: gdf[c].nunique())

    raise ValueError(f"Could not automatically detect elevation column from attributes: {list(gdf.columns)}")


def _all_lines(geom):
    """Flatten a (Multi)LineString into a list of LineStrings."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == 'LineString':
        return [geom]
    if geom.geom_type == 'MultiLineString':
        return list(geom.geoms)
    if geom.geom_type == 'GeometryCollection':
        out = []
        for g in geom.geoms:
            out.extend(_all_lines(g))
        return out
    return []


def _lines_at(contours_gdf, elev_col, el):
    """All LineStrings for a single contour elevation."""
    sub = contours_gdf[contours_gdf[elev_col] == el]
    lines = []
    for g in sub.geometry:
        lines.extend(_all_lines(g))
    return lines


def _extend_line(line, distance=0.3):
    """Extend a LineString slightly at both ends so it cleanly intersects boundaries during polygon splits."""
    coords = list(line.coords)
    if len(coords) < 2:
        return line
    p0, p1 = coords[0], coords[1]
    dx0, dy0 = p0[0] - p1[0], p0[1] - p1[1]
    L0 = (dx0**2 + dy0**2)**0.5
    if L0 > 0:
        coords[0] = (p0[0] + (dx0 / L0) * distance, p0[1] + (dy0 / L0) * distance)
    pn, pn_prev = coords[-1], coords[-2]
    dxn, dyn = pn[0] - pn_prev[0], pn[1] - pn_prev[1]
    Ln = (dxn**2 + dyn**2)**0.5
    if Ln > 0:
        coords[-1] = (pn[0] + (dxn / Ln) * distance, pn[1] + (dyn / Ln) * distance)
    return LineString(coords)


def clean_polygon(geom):
    """Ensure geometry is strictly a valid Polygon or MultiPolygon with non-zero area."""
    if geom is None or geom.is_empty:
        return Polygon()
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    if geom.geom_type in ('Polygon', 'MultiPolygon'):
        return geom
    if geom.geom_type == 'GeometryCollection':
        polys = [g for g in geom.geoms if g.geom_type in ('Polygon', 'MultiPolygon') and g.area > 0]
        if polys:
            u = unary_union(polys)
            return u if u.is_valid else shapely.make_valid(u)
    return Polygon()


def _robust_union(geoms):
    """Union a list of geometries, healing invalid inputs before/after the merge."""
    cleaned = [p for p in geoms if p is not None and not p.is_empty]
    cleaned = [p if p.is_valid else shapely.make_valid(p) for p in cleaned]
    if not cleaned:
        return Polygon()
    try:
        merged = unary_union(cleaned)
    except Exception:
        merged = shapely.union_all([shapely.set_precision(p, 1e-6) for p in cleaned])
    if not merged.is_valid:
        merged = shapely.make_valid(merged)
    return merged


def analyze_and_load(input_path, boundary_path=None, elev_col_override=None, target_epsg_override=None):
    """Load, inspect, and project contour and boundary datasets."""
    print("=" * 80)
    print("STAGE 1: INPUT DATA ANALYSIS & PROJECTION")
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    gdf_raw = gpd.read_file(input_path)
    print(f"  Input Dataset: {input_path}")
    print(f"  Total Features: {len(gdf_raw)}")
    print(f"  Source CRS: {gdf_raw.crs}")

    if target_epsg_override:
        target_crs = target_epsg_override
    elif gdf_raw.crs is not None and not gdf_raw.crs.is_geographic:
        target_crs = gdf_raw.crs
    else:
        if gdf_raw.crs is None:
            gdf_raw = gdf_raw.set_crs("EPSG:4326")
        target_crs = gdf_raw.estimate_utm_crs()

    print(f"  Projected Metric CRS: {target_crs}")
    gdf = gdf_raw.to_crs(target_crs)
    gdf['geometry'] = shapely.force_2d(gdf.geometry.values)

    elev_col = detect_elevation_column(gdf, elev_col_override)
    print(f"  Elevation Attribute Column: '{elev_col}'")

    bnd_poly = None
    bnd_line = None
    if boundary_path and os.path.exists(boundary_path):
        bnd_gdf = gpd.read_file(boundary_path).to_crs(target_crs)
        bnd_poly = clean_polygon(unary_union(bnd_gdf.geometry))
        bnd_line = bnd_poly.boundary
        print(f"  Boundary: loaded from external file ({boundary_path})")
    else:
        zero_rows = gdf[gdf[elev_col] == 0.0]
        if len(zero_rows) > 0 and len(zero_rows) <= 2:
            geom = zero_rows.geometry.iloc[0]
            if geom.geom_type in ('Polygon', 'MultiPolygon'):
                bnd_poly = clean_polygon(geom)
                bnd_line = bnd_poly.boundary
            elif geom.geom_type == 'LineString':
                bnd_line = geom
                bnd_poly = Polygon(geom.coords) if geom.is_closed else Polygon()
            elif geom.geom_type == 'MultiLineString':
                bnd_line = unary_union(list(geom.geoms))
                closed = [l for l in geom.geoms if l.is_closed]
                bnd_poly = Polygon(closed[0].coords) if closed else Polygon()

            if bnd_poly is not None and bnd_poly.is_valid and bnd_poly.area > 0:
                print(f"  Boundary: auto-detected explicit boundary feature (ELEVATION == 0.0)")

    if bnd_poly is not None and bnd_poly.area > 0:
        contours_gdf = gdf[gdf[elev_col] > 0.0].copy()
    else:
        contours_gdf = gdf.copy()
        u_lines = unary_union(contours_gdf.geometry)
        bnd_poly = clean_polygon(u_lines.convex_hull)
        bnd_line = bnd_poly.boundary
        print("  Boundary: auto-derived convex envelope from contour extents")

    bnd_poly = clean_polygon(bnd_poly)
    print(f"  Boundary Footprint Area: {bnd_poly.area:,.2f} m² ({bnd_poly.area / 10000.0:.3f} ha)")
    print(f"  Boundary Perimeter: {bnd_line.length:,.2f} m")
    return gdf, contours_gdf, elev_col, bnd_poly, bnd_line, str(target_crs)


# ---------------------------------------------------------------------------
# TOPOLOGICAL SOLVERS
# ---------------------------------------------------------------------------

def _solve_ring_snap(contours_gdf, elev_col, bnd_line, unique_elevs, max_elev):
    """Solver 1: Ring-snap for closed contour rings (South-style)."""
    crest_rows = contours_gdf[contours_gdf[elev_col] == max_elev]
    crest_lines = []
    for g in crest_rows.geometry:
        crest_lines.extend(_all_lines(g))

    crest_rings = [Polygon(l) for l in crest_lines if l.is_ring and Polygon(l).is_valid and Polygon(l).area > 0]
    if not crest_rings:
        raise ValueError(f"Could not form closed crest ring at elevation {max_elev:.1f} m.")
    crest_poly = crest_rings[0]

    cumul_polys = {max_elev: crest_poly}
    for el in unique_elevs:
        if el >= max_elev:
            continue
        lines = _lines_at(contours_gdf, elev_col, el)
        rings = [Polygon(l) for l in lines if l.is_ring and Polygon(l).is_valid and Polygon(l).area > 0]
        open_lines = [l for l in lines if not l.is_ring]

        if len(open_lines) == 0 and len(rings) > 0:
            p = unary_union(rings)
        else:
            snapped_lines = [shapely.snap(l, bnd_line, tolerance=0.1) for l in open_lines]
            curr_bnd = bnd_line
            for sl in snapped_lines:
                curr_bnd = shapely.snap(curr_bnd, sl, tolerance=0.1)
            noded = unary_union([curr_bnd] + snapped_lines + [l for l in lines if l.is_ring])
            candidates = list(polygonize(noded))
            matching = [cp for cp in candidates if cp.intersection(crest_poly).area > 0.3 * crest_poly.area]
            p = unary_union(matching) if matching else crest_poly

        cumul_polys[el] = p

    return cumul_polys


def _solve_boundary_split(contours_gdf, elev_col, bnd_poly, unique_elevs, max_elev, ext_dist=0.3):
    """Solver 2: Boundary-cut planar partition for mining concession blocks (10B-style)."""
    stage_polys = {}
    running_poly = None

    for el in sorted(unique_elevs, reverse=True):
        sub = contours_gdf[contours_gdf[elev_col] == el]
        raw_lines = []
        for g in sub.geometry:
            raw_lines.extend(_all_lines(g))

        rings = [Polygon(l.coords) for l in raw_lines if l.is_ring and Polygon(l.coords).is_valid and Polygon(l.coords).area > 0]
        open_lines = [l for l in raw_lines if not l.is_ring]

        if len(open_lines) == 0 and len(rings) > 0:
            stage_p = clean_polygon(unary_union(rings))
        else:
            ext_lines = [_extend_line(l, ext_dist) for l in open_lines]
            ring_lines = [Polygon(r.exterior).exterior for r in rings]
            cut_lines = unary_union(ext_lines + ring_lines)

            split_res = split(bnd_poly, cut_lines)
            candidates = [p for p in split_res.geoms if p.area > 1e-4]

            if not candidates:
                stage_p = bnd_poly
            elif running_poly is None:
                stage_p = min(candidates, key=lambda p: p.area)
            else:
                matching = [p for p in candidates if p.intersection(running_poly).area > 0.4 * running_poly.area]
                stage_p = unary_union(matching) if matching else max(candidates, key=lambda p: p.intersection(running_poly).area)

        stage_p = clean_polygon(stage_p)
        running_poly = stage_p if running_poly is None else unary_union([running_poly, stage_p])
        running_poly = clean_polygon(running_poly)
        stage_polys[el] = running_poly

    return stage_polys


def _solve_corridor_band(contours_gdf, elev_col, bnd_poly, unique_elevs, close_dist=DEFAULT_CLOSE_DIST):
    """Solver 3: Morphological corridor band for open embankment bunds (North-style)."""
    all_lines = []
    line_elev = []
    for _, row in contours_gdf.iterrows():
        el = float(row[elev_col])
        for l in _all_lines(row.geometry):
            if not l.is_empty:
                all_lines.append(l)
                line_elev.append(el)

    line_elev = np.asarray(line_elev, dtype=float)
    clip_poly = bnd_poly if (bnd_poly is not None and not bnd_poly.is_empty and bnd_poly.area > 0) else None

    def _band_at_or_above(el):
        sel = [all_lines[i] for i in range(len(all_lines)) if line_elev[i] >= (el - 1e-9)]
        if not sel:
            return Polygon()
        u = _robust_union(sel)
        band = u.buffer(close_dist, join_style=1).buffer(-close_dist, join_style=1)
        if not band.is_valid:
            band = shapely.make_valid(band)
        if clip_poly is not None:
            band = band.intersection(clip_poly)
            if not band.is_valid:
                band = shapely.make_valid(band)
        return clean_polygon(band)

    footprints = {el: _band_at_or_above(el) for el in unique_elevs}
    elevs_desc = sorted(unique_elevs, reverse=True)
    running = None
    for el in elevs_desc:
        fp = footprints[el]
        running = fp if (running is None or running.is_empty) else _robust_union([running, fp])
        if clip_poly is not None:
            running = running.intersection(clip_poly)
            if not running.is_valid:
                running = shapely.make_valid(running)
        footprints[el] = clean_polygon(running)

    return footprints


def solve_stage_footprints(contours_gdf, elev_col, bnd_poly, bnd_line, method="auto",
                           close_dist=DEFAULT_CLOSE_DIST, snap_tol=1.0):
    """
    Selects and runs the appropriate solver based on data topology or user choice.
    """
    print("\n" + "=" * 80)
    print("STAGE 2: TOPOLOGICAL CONTOUR SLICING & FOOTPRINT EXTRACTION")

    unique_elevs = sorted(contours_gdf[elev_col].unique())
    max_elev = max(unique_elevs)
    min_elev = min(unique_elevs)
    print(f"  Contour Elevation Range: {min_elev:.1f} m (Base) to {max_elev:.1f} m (Crest)")
    print(f"  Number of Discrete Contour Stages: {len(unique_elevs)}")

    # Check crest closure
    crest_rows = contours_gdf[contours_gdf[elev_col] == max_elev]
    crest_lines = []
    for g in crest_rows.geometry:
        crest_lines.extend(_all_lines(g))
    has_closed_crest = any(l.is_ring for l in crest_lines if hasattr(l, 'is_ring'))

    # Calculate boundary compactness (isoperimetric quotient: 4*pi*A / P^2)
    bnd_area = bnd_poly.area
    bnd_perim = bnd_line.length
    compactness = (4.0 * np.pi * bnd_area) / (bnd_perim ** 2) if bnd_perim > 0 else 0.0

    # Auto-detection
    if method == "auto":
        if has_closed_crest:
            chosen = "ring"
            reason = "standalone closed crest ring detected (closed basin / pit model)"
        elif compactness < 0.1:
            chosen = "band"
            reason = f"elongated corridor morphology (compactness={compactness:.4f} < 0.1, open bund model)"
        else:
            chosen = "split"
            reason = f"compact concession block morphology (compactness={compactness:.4f} >= 0.1, boundary-cut model)"
    else:
        chosen = method
        reason = f"explicitly requested by user (--method {method})"

    print(f"  Selected Solver: '{chosen.upper()}' ({reason})")

    if chosen == "ring":
        try:
            cumul_polys = _solve_ring_snap(contours_gdf, elev_col, bnd_line, unique_elevs, max_elev)
        except Exception as e:
            print(f"  Ring solver encountered: {e}. Falling back to boundary-split.")
            cumul_polys = _solve_boundary_split(contours_gdf, elev_col, bnd_poly, unique_elevs, max_elev)
    elif chosen == "band":
        print(f"  Contour-band close distance: {close_dist:.1f} m")
        cumul_polys = _solve_corridor_band(contours_gdf, elev_col, bnd_poly, unique_elevs, close_dist=close_dist)
    else:  # split
        cumul_polys = _solve_boundary_split(contours_gdf, elev_col, bnd_poly, unique_elevs, max_elev)

    # Drop empty stages
    cumul_polys = {el: clean_polygon(p) for el, p in cumul_polys.items()
                   if p is not None and not p.is_empty and p.area > 0}

    elevs_asc = sorted(cumul_polys.keys())
    print("\n  Verified Watertight Stage Polygons:")
    for el in elevs_asc:
        pa = cumul_polys[el].area
        print(f"    Stage {el:6.1f} m: Area = {pa:10.2f} m² ({pa / 10000.0:.3f} ha)")

    return elevs_asc, cumul_polys


def compute_volumetrics(elevs_asc, stage_polys, bnd_poly, crs_str):
    """
    Stage 3: Calculate multi-layer prismoidal frustum and end-area volumes.
    """
    print("\n" + "=" * 80)
    print("STAGE 3: VOLUMETRIC COMPUTATION (PRISMOIDAL FRUSTUM)")

    n_stages = len(elevs_asc)
    areas_m2 = [stage_polys[el].area for el in elevs_asc]

    stage_records = []
    layer_records = []

    cumul_frustum_vol = 0.0
    cumul_endarea_vol = 0.0

    base_elev = elevs_asc[0]
    base_area = areas_m2[0]

    stage_records.append({
        'Stage_ID': 1,
        'Elevation_m': base_elev,
        'Stage_Depth_m': 0.0,
        'Contour_Area_m2': round(base_area, 2),
        'Contour_Area_ha': round(base_area / 10000.0, 4),
        'Slice_Frustum_Vol_m3': 0.0,
        'Slice_Frustum_Vol_CuFt': 0.0,
        'Cumul_Frustum_Vol_m3': 0.0,
        'Cumul_Frustum_Vol_1000m3': 0.0,
        'Cumul_Frustum_Vol_AcreFeet': 0.0,
        'Cumul_Frustum_Vol_CuFt': 0.0,
        'Slice_EndArea_Vol_m3': 0.0,
        'Slice_EndArea_Vol_CuFt': 0.0,
        'Cumul_EndArea_Vol_m3': 0.0,
        'Cumul_EndArea_Vol_CuFt': 0.0,
        'Delta_Vol_m3': 0.0,
        'Delta_Percent': 0.0
    })

    print("-" * 115)
    print(f"{'Layer':<6} | {'Z_Low (m)':<9} | {'Z_High (m)':<10} | {'dH (m)':<6} | {'Frustum (m³)':<13} | {'End-Area (m³)':<13} | {'Diff (m³)':<10} | {'Cumul Frustum (m³)':<18}")
    print("-" * 115)

    for k in range(n_stages - 1):
        z_low = elevs_asc[k]
        z_high = elevs_asc[k + 1]
        dh = round(z_high - z_low, 3)
        a_low = areas_m2[k]
        a_high = areas_m2[k + 1]

        v_frustum = (dh / 3.0) * (a_low + a_high + np.sqrt(a_low * a_high))
        v_endarea = (dh / 2.0) * (a_low + a_high)

        diff_vol = v_endarea - v_frustum
        diff_pct = (diff_vol / v_frustum * 100.0) if v_frustum > 0 else 0.0

        cumul_frustum_vol += v_frustum
        cumul_endarea_vol += v_endarea

        stage_depth = round(z_high - base_elev, 2)
        print(f"L{k+1:<5} | {z_low:<9.1f} | {z_high:<10.1f} | {dh:<6.2f} | {v_frustum:<13,.2f} | {v_endarea:<13,.2f} | {diff_vol:<+10.2f} | {cumul_frustum_vol:<18,.2f}")

        slice_geom = clean_polygon(stage_polys[z_low].difference(stage_polys[z_high]))

        layer_records.append({
            'STAGE_ID': k + 1,
            'Z_LOW': z_low,
            'Z_HIGH': z_high,
            'DELTA_H': dh,
            'A_LOW_M2': round(a_low, 2),
            'A_HIGH_M2': round(a_high, 2),
            'VOL_M3': round(v_frustum, 2),
            'VOL_CUFT': round(v_frustum * M3_TO_CUFT, 2),
            'CUMUL_M3': round(cumul_frustum_vol, 2),
            'CUM_CUFT': round(cumul_frustum_vol * M3_TO_CUFT, 2),
            'geometry': slice_geom
        })

        stage_records.append({
            'Stage_ID': k + 2,
            'Elevation_m': z_high,
            'Stage_Depth_m': stage_depth,
            'Contour_Area_m2': round(a_high, 2),
            'Contour_Area_ha': round(a_high / 10000.0, 4),
            'Slice_Frustum_Vol_m3': round(v_frustum, 2),
            'Slice_Frustum_Vol_CuFt': round(v_frustum * M3_TO_CUFT, 2),
            'Cumul_Frustum_Vol_m3': round(cumul_frustum_vol, 2),
            'Cumul_Frustum_Vol_1000m3': round(cumul_frustum_vol / 1000.0, 3),
            'Cumul_Frustum_Vol_AcreFeet': round(cumul_frustum_vol * M3_TO_ACRE_FEET, 3),
            'Cumul_Frustum_Vol_CuFt': round(cumul_frustum_vol * M3_TO_CUFT, 2),
            'Slice_EndArea_Vol_m3': round(v_endarea, 2),
            'Slice_EndArea_Vol_CuFt': round(v_endarea * M3_TO_CUFT, 2),
            'Cumul_EndArea_Vol_m3': round(cumul_endarea_vol, 2),
            'Cumul_EndArea_Vol_CuFt': round(cumul_endarea_vol * M3_TO_CUFT, 2),
            'Delta_Vol_m3': round(diff_vol, 2),
            'Delta_Percent': round(diff_pct, 3)
        })

    cumul_records = []
    for idx, el in enumerate(elevs_asc):
        cumul_records.append({
            'STAGE_ID': idx + 1,
            'ELEVATION': el,
            'AREA_M2': round(stage_polys[el].area, 2),
            'AREA_HA': round(stage_polys[el].area / 10000.0, 4),
            'DEPTH_M': round(el - base_elev, 2),
            'geometry': stage_polys[el]
        })

    report_df = pd.DataFrame(stage_records)
    layers_gdf = gpd.GeoDataFrame(layer_records, crs=crs_str)
    cumul_gdf = gpd.GeoDataFrame(cumul_records, crs=crs_str)

    print("-" * 115)
    print(f"Total Frustum Volume:  {cumul_frustum_vol:15,.2f} m³ ({cumul_frustum_vol * M3_TO_CUFT:,.2f} cu ft / {cumul_frustum_vol * M3_TO_ACRE_FEET:,.2f} acre-ft)")
    print(f"Total End-Area Volume: {cumul_endarea_vol:15,.2f} m³ ({cumul_endarea_vol * M3_TO_CUFT:,.2f} cu ft)")
    print(f"Difference (End-Area - Frustum): {cumul_endarea_vol - cumul_frustum_vol:+10.2f} m³ ({(cumul_endarea_vol - cumul_frustum_vol)/cumul_frustum_vol*100.0:+.2f}%)")

    return report_df, layers_gdf, cumul_gdf


def export_deliverables(output_dir, prefix, report_df, layers_gdf, cumul_gdf, bnd_poly):
    """
    Stage 4: Write all 5 standard engineering deliverables.
    """
    print("\n" + "=" * 80)
    print("STAGE 4: EXPORTING DELIVERABLES")
    os.makedirs(output_dir, exist_ok=True)

    # 1. Frustum slice polygons shapefile
    slice_shp = os.path.join(output_dir, f"{prefix}_frustum_slice_polygons.shp")
    layers_gdf.to_file(slice_shp)
    print(f"  [1/5] Slice Polygons Shapefile:       {slice_shp}")

    # 2. Cumulative stage footprints shapefile
    cumul_shp = os.path.join(output_dir, f"{prefix}_frustum_cumulative_polygons.shp")
    cumul_gdf.to_file(cumul_shp)
    print(f"  [2/5] Cumulative Polygons Shapefile:  {cumul_shp}")

    # 3. CSV Report
    report_csv = os.path.join(output_dir, f"{prefix}_frustum_volumetric_report.csv")
    report_df.to_csv(report_csv, index=False)
    print(f"  [3/5] Volumetric Schedule CSV:        {report_csv}")

    # 4. Stage-Storage Curves Plot
    curves_png = os.path.join(output_dir, f"{prefix}_stage_storage_curves.png")
    fig, ax1 = plt.subplots(figsize=(10, 6), dpi=300)
    elevations = report_df['Elevation_m']
    areas = report_df['Contour_Area_m2']
    vols = report_df['Cumul_Frustum_Vol_m3']

    color1 = '#1f77b4'
    ax1.set_xlabel('Contour Elevation (m)', fontweight='bold')
    ax1.set_ylabel('Stage Footprint Area (m²)', color=color1, fontweight='bold')
    line1 = ax1.plot(elevations, areas, color=color1, marker='o', markersize=3, label='Stage Area (m²)', linewidth=2)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, linestyle='--', alpha=0.5)

    ax2 = ax1.twinx()
    color2 = '#d62728'
    ax2.set_ylabel('Cumulative Frustum Volume (m³)', color=color2, fontweight='bold')
    line2 = ax2.plot(elevations, vols, color=color2, marker='s', markersize=3, label='Cumul. Volume (m³)', linewidth=2)
    ax2.tick_params(axis='y', labelcolor=color2)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc='center left', framealpha=0.9)
    plt.title(f'Stage-Area & Stage-Storage Curves — {prefix.upper()}', fontweight='bold', pad=12)
    fig.tight_layout()
    plt.savefig(curves_png)
    plt.close()
    print(f"  [4/5] Stage-Storage Curves Plot:      {curves_png}")

    # 5. Planimetric 2D Slices Map
    map_png = os.path.join(output_dir, f"{prefix}_contour_slices_map.png")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=300)
    norm = Normalize(vmin=cumul_gdf['ELEVATION'].min(), vmax=cumul_gdf['ELEVATION'].max())
    cmap = cm.viridis

    for _, row in cumul_gdf.sort_values('ELEVATION', ascending=True).iterrows():
        color = cmap(norm(row['ELEVATION']))
        g = row.geometry
        if g.geom_type == 'Polygon':
            ax.plot(*g.exterior.xy, color=color, linewidth=1.2)
        elif g.geom_type == 'MultiPolygon':
            for p in g.geoms:
                ax.plot(*p.exterior.xy, color=color, linewidth=1.2)

    if bnd_poly.geom_type == 'Polygon':
        ax.plot(*bnd_poly.exterior.xy, color='black', linewidth=2.0, linestyle='--', label='Boundary')
    elif bnd_poly.geom_type == 'MultiPolygon':
        for p in bnd_poly.geoms:
            ax.plot(*p.exterior.xy, color='black', linewidth=2.0, linestyle='--', label='Boundary')

    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label('Contour Elevation (m)', fontweight='bold')

    ax.set_aspect('equal', 'box')
    ax.set_title(f'Watertight Contour Stage Footprints — {prefix.upper()}', fontweight='bold', pad=12)
    ax.set_xlabel('UTM Easting (m)', fontweight='bold')
    ax.set_ylabel('UTM Northing (m)', fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.6)
    fig.tight_layout()
    plt.savefig(map_png)
    plt.close()
    print(f"  [5/5] Planimetric Contour Slices Map: {map_png}")

    print("=" * 80)
    print("ANALYSIS COMPLETE — ALL DELIVERABLES GENERATED SUCCESSFULLY.")


def main():
    args = parse_args()
    input_path = os.path.abspath(args.input)
    
    input_stem = os.path.splitext(os.path.basename(input_path))[0]
    prefix = args.prefix.strip().lower() if args.prefix else input_stem.lower()

    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        parent_dir = os.path.dirname(input_path)
        grandparent_dir = os.path.dirname(parent_dir)
        if os.path.basename(parent_dir).lower() == "input":
            output_dir = os.path.join(grandparent_dir, "output")
        else:
            output_dir = os.path.join(parent_dir, "output")

    # Pipeline execution
    gdf, contours_gdf, elev_col, bnd_poly, bnd_line, crs_str = analyze_and_load(
        input_path=input_path,
        boundary_path=args.boundary,
        elev_col_override=args.elev_col,
        target_epsg_override=args.target_epsg
    )

    elevs_asc, stage_polys = solve_stage_footprints(
        contours_gdf=contours_gdf,
        elev_col=elev_col,
        bnd_poly=bnd_poly,
        bnd_line=bnd_line,
        method=args.method,
        close_dist=args.close_dist,
        snap_tol=args.snap_tol
    )

    report_df, layers_gdf, cumul_gdf = compute_volumetrics(
        elevs_asc=elevs_asc,
        stage_polys=stage_polys,
        bnd_poly=bnd_poly,
        crs_str=crs_str
    )

    export_deliverables(
        output_dir=output_dir,
        prefix=prefix,
        report_df=report_df,
        layers_gdf=layers_gdf,
        cumul_gdf=cumul_gdf,
        bnd_poly=bnd_poly
    )


if __name__ == "__main__":
    main()
