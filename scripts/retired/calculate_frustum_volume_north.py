#!/usr/bin/env python3
"""
calculate_frustum_volume_north.py

Standalone, robust Python script to calculate the multi-layer volumetric capacity
of a contour area using the Prismoidal Frustum Method across all internal contours
at Delta h = 0.5 m spacing.

This script is dataset-agnostic and runs on BOTH:
  * SOUTH-style data  : an explicit outer boundary feature (ELEVATION == 0.0)
                        plus clean nested closed contour rings.
  * NORTH-style data  : NO explicit boundary feature and mostly OPEN contour
                        polylines. In this case the corridor boundary and the
                        nested stage footprints are reconstructed purely by
                        VECTOR contour polygonization (noding the contour lines,
                        closing open lines against the boundary, and polygonizing).
                        No TIN / triangulation is used anywhere.

Outputs (prefixed with the detected region name, e.g. "south_" or "north_"):
1. <region>_frustum_slice_polygons.shp       (horizontal slice layers)
2. <region>_frustum_cumulative_polygons.shp  (solid stage footprints)
3. <region>_frustum_volumetric_report.csv    (tabular engineering schedule)
4. <region>_stage_storage_curves.png         (stage-area & stage-storage curves)
5. <region>_contour_slices_map.png           (2D planimetric slice map)

Strictly outputs ESRI Shapefiles (.shp, .shx, .dbf, .prj, .cpg). No GeoJSON files.
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
import geopandas as gpd
import shapely
from shapely.geometry import Polygon, MultiPolygon, LineString, MultiLineString
from shapely.ops import unary_union, polygonize
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.colors import Normalize
import matplotlib.cm as cm

# Constants
M3_TO_ACRE_FEET = 0.000810713194
M3_TO_CUFT = 35.31466672148859

# Snap tolerance (m) used when closing open contour polylines against the
# corridor boundary during vector polygonization of open-contour datasets.
DEFAULT_SNAP_TOL = 1.0

# Morphological-close distance (m) used to bridge the gaps BETWEEN neighbouring
# open contour lines when building the corridor band for OPEN-contour
# (north-style) datasets. It must be larger than the spacing between adjacent
# contours (so the band becomes a single connected ribbon) yet much smaller than
# any genuine empty interior (so voids the contours do NOT cover stay excluded
# from the footprint). Buffer-out then buffer-in by this distance.
DEFAULT_CLOSE_DIST = 25.0


def parse_args():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_input = os.path.join(script_dir, "north", "input", "Clip_Contour_North.shp")
    default_output_dir = os.path.join(script_dir, "north", "output")

    parser = argparse.ArgumentParser(
        description="Prismoidal Frustum Volumetric Calculation for a Contour Area (south or north)"
    )
    parser.add_argument(
        "--input", "-i",
        default=default_input,
        help=f"Path to Contours shapefile (default: {default_input})"
    )
    parser.add_argument(
        "--output-dir", "-o",
        default=default_output_dir,
        help=f"Target output directory for shapefiles, report, and curves (default: {default_output_dir})"
    )
    parser.add_argument(
        "--region", "-r",
        default=None,
        help="Region label used as output filename prefix (default: auto-detected from the input path, e.g. 'north' or 'south')."
    )
    parser.add_argument(
        "--snap-tol",
        type=float,
        default=DEFAULT_SNAP_TOL,
        help=f"Snap tolerance (m) for closing open contour lines against the corridor boundary (default: {DEFAULT_SNAP_TOL})."
    )
    parser.add_argument(
        "--close-dist",
        type=float,
        default=DEFAULT_CLOSE_DIST,
        help=(f"Morphological-close distance (m) for building the corridor band from open "
              f"contour lines (north-style data). Must exceed spacing between adjacent contours "
              f"but stay well below any genuine empty interior (default: {DEFAULT_CLOSE_DIST}).")
    )
    return parser.parse_args()


def detect_region(input_path, override=None):
    """
    Derive a short region label used as the output filename prefix.
    Priority: explicit override > 'north'/'south' found in the path > shapefile stem.
    """
    if override:
        return override.strip().lower()

    # Inspect path segments from the most specific (filename) outward so that an
    # ancestor folder like "Clip_Contour_North" does not mislabel a south input.
    norm = os.path.normpath(input_path).lower()
    segments = norm.split(os.sep)
    filename = os.path.splitext(segments[-1])[0] if segments else ""
    ordered = [filename] + list(reversed(segments[:-1]))
    for seg in ordered:
        if "north" in seg:
            return "north"
        if "south" in seg:
            return "south"
    return filename or "region"


def detect_elevation_column(gdf):
    """Find the elevation attribute column, tolerant to naming variants."""
    preferred = ['ELEVATION', 'Elevation', 'elevation', 'ELEV', 'elev', 'CONTOUR', 'contour', 'Z', 'z']
    for col in preferred:
        if col in gdf.columns:
            return col
    for col in gdf.columns:
        if any(c.lower() == col.lower() for c in ['elevation', 'elev', 'contour', 'z']):
            return col
    raise ValueError(f"Could not find elevation column in attributes: {list(gdf.columns)}")


def load_and_project_data(input_path, target_epsg="EPSG:32643"):
    """
    Step 1: Read input shapefile and reproject to UTM Zone 43N (EPSG:32643).
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input shapefile not found at: {input_path}")

    print("=" * 80)
    print("STAGE 1: COORDINATE TRANSFORMATION & DATA LOADING")
    print(f"Reading input dataset: {input_path}")
    gdf_raw = gpd.read_file(input_path)
    print(f"  Source CRS: {gdf_raw.crs}")
    print(f"  Total features in shapefile: {len(gdf_raw)}")

    # Normalize CRS so all planar geometry, areas, and distances are consistent.
    if gdf_raw.crs is None:
        gdf_raw = gdf_raw.set_crs("EPSG:4326")
        print("  Source CRS missing -> assumed EPSG:4326")
    gdf_utm = gdf_raw.to_crs(target_epsg)
    print(f"  Reprojected to metric projected CRS: {target_epsg}")

    # Force strictly 2D geometry. Input contours carry a Z ordinate which, if
    # left in place, leaks into planar polygonization and triggers GEOS topology
    # errors. Flattening to 2D keeps the CRS uniform.
    if bool(shapely.has_z(gdf_utm.geometry).any()):
        gdf_utm["geometry"] = shapely.force_2d(gdf_utm.geometry.values)
        print("  Flattened 3D geometry to 2D (Z ordinate dropped)")

    elev_col = detect_elevation_column(gdf_utm)
    print(f"  Elevation attribute column: '{elev_col}'")
    return gdf_utm, elev_col


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


def _robust_union(geoms):
    """Union a list of geometries, healing invalid inputs before/after the merge."""
    cleaned = []
    for p in geoms:
        if p is None or p.is_empty:
            continue
        if not p.is_valid:
            p = p.buffer(0)
        if not p.is_empty:
            cleaned.append(p)
    if not cleaned:
        return Polygon()
    try:
        merged = unary_union(cleaned)
    except Exception:
        merged = shapely.union_all([shapely.set_precision(p, 1e-6) for p in cleaned])
    if not merged.is_valid:
        merged = merged.buffer(0)
    return merged


def _polygonize_lines(lines):
    """Node a set of lines together and polygonize into face polygons."""
    if not lines:
        return []
    noded = unary_union(lines)  # nodes intersections
    return [p for p in polygonize(noded) if p.is_valid and p.area > 0]


def _polygonal_only(geom):
    """
    Reduce any geometry to its strictly polygonal content, returning a
    Polygon/MultiPolygon (possibly empty). Lines and points that can arise from a
    degenerate polygon difference are dropped so the result is always safe to
    write to a POLYGON shapefile.
    """
    if geom is None or geom.is_empty:
        return Polygon()
    gt = geom.geom_type
    if gt in ('Polygon', 'MultiPolygon'):
        return geom if geom.is_valid else geom.buffer(0)
    if gt == 'GeometryCollection':
        polys = [g for g in geom.geoms if g.geom_type in ('Polygon', 'MultiPolygon')]
        return unary_union(polys) if polys else Polygon()
    # LineString / MultiLineString / Point / MultiPoint -> no area.
    return Polygon()


# ---------------------------------------------------------------------------
# STAGE 2: BOUNDARY DELINEATION
# ---------------------------------------------------------------------------
def compute_vector_boundary(contours_gdf, elev_col, snap_tol=DEFAULT_SNAP_TOL,
                            close_dist=DEFAULT_CLOSE_DIST):
    """
    Derive the corridor band for an OPEN-contour dataset.

    OPEN contour polylines do not themselves enclose faces, so polygonizing the
    raw line network yields nothing usable. A convex/concave hull of the vertices
    is also WRONG here: it spans across the empty interior of a bent (L-shaped)
    corridor and fabricates footprint area where no contours exist.

    Instead we build the band that the contours actually occupy with a
    MORPHOLOGICAL CLOSE of the contour line network:

      band = union(lines).buffer(+close_dist).buffer(-close_dist)

    Buffering out then in by ``close_dist`` fuses gaps between neighbouring
    contour lines into a single connected ribbon, but because ``close_dist`` is
    far smaller than any genuine empty region, voids the contours do not cover
    (e.g. the open middle of an L bend) stay OUTSIDE the band. Interior holes are
    preserved so the footprint reflects only surveyed ground.
    """
    lines = []
    for g in contours_gdf.geometry:
        lines.extend(_all_lines(g))
    if not lines:
        raise ValueError("No contour lines available to derive a corridor band.")

    line_union = _robust_union(lines)
    band = line_union.buffer(close_dist, join_style=1).buffer(-close_dist, join_style=1)
    if not band.is_valid:
        band = band.buffer(0)

    if band is None or band.is_empty or band.geom_type not in ('Polygon', 'MultiPolygon'):
        raise ValueError("Could not derive a corridor band from the contour lines.")

    if band.geom_type == 'MultiPolygon':
        band = max(band.geoms, key=lambda gp: gp.area)
    return band


def delineate_boundary(gdf_utm, elev_col, snap_tol=DEFAULT_SNAP_TOL, close_dist=DEFAULT_CLOSE_DIST):
    """
    Step 2: Identify the outer perimeter boundary.
      * If a feature with ELEVATION == 0.0 exists -> use it (south path).
      * Otherwise -> derive it by vector contour polygonization (north path).
    Returns (bnd_line, bnd_poly, has_explicit_bnd).
    """
    print("\n" + "=" * 80)
    print("STAGE 2: CORRIDOR & BOUNDARY DELINEATION")

    bnd_rows = gdf_utm[gdf_utm[elev_col] == 0.0]
    has_explicit_bnd = len(bnd_rows) > 0

    if has_explicit_bnd:
        bnd_geom = bnd_rows.geometry.iloc[0]
        if bnd_geom.geom_type == 'LineString':
            bnd_line = bnd_geom
        elif bnd_geom.geom_type == 'MultiLineString':
            bnd_line = unary_union(list(bnd_geom.geoms))
        else:
            bnd_line = bnd_geom
        bnd_poly = Polygon(bnd_line.coords) if hasattr(bnd_line, 'coords') else Polygon(bnd_line)
        if not bnd_poly.is_valid:
            bnd_poly = bnd_poly.buffer(0)
        if bnd_poly.geom_type == 'MultiPolygon':
            bnd_poly = max(bnd_poly.geoms, key=lambda gp: gp.area)
        print("  Boundary source: explicit feature (ELEVATION == 0.0)")
        print(f"  Identified boundary feature: {bnd_geom.geom_type}")
    else:
        contours_gdf = gdf_utm[gdf_utm[elev_col] > 0.0]
        bnd_poly = compute_vector_boundary(contours_gdf, elev_col, snap_tol=snap_tol, close_dist=close_dist)
        bnd_line = bnd_poly.boundary  # exterior + any interior rings
        print("  Boundary source: morphological-close band of contour lines (no ELEVATION == 0.0 feature present)")
        print(f"  Contour-band close distance: {close_dist:.1f} m")

    bnd_area_m2 = bnd_poly.area
    print(f"  Boundary Perimeter: {bnd_line.length:,.2f} m")
    print(f"  Watertight Boundary Area: {bnd_area_m2:,.2f} m² ({bnd_area_m2/10000.0:.3f} ha)")
    return bnd_line, bnd_poly, has_explicit_bnd


# ---------------------------------------------------------------------------
# STAGE 3: CONTOUR POLYGONIZATION
# ---------------------------------------------------------------------------
def _polygonize_south(contours_gdf, elev_col, bnd_line, unique_elevs, max_elev):
    """Original south-style topological ring-snap polygonization (unchanged)."""
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

    return cumul_polys, crest_poly


def _build_nested_footprints_vector(contours_gdf, elev_col, bnd_poly, bnd_line,
                                    unique_elevs, snap_tol=DEFAULT_SNAP_TOL,
                                    close_dist=DEFAULT_CLOSE_DIST):
    """
    Reconstruct strictly-nested stage footprints for a RAISED BUND / EMBANKMENT
    described by OPEN contour polylines (north-style data), with no triangulation.

    A bund's fill volume lives in the CONTOURED SLOPES, not in the flat,
    uncontoured ground the bund sits around. So the plan footprint at stage Z is
    the area the embankment contours at or above Z actually occupy - NOT the
    whole area enclosed by any outer boundary (that would fabricate volume over
    flat terrain the survey never contoured).

    Method (per stage Z_k):
      1. Take every contour line whose elevation >= Z_k.
      2. Fuse them into a single connected band with a morphological close
         (buffer out then in by ``close_dist``). This bridges the gaps between
         neighbouring contour lines into a solid slope footprint while leaving
         any large uncontoured interior OUTSIDE the band.
      3. If an explicit corridor boundary polygon is supplied, clip the band to
         it so the footprint never spills past the surveyed toe.

    Since {contours >= Z_{k+1}} is a subset of {contours >= Z_k}, the bands - and
    therefore the areas - shrink monotonically as elevation rises. A final
    downward-accumulating union enforces strict nesting explicitly.
    """
    elevs_desc = sorted(unique_elevs, reverse=True)

    # --- Collect all contour lines with their elevations.
    all_lines = []
    line_elev = []
    for _, row in contours_gdf.iterrows():
        el = float(row[elev_col])
        for l in _all_lines(row.geometry):
            if l.is_empty:
                continue
            all_lines.append(l)
            line_elev.append(el)

    if not all_lines:
        return {el: Polygon() for el in unique_elevs}

    line_elev = np.asarray(line_elev, dtype=float)

    # Clip footprints to the corridor boundary only when it is a genuine tight
    # envelope. (For the no-boundary path bnd_poly is itself derived from these
    # contours, so clipping is a harmless no-op.)
    clip_poly = bnd_poly if (bnd_poly is not None and not bnd_poly.is_empty and bnd_poly.area > 0) else None

    def _band_at_or_above(el):
        sel = [all_lines[i] for i in range(len(all_lines)) if line_elev[i] >= (el - 1e-9)]
        if not sel:
            return Polygon()
        u = _robust_union(sel)
        # Morphological close: fuse gaps between adjacent contours into a solid
        # slope band; the large uncontoured interior stays excluded.
        band = u.buffer(close_dist, join_style=1).buffer(-close_dist, join_style=1)
        if not band.is_valid:
            band = band.buffer(0)
        if clip_poly is not None:
            band = band.intersection(clip_poly)
            if not band.is_valid:
                band = band.buffer(0)
        return band if band.geom_type in ('Polygon', 'MultiPolygon') else Polygon()

    footprints = {el: _band_at_or_above(el) for el in unique_elevs}

    # --- Enforce strict nesting: every lower stage contains all higher stages.
    running = None
    for el in elevs_desc:
        fp = footprints[el]
        running = fp if (running is None or running.is_empty) else _robust_union([running, fp])
        if clip_poly is not None:
            running = running.intersection(clip_poly)
            if not running.is_valid:
                running = running.buffer(0)
        footprints[el] = running

    return footprints


def generate_contour_polygons(gdf_utm, elev_col, bnd_line, bnd_poly, has_explicit_bnd,
                              snap_tol=DEFAULT_SNAP_TOL, close_dist=DEFAULT_CLOSE_DIST):
    """
    Step 3: Extract all contour lines with ELEVATION > 0, sort discrete stages at
    0.5 m spacing, and form watertight horizontal footprint polygons P(Z_k)
    confined within the boundary.

      * SOUTH path (explicit boundary + clean rings): topological ring-snap.
      * NORTH path (no boundary / open contours): vector contour polygonization.
    """
    print("\n" + "=" * 80)
    print("STAGE 3: INTERNAL CONTOUR SURFACE SLICING")

    contours_gdf = gdf_utm[gdf_utm[elev_col] > 0.0].copy()
    unique_elevs = sorted(contours_gdf[elev_col].dropna().unique(), reverse=True)
    min_elev = float(unique_elevs[-1])
    max_elev = float(unique_elevs[0])

    print(f"  Contour elevation range: {min_elev:.1f} m (Base) to {max_elev:.1f} m (Crest)")
    print(f"  Number of discrete contour stages: {len(unique_elevs)}")
    print(f"  Elevations: {[round(float(e), 1) for e in sorted(unique_elevs)]}")

    if has_explicit_bnd:
        # An explicit ELEVATION==0 boundary is present. Prefer the clean south
        # ring-snap, but that method requires the internal contours (and the
        # crest in particular) to be CLOSED rings. Cleaned north-style data can
        # carry a proper boundary yet still have OPEN contour polylines, in which
        # case ring-snap cannot form a crest ring. Detect that and fall back to
        # the vector cell-classification footprints, using the real boundary
        # polygon as the corridor envelope (best of both: surveyed boundary +
        # robust open-contour handling).
        try:
            print("  Polygonization method: topological ring-snap (explicit boundary present)")
            cumul_polys, crest_poly = _polygonize_south(contours_gdf, elev_col, bnd_line, unique_elevs, max_elev)
        except ValueError as exc:
            print(f"  Ring-snap could not close contours ({exc})")
            print("  Falling back to bund slope-band footprints (clipped to the explicit boundary).")
            cumul_polys = _build_nested_footprints_vector(
                contours_gdf, elev_col, bnd_poly, bnd_line, unique_elevs,
                snap_tol=snap_tol, close_dist=close_dist
            )
            crest_poly = cumul_polys.get(max_elev, Polygon())
    else:
        print("  Polygonization method: bund slope-band footprints (open contours)")
        cumul_polys = _build_nested_footprints_vector(
            contours_gdf, elev_col, bnd_poly, bnd_line, unique_elevs,
            snap_tol=snap_tol, close_dist=close_dist
        )
        crest_poly = cumul_polys.get(max_elev, Polygon())

    # Drop stages that produced empty geometry (can happen at sparse extremes).
    cumul_polys = {el: p for el, p in cumul_polys.items()
                   if p is not None and (not p.is_empty) and p.area > 0}

    elevs_asc = sorted(cumul_polys.keys())
    print("\n  Verified Watertight Stage Polygons:")
    for el in elevs_asc:
        poly_area = cumul_polys[el].area
        print(f"    Stage {el:5.1f} m: Area = {poly_area:10.2f} m² ({poly_area/10000:.3f} ha)")

    return elevs_asc, cumul_polys, crest_poly


# ---------------------------------------------------------------------------
# STAGE 4: VOLUMETRIC COMPUTATIONS
# ---------------------------------------------------------------------------
def compute_volumetrics(elevs_asc, cumul_polys):
    """
    Step 4: Volumetric & Area Computations.
    Multi-layer Prismoidal Frustum Method across all internal contours:
      V_slice,k = (Delta_h / 3) * (A_k + A_{k+1} + sqrt(A_k * A_{k+1}))
      V_cumul(Z_m) = sum(V_slice,k)
    Engineering cross-check:
      Average End-Area Method: V_endarea,k = (Delta_h / 2) * (A_k + A_{k+1})
    """
    print("\n" + "=" * 80)
    print("STAGE 4: VOLUMETRIC COMPUTATIONS (PRISMOIDAL FRUSTUM VS END-AREA)")

    n_stages = len(elevs_asc)
    areas_m2 = [cumul_polys[el].area for el in elevs_asc]

    stage_records = []
    layer_records = []

    cumul_frustum_vol = 0.0
    cumul_endarea_vol = 0.0

    # Base stage (Stage 0 / ID 1)
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
        dh = round(z_high - z_low, 2)
        a_low = areas_m2[k]
        a_high = areas_m2[k + 1]

        # Frustum Method
        v_frustum = (dh / 3.0) * (a_low + a_high + np.sqrt(a_low * a_high))
        # Average End-Area Method
        v_endarea = (dh / 2.0) * (a_low + a_high)

        diff_vol = v_endarea - v_frustum
        diff_pct = (diff_vol / v_frustum * 100.0) if v_frustum > 0 else 0.0

        cumul_frustum_vol += v_frustum
        cumul_endarea_vol += v_endarea

        stage_depth = round(z_high - base_elev, 2)

        print(f"L{k+1:<5} | {z_low:<9.1f} | {z_high:<10.1f} | {dh:<6.1f} | {v_frustum:<13,.2f} | {v_endarea:<13,.2f} | {diff_vol:<+10.2f} | {cumul_frustum_vol:<18,.2f}")

        # Record for Layer / Slice Shapefile (contour-shaped ring between stages)
        low_poly = cumul_polys[z_low]
        high_poly = cumul_polys[z_high]
        if not low_poly.is_valid:
            low_poly = shapely.make_valid(low_poly)
        if not high_poly.is_valid:
            high_poly = shapely.make_valid(high_poly)
        slice_geom = low_poly.difference(high_poly)
        if not slice_geom.is_valid:
            slice_geom = shapely.make_valid(slice_geom)
        # Coerce to strictly polygonal geometry. A difference of near-equal
        # footprints can collapse to lines/points or a mixed GeometryCollection;
        # keep only the (Multi)Polygon parts so the slice layer stays writable to
        # a POLYGON shapefile.
        slice_geom = _polygonal_only(slice_geom)

        layer_records.append({
            'STAGE_ID': k + 1,
            'Z_LOW': z_low,
            'Z_HIGH': z_high,
            'DELTA_H': dh,
            'AREA_M2': round(slice_geom.area, 2),
            'VOL_M3': round(v_frustum, 2),
            'VOL_CUFT': round(v_frustum * M3_TO_CUFT, 2),
            'CUMUL_M3': round(cumul_frustum_vol, 2),
            'CUM_CUFT': round(cumul_frustum_vol * M3_TO_CUFT, 2),
            'geometry': slice_geom
        })

        # Record for Stage CSV Report
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
            'Cumul_Frustum_Vol_AcreFeet': round(cumul_frustum_vol * M3_TO_ACRE_FEET, 2),
            'Cumul_Frustum_Vol_CuFt': round(cumul_frustum_vol * M3_TO_CUFT, 2),
            'Slice_EndArea_Vol_m3': round(v_endarea, 2),
            'Slice_EndArea_Vol_CuFt': round(v_endarea * M3_TO_CUFT, 2),
            'Cumul_EndArea_Vol_m3': round(cumul_endarea_vol, 2),
            'Cumul_EndArea_Vol_CuFt': round(cumul_endarea_vol * M3_TO_CUFT, 2),
            'Delta_Vol_m3': round(diff_vol, 2),
            'Delta_Percent': round(diff_pct, 2)
        })

    print("-" * 115)
    print(f"TOTAL FRUSTUM VOLUME:       {cumul_frustum_vol:,.2f} m³ ({cumul_frustum_vol * M3_TO_ACRE_FEET:.2f} acre-feet | {cumul_frustum_vol * M3_TO_CUFT:,.2f} ft³)")
    print(f"TOTAL AVERAGE END-AREA:     {cumul_endarea_vol:,.2f} m³ ({cumul_endarea_vol * M3_TO_ACRE_FEET:.2f} acre-feet | {cumul_endarea_vol * M3_TO_CUFT:,.2f} ft³)")
    total_delta = cumul_endarea_vol - cumul_frustum_vol
    denom = cumul_frustum_vol if cumul_frustum_vol > 0 else 1.0
    print(f"COMPARATIVE DELTA:          {total_delta:+,.2f} m³ ({(total_delta / denom) * 100:.2f}%)")
    print("-" * 115)

    df_report = pd.DataFrame(stage_records)

    # Cumulative footprints GeoDataFrame (solid stage polygons)
    cumul_footprint_records = []
    for idx, row in df_report.iterrows():
        st_id = int(row['Stage_ID'])
        el = row['Elevation_m']
        depth = row['Stage_Depth_m']
        cumul_footprint_records.append({
            'STAGE_ID': st_id,
            'Z_LOW': base_elev,
            'Z_HIGH': el,
            'DELTA_H': depth,
            'AREA_M2': round(cumul_polys[el].area, 2),
            'VOL_M3': round(row['Slice_Frustum_Vol_m3'], 2),
            'VOL_CUFT': round(row['Slice_Frustum_Vol_CuFt'], 2),
            'CUMUL_M3': round(row['Cumul_Frustum_Vol_m3'], 2),
            'CUM_CUFT': round(row['Cumul_Frustum_Vol_CuFt'], 2),
            'geometry': cumul_polys[el]
        })

    return layer_records, cumul_footprint_records, df_report


def export_shapefiles_and_csv(region, layer_records, cumul_footprint_records, df_report, output_dir, crs="EPSG:32643"):
    """
    Step 5 & 6: GIS Shapefile Export (.shp only) and Tabular Engineering Report (.csv).
    Strictly NO .geojson files.
    """
    print("\n" + "=" * 80)
    print("STAGE 5 & 6: EXPORTING SHAPEFILES AND CSV ENGINEERING REPORT")
    os.makedirs(output_dir, exist_ok=True)

    gdf_slices = gpd.GeoDataFrame(layer_records, crs=crs)
    # Final safety net: guarantee every slice geometry is strictly polygonal and
    # non-empty before writing to a POLYGON shapefile.
    gdf_slices["geometry"] = gdf_slices["geometry"].apply(_polygonal_only)
    gdf_slices = gdf_slices[~gdf_slices.geometry.is_empty & gdf_slices.geometry.notna()].copy()
    slice_shp_path = os.path.join(output_dir, f"{region}_frustum_slice_polygons.shp")
    gdf_slices.to_file(slice_shp_path, driver="ESRI Shapefile")
    print(f"✓ Saved Slice Polygons Shapefile: {slice_shp_path} ({len(gdf_slices)} features)")

    gdf_cumul = gpd.GeoDataFrame(cumul_footprint_records, crs=crs)
    gdf_cumul["geometry"] = gdf_cumul["geometry"].apply(_polygonal_only)
    gdf_cumul = gdf_cumul[~gdf_cumul.geometry.is_empty & gdf_cumul.geometry.notna()].copy()
    cumul_shp_path = os.path.join(output_dir, f"{region}_frustum_cumulative_polygons.shp")
    gdf_cumul.to_file(cumul_shp_path, driver="ESRI Shapefile")
    print(f"✓ Saved Cumulative Footprints Shapefile: {cumul_shp_path} ({len(gdf_cumul)} features)")

    csv_report_path = os.path.join(output_dir, f"{region}_frustum_volumetric_report.csv")
    df_report.to_csv(csv_report_path, index=False)
    print(f"✓ Saved Tabular Engineering Report: {csv_report_path} ({len(df_report)} records)")

    for f in os.listdir(output_dir):
        if f.lower().endswith(".geojson"):
            os.remove(os.path.join(output_dir, f))
            print(f"Removed disallowed GeoJSON file: {f}")

    return gdf_slices, gdf_cumul, csv_report_path


def generate_visualizations(region, gdf_slices, bnd_poly, crest_poly, df_report, output_dir):
    """
    Step 7: Visualization Deliverables:
    1. <region>_stage_storage_curves.png
    2. <region>_contour_slices_map.png
    """
    print("\n" + "=" * 80)
    print("STAGE 7: GENERATING ENGINEERING VISUALIZATIONS")

    region_title = region.capitalize()
    base_elev = float(df_report['Elevation_m'].iloc[0])
    crest_elev = float(df_report['Elevation_m'].iloc[-1])
    n_stages = len(df_report)
    n_slices = max(n_stages - 1, 0)

    # -------------------------------------------------------------
    # Deliverable 1: Stage-Storage & Stage-Area Engineering Curves
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7), dpi=300)

    elevations = df_report['Elevation_m']
    areas_ha = df_report['Contour_Area_ha']
    cumul_frustum_k_m3 = df_report['Cumul_Frustum_Vol_1000m3']
    cumul_endarea_k_m3 = df_report['Cumul_EndArea_Vol_m3'] / 1000.0

    ax1.plot(areas_ha, elevations, marker='o', color='#1d3557', linewidth=2.4, markersize=5.5, label='Contour Enclosed Area')
    ax1.set_title("Stage-Area Relationship\n(Elevation vs Horizontal Cross-Sectional Area)", fontsize=13, fontweight='bold', pad=12)
    ax1.set_xlabel("Contour Cross-Sectional Area (hectares)", fontsize=11, fontweight='bold')
    ax1.set_ylabel("Stage Elevation (m)", fontsize=11, fontweight='bold')
    ax1.axhline(base_elev, color='#457b9d', linestyle=':', linewidth=1.4, label=f'Corridor Toe / Base ({base_elev:.1f} m)')
    ax1.axhline(crest_elev, color='#e63946', linestyle='--', linewidth=1.5, label=f'Anchor Crest Crown ({crest_elev:.1f} m)')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend(loc='upper right', fontsize=9.5)

    ax1_depth = ax1.secondary_yaxis('right', functions=(lambda z: z - base_elev, lambda d: d + base_elev))
    ax1_depth.set_ylabel("Stage Depth Above Base (m)", fontsize=10, fontweight='bold', color='#1d3557')

    ax2.plot(cumul_frustum_k_m3, elevations, marker='s', color='#2a9d8f', linewidth=2.4, markersize=5.5, label='Prismoidal Frustum Method')
    ax2.plot(cumul_endarea_k_m3, elevations, marker='^', color='#e76f51', linewidth=1.8, linestyle='--', markersize=5.0, label='Average End-Area Method (Check)')
    ax2.set_title("Stage-Storage Capacity Curves\n(Elevation vs Cumulative Volume)", fontsize=13, fontweight='bold', pad=12)
    ax2.set_xlabel("Cumulative Volume (thousand m³)", fontsize=11, fontweight='bold')
    ax2.set_ylabel("Stage Elevation (m)", fontsize=11, fontweight='bold')
    ax2.axhline(crest_elev, color='#e63946', linestyle='--', linewidth=1.5, label=f'Anchor Crest Crown ({crest_elev:.1f} m)')
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend(loc='lower right', fontsize=9.5)

    ax2_acft = ax2.secondary_xaxis('top', functions=(lambda v: v * 1000.0 * M3_TO_ACRE_FEET, lambda af: (af / M3_TO_ACRE_FEET) / 1000.0))
    ax2_acft.set_xlabel("Cumulative Storage (Acre-Feet)", fontsize=10, fontweight='bold', color='#2a9d8f')

    total_vol_frustum = df_report['Cumul_Frustum_Vol_m3'].iloc[-1]
    total_vol_endarea = df_report['Cumul_EndArea_Vol_m3'].iloc[-1]
    diff_pct = ((total_vol_endarea - total_vol_frustum) / total_vol_frustum) * 100.0 if total_vol_frustum > 0 else 0.0

    annotation_text = (
        f"Total Capacity (Crest {crest_elev:.1f}m):\n"
        f"• Frustum: {total_vol_frustum:,.1f} m³ ({total_vol_frustum * M3_TO_ACRE_FEET:.1f} ac-ft | {total_vol_frustum * M3_TO_CUFT:,.0f} ft³)\n"
        f"• End-Area: {total_vol_endarea:,.1f} m³ ({total_vol_endarea * M3_TO_CUFT:,.0f} ft³)\n"
        f"• Variance: +{total_vol_endarea - total_vol_frustum:,.1f} m³ (+{diff_pct:.2f}%)"
    )
    ax2.text(0.05, 0.65, annotation_text, transform=ax2.transAxes, fontsize=9,
             verticalalignment='top', bbox=dict(boxstyle='round,pad=0.5', facecolor='#f8f9fa', edgecolor='#ced4da', alpha=0.9))

    plt.suptitle(f"{region_title} Contour Area: Volumetric Capacity & Stage-Storage Curves", fontsize=15, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])

    curves_path = os.path.join(output_dir, f"{region}_stage_storage_curves.png")
    plt.savefig(curves_path, dpi=300)
    plt.close()
    print(f"✓ Saved Stage-Storage Engineering Curves: {curves_path}")

    # -------------------------------------------------------------
    # Deliverable 2: 2D Thematic Planimetric Map of Internal Slices
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 14), dpi=300)

    gpd.GeoSeries([bnd_poly], crs=gdf_slices.crs).plot(
        ax=ax, color='#f1f5f9', edgecolor='#64748b', linewidth=1.5, linestyle='-', label='Outer Corridor Boundary'
    )

    cmap = plt.colormaps['viridis_r'].resampled(max(len(gdf_slices), 1))
    norm = Normalize(vmin=gdf_slices['Z_LOW'].min(), vmax=gdf_slices['Z_HIGH'].max())

    for idx, row in gdf_slices.iterrows():
        color = cmap(norm((row['Z_LOW'] + row['Z_HIGH']) / 2.0))
        gpd.GeoSeries([row['geometry']], crs=gdf_slices.crs).plot(
            ax=ax, color=color, edgecolor='#334155', linewidth=0.4, alpha=0.9
        )

    gpd.GeoSeries([crest_poly], crs=gdf_slices.crs).plot(
        ax=ax, facecolor='#ef4444', edgecolor='#991b1b', linewidth=2.0, alpha=0.85, label=f'Crest Crown ({crest_elev:.1f} m)'
    )

    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, orientation='horizontal', fraction=0.035, pad=0.06, aspect=30)
    cbar.set_label('Contour Slice Elevation Band (m AOD)', fontsize=11, fontweight='bold')
    cbar.set_ticks(np.arange(np.floor(base_elev), np.ceil(crest_elev) + 1.0, 1.0))

    ax.set_title(f"{region_title} Area: Internal Contour Slices & Corridor Delineation\n"
                 f"({n_stages} Discrete Contour Stages | {n_slices} Prismoidal Slices | {base_elev:.1f} m to {crest_elev:.1f} m)",
                 fontsize=14, fontweight='bold', pad=15)
    ax.set_xlabel("UTM Zone 43N Easting (m)", fontsize=11, fontweight='bold')
    ax.set_ylabel("UTM Zone 43N Northing (m)", fontsize=11, fontweight='bold')
    ax.grid(True, linestyle=':', alpha=0.6, color='#94a3b8')

    x_arrow = 0.94
    y_arrow = 0.92
    ax.annotate('N', xy=(x_arrow, y_arrow), xytext=(x_arrow, y_arrow - 0.05),
                xycoords='axes fraction', ha='center', va='center',
                fontsize=14, fontweight='bold',
                arrowprops=dict(facecolor='black', edgecolor='black', width=3, headwidth=9))

    legend_patches = [
        mpatches.Patch(facecolor='#f1f5f9', edgecolor='#64748b', linewidth=1.2, label=f'Boundary Ring ({bnd_poly.area:,.0f} m²)'),
        mpatches.Patch(facecolor='#ef4444', edgecolor='#991b1b', linewidth=1.5, label=f'Anchor Crest ({crest_poly.area:,.0f} m²)'),
        mpatches.Patch(facecolor='#3b82f6', edgecolor='#1e3a8a', linewidth=0.8, label=f'{n_slices} Frustum Slices ({total_vol_frustum:,.0f} m³)')
    ]
    ax.legend(handles=legend_patches, loc='lower right', fontsize=9.5, framealpha=0.92)

    plt.tight_layout()
    slices_map_path = os.path.join(output_dir, f"{region}_contour_slices_map.png")
    plt.savefig(slices_map_path, dpi=300)
    plt.close()
    print(f"✓ Saved Planimetric Contour Slices Map: {slices_map_path}")


def main():
    args = parse_args()
    input_path = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output_dir)
    region = detect_region(input_path, args.region)

    print("\n" + "#" * 80)
    print(f"FRUSTUM METHOD VOLUMETRIC CALCULATION ({region.upper()} AREA)")
    print(f"Input Shapefile:  {input_path}")
    print(f"Output Directory: {output_dir}")
    print(f"Region Prefix:    {region}")
    print("#" * 80)

    # 1. Coordinate transformation & load data
    gdf_utm, elev_col = load_and_project_data(input_path, target_epsg="EPSG:32643")

    # 2. Delineate outer boundary (explicit or vector-derived)
    bnd_line, bnd_poly, has_explicit_bnd = delineate_boundary(
        gdf_utm, elev_col, snap_tol=args.snap_tol, close_dist=args.close_dist
    )

    # 3. Extract and slice internal contours
    elevs_asc, cumul_polys, crest_poly = generate_contour_polygons(
        gdf_utm, elev_col, bnd_line, bnd_poly, has_explicit_bnd,
        snap_tol=args.snap_tol, close_dist=args.close_dist
    )

    # 4. Compute Prismoidal Frustum & End-Area volumetrics
    layer_records, cumul_footprint_records, df_report = compute_volumetrics(elevs_asc, cumul_polys)

    # 5 & 6. Export Shapefiles (.shp only) and CSV engineering report
    gdf_slices, gdf_cumul, csv_path = export_shapefiles_and_csv(
        region, layer_records, cumul_footprint_records, df_report, output_dir, crs="EPSG:32643"
    )

    # 7. Generate visualizations
    generate_visualizations(region, gdf_slices, bnd_poly, crest_poly, df_report, output_dir)

    print("\n" + "=" * 80)
    print(f"ALL {region.upper()} AREA FRUSTUM CALCULATIONS AND DELIVERABLES COMPLETED SUCCESSFULLY!")
    print(f"Deliverables directory: {output_dir}")
    print("=" * 80 + "\n")


if __name__ == '__main__':
    main()
