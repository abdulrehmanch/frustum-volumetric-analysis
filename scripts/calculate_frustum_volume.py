#!/usr/bin/env python3
"""
calculate_frustum_volume.py

Universal, robust Python script to calculate the multi-layer volumetric capacity
of any contour dataset using the Prismoidal Frustum Method:
    V_slice = (dh / 3) * (A_low + A_high + sqrt(A_low * A_high))

Features:
- Dataset-agnostic: auto-detects CRS, elevation attributes, boundary morphology, and vertical intervals.
- Flexible Column Mapping: options for mapping all columns (--elevation-col, --geometry-col, --boundary-col, --col-map).
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

Standard Input Columns & Mapping Options
-----------------------------------------
The input shapefile requires:

  Column Role   Default Candidates                        CLI Mapping Flags
  -----------   ---------------------------------------   ---------------------------------------------
  Elevation     elevation, elev, contour, z, height,      --elevation-col / --elev-col / -e
                level                                     --col-map elevation=<col>
  Geometry      geometry, geom, shape, the_geom           --geometry-col / --geom-col / -g
                                                          --col-map geometry=<col>
  Boundary      (Optional embedded indicator: ELEV=0.0)   --boundary-col / --bnd-col
  (Embedded)                                              --boundary-val / --bnd-val
                                                          --col-map boundary=<col>,boundary_val=<val>

If any required column is missing, the script halts with a detailed error report
listing available columns, candidates tried, and the exact mapping commands to fix it.
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

# Standard candidate elevation column names (lower-case; used for auto-detection)
STANDARD_ELEV_CANDIDATES = ["elevation", "elev", "contour", "z", "height", "level"]
STANDARD_GEOM_CANDIDATES = ["geometry", "geom", "shape", "the_geom"]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_col_map(col_map_str):
    """Parse key=value pairs from a column mapping string."""
    mapping = {}
    if not col_map_str:
        return mapping
    pairs = [p.strip() for p in col_map_str.replace(";", ",").split(",") if p.strip()]
    for pair in pairs:
        if "=" in pair:
            k, v = pair.split("=", 1)
            mapping[k.strip().lower()] = v.strip()
        elif ":" in pair:
            k, v = pair.split(":", 1)
            mapping[k.strip().lower()] = v.strip()
    return mapping


def parse_args():
    parser = argparse.ArgumentParser(
        description="Universal Contour Prismoidal Frustum Volumetric Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Standard Required Input Columns & Mapping Flags
------------------------------------------------
  --elevation-col / --elev-col / -e   : Elevation column name (or in --col-map)
  --geometry-col  / --geom-col / -g   : Geometry column name (or in --col-map)
  --boundary-col  / --bnd-col         : Embedded boundary attribute column (e.g. TYPE, ELEVATION)
  --boundary-val  / --bnd-val         : Value in boundary column indicating boundary feature (default: 0.0)
  --col-map       / --column-map      : Generic key=val mapping string, e.g. "elevation=Z,geom=the_geom"
        """
    )
    # Required inputs
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

    # Output configuration
    parser.add_argument(
        "--output-dir", "-o",
        default=None,
        help="Target output directory. Defaults to outputs/<site_name>/."
    )
    parser.add_argument(
        "--prefix", "--site-name", "-p", "-s",
        dest="prefix",
        default=None,
        help="Prefix for output filenames. Defaults to shapefile stem in lowercase."
    )

    # Column mapping options for all columns
    col_group = parser.add_argument_group(
        "Column Mapping Options",
        "Override / map input column names if your dataset uses non-standard names."
    )
    col_group.add_argument(
        "--elevation-col", "--elev-col", "-e",
        dest="elev_col",
        default=None,
        help=(
            "Elevation attribute column. Auto-detected from: "
            + " | ".join(STANDARD_ELEV_CANDIDATES)
        )
    )
    col_group.add_argument(
        "--geometry-col", "--geom-col", "-g",
        dest="geom_col",
        default=None,
        help="Geometry column. Defaults to active geometry or 'geometry' / 'geom' / 'shape'."
    )
    col_group.add_argument(
        "--boundary-col", "--bnd-col",
        dest="bnd_col",
        default=None,
        help="Embedded boundary attribute column (e.g., 'TYPE', 'FEATURE', 'ELEVATION')."
    )
    col_group.add_argument(
        "--boundary-val", "--bnd-val",
        dest="bnd_val",
        default=None,
        help="Value in --boundary-col indicating a boundary feature (default: '0.0' or '0')."
    )
    col_group.add_argument(
        "--col-map", "--column-map",
        dest="col_map",
        default=None,
        help="Generic column mapping string, e.g. 'elevation=Z,geom=the_geom,boundary=TYPE,boundary_val=bnd'."
    )

    # Solver & geometric parameters
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


# ---------------------------------------------------------------------------
# COLUMN VALIDATION & MAPPING
# ---------------------------------------------------------------------------

def validate_and_map_columns(gdf, input_path, elev_override=None, geom_override=None,
                             bnd_col_override=None, bnd_val_override=None, col_map_override=None):
    """
    Validate and map all required and optional input columns.

    Parameters
    ----------
    gdf : GeoDataFrame
        The raw GeoDataFrame loaded from the shapefile.
    input_path : str
        Path to the input file.
    elev_override : str or None
        Explicit elevation column from CLI.
    geom_override : str or None
        Explicit geometry column from CLI.
    bnd_col_override : str or None
        Explicit boundary column from CLI.
    bnd_val_override : str or None
        Explicit boundary indicator value.
    col_map_override : str or None
        Generic key=value mapping string.

    Returns
    -------
    mapped_cols : dict
        Dictionary containing mapped column names and boundary value:
        {
            'geometry': <geom_col_name>,
            'elevation': <elev_col_name>,
            'boundary_col': <bnd_col_name_or_None>,
            'boundary_val': <bnd_val_or_None>
        }
    """
    errors = []
    warnings = []
    present_cols = list(gdf.columns)
    col_lower_map = {c.strip().lower(): c for c in present_cols}

    # Parse generic mapping string
    col_map = parse_col_map(col_map_override)

    # ── 1. Resolve Geometry Column ──────────────────────────────────────────
    geom_candidate = (
        geom_override
        or col_map.get("geometry")
        or col_map.get("geom")
        or col_map.get("shape")
        or col_map.get("the_geom")
    )
    resolved_geom_col = None

    if geom_candidate:
        if geom_candidate in present_cols:
            resolved_geom_col = geom_candidate
        elif geom_candidate.lower() in col_lower_map:
            resolved_geom_col = col_lower_map[geom_candidate.lower()]
        else:
            errors.append(
                f"  [MISSING] Geometry column '{geom_candidate}' specified via mapping was not found in file."
            )
    else:
        # Check active geometry or candidate column names
        if hasattr(gdf, "geometry") and gdf.geometry.name in present_cols:
            resolved_geom_col = gdf.geometry.name
        else:
            for gcand in STANDARD_GEOM_CANDIDATES:
                if gcand in col_lower_map:
                    resolved_geom_col = col_lower_map[gcand]
                    break

    if not resolved_geom_col and not errors:
        errors.append(
            "  [MISSING] Geometry column — no standard geometry column ('geometry', 'geom', 'shape') found.\n"
            "            Specify the geometry column with --geometry-col <name> or --col-map geometry=<name>."
        )
    elif resolved_geom_col and gdf[resolved_geom_col].is_empty.all():
        errors.append(
            f"  [INVALID] Geometry column '{resolved_geom_col}' has all empty geometries. Check that the file is not corrupt."
        )

    # ── 2. Resolve Elevation Column ─────────────────────────────────────────
    elev_candidate = (
        elev_override
        or col_map.get("elevation")
        or col_map.get("elev")
        or col_map.get("z")
        or col_map.get("contour")
        or col_map.get("height")
        or col_map.get("level")
    )
    resolved_elev_col = None

    if elev_candidate:
        if elev_candidate in present_cols:
            resolved_elev_col = elev_candidate
        elif elev_candidate.lower() in col_lower_map:
            resolved_elev_col = col_lower_map[elev_candidate.lower()]
        else:
            errors.append(
                f"  [MISSING] Elevation column '{elev_candidate}' specified via mapping was not found in file."
            )
    else:
        # Auto-detection: exact matches first
        for cand in STANDARD_ELEV_CANDIDATES:
            if cand in col_lower_map:
                resolved_elev_col = col_lower_map[cand]
                break

        # Partial matches
        if resolved_elev_col is None:
            for cand in STANDARD_ELEV_CANDIDATES:
                for col in present_cols:
                    if cand in col.lower() and col.lower() != str(resolved_geom_col).lower():
                        resolved_elev_col = col
                        break
                if resolved_elev_col:
                    break

        # Fallback to numeric column with most unique values
        if resolved_elev_col is None:
            numeric_cols = [
                c for c in gdf.select_dtypes(include=[np.number]).columns
                if c != resolved_geom_col
            ]
            if numeric_cols:
                resolved_elev_col = max(numeric_cols, key=lambda c: gdf[c].nunique())
                warnings.append(
                    f"  [WARNING] No standard elevation column name found. "
                    f"Auto-mapped to numeric column with highest variation: '{resolved_elev_col}'. "
                    f"Use --elevation-col <name> to map explicitly if needed."
                )
            else:
                errors.append(
                    "  [MISSING] Elevation column — no numeric or standard elevation column found.\n"
                    "            Standard accepted names:\n"
                    "              " + " | ".join(STANDARD_ELEV_CANDIDATES) + "\n"
                    "            Map your elevation column using: --elevation-col <name> (or --elev-col / -e)."
                )

    # Elevation dtype & validity check
    if resolved_elev_col and resolved_elev_col in present_cols:
        if not pd.api.types.is_numeric_dtype(gdf[resolved_elev_col]):
            # Attempt coercion to numeric
            coerced = pd.to_numeric(gdf[resolved_elev_col], errors="coerce")
            if coerced.notna().sum() > 0:
                warnings.append(
                    f"  [WARNING] Elevation column '{resolved_elev_col}' contains non-numeric strings; coerced valid entries to float."
                )
            else:
                errors.append(
                    f"  [INVALID] Elevation column '{resolved_elev_col}' is non-numeric (dtype: {gdf[resolved_elev_col].dtype}) "
                    f"and could not be converted to numbers."
                )
        elif gdf[resolved_elev_col].isna().all():
            errors.append(
                f"  [INVALID] Elevation column '{resolved_elev_col}' contains only null/NaN values."
            )
        elif gdf[resolved_elev_col].isna().any():
            n_null = int(gdf[resolved_elev_col].isna().sum())
            warnings.append(
                f"  [WARNING] Elevation column '{resolved_elev_col}' has {n_null} null value(s); these features will be ignored."
            )

    # ── 3. Resolve Embedded Boundary Column / Value (Optional) ──────────────
    bnd_col_candidate = (
        bnd_col_override
        or col_map.get("boundary")
        or col_map.get("bnd")
        or col_map.get("boundary_col")
        or col_map.get("bnd_col")
    )
    bnd_val_candidate = (
        bnd_val_override
        or col_map.get("boundary_val")
        or col_map.get("bnd_val")
    )

    resolved_bnd_col = None
    if bnd_col_candidate:
        if bnd_col_candidate in present_cols:
            resolved_bnd_col = bnd_col_candidate
        elif bnd_col_candidate.lower() in col_lower_map:
            resolved_bnd_col = col_lower_map[bnd_col_candidate.lower()]
        else:
            errors.append(
                f"  [MISSING] Boundary column '{bnd_col_candidate}' specified via mapping was not found in file."
            )

    # ── Print warnings (non-fatal) ──────────────────────────────────────────
    for w in warnings:
        print(w)

    # ── Fail fast on errors ─────────────────────────────────────────────────
    if errors:
        sep = "=" * 80
        print(f"\n{sep}")
        print("ERROR: INPUT COLUMN VALIDATION & MAPPING FAILED")
        print(sep)
        print(f"  File : {input_path}")
        print(f"  Total features   : {len(gdf)}")
        print(f"  Columns present  : {present_cols}")
        print()
        print("  Issues encountered:")
        for err in errors:
            print(err)
        print()
        print("  COLUMN MAPPING OPTIONS AVAILABLE:")
        print("  ---------------------------------")
        print("  To map elevation column : --elevation-col <col_name>  (or --elev-col / -e)")
        print("  To map geometry column  : --geometry-col <col_name>   (or --geom-col / -g)")
        print("  To map boundary column  : --boundary-col <col_name>   (and optionally --boundary-val <val>)")
        print("  To map multiple at once : --col-map 'elevation=<col>,geometry=<geom>,boundary=<bnd>'")
        print(sep)
        sys.exit(1)

    return {
        "geometry": resolved_geom_col,
        "elevation": resolved_elev_col,
        "boundary_col": resolved_bnd_col,
        "boundary_val": bnd_val_candidate,
    }


def detect_elevation_column(gdf, override=None):
    """Fallback / helper to detect elevation column."""
    if override:
        if override in gdf.columns:
            return override
        raise ValueError(f"Elevation column '{override}' not found in columns: {list(gdf.columns)}")

    col_lower_map = {c.strip().lower(): c for c in gdf.columns}
    for cand in STANDARD_ELEV_CANDIDATES:
        if cand in col_lower_map:
            return col_lower_map[cand]

    for cand in STANDARD_ELEV_CANDIDATES:
        for col in gdf.columns:
            if cand in col.lower():
                return col

    numeric_cols = [c for c in gdf.select_dtypes(include=[np.number]).columns if c != "geometry"]
    if numeric_cols:
        return max(numeric_cols, key=lambda c: gdf[c].nunique())

    raise ValueError(f"Could not detect elevation column in: {list(gdf.columns)}")


# ---------------------------------------------------------------------------
# GEOMETRY UTILITIES
# ---------------------------------------------------------------------------

def _all_lines(geom):
    """Flatten a (Multi)LineString into a list of LineStrings."""
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return list(geom.geoms)
    if geom.geom_type == "GeometryCollection":
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
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        return geom
    if geom.geom_type == "GeometryCollection":
        polys = [g for g in geom.geoms if g.geom_type in ("Polygon", "MultiPolygon") and g.area > 0]
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


# ---------------------------------------------------------------------------
# STAGE 1: LOAD & PROJECT
# ---------------------------------------------------------------------------

def analyze_and_load(input_path, boundary_path=None, elev_col_override=None, geom_col_override=None,
                     bnd_col_override=None, bnd_val_override=None, col_map_override=None,
                     target_epsg_override=None):
    """Load, validate, map columns, inspect, and project contour and boundary datasets."""
    sep = "=" * 80
    print(sep)
    print("STAGE 1: INPUT DATA ANALYSIS & PROJECTION")
    print(sep)

    if not os.path.exists(input_path):
        print(f"\nERROR: Input file not found: {input_path}")
        sys.exit(1)

    gdf_raw = gpd.read_file(input_path)
    print(f"  File             : {input_path}")
    print(f"  Total features   : {len(gdf_raw)}")
    print(f"  Columns present  : {list(gdf_raw.columns)}")
    print(f"  Source CRS       : {gdf_raw.crs}")

    # Column Mapping & Schema Validation
    mapping = validate_and_map_columns(
        gdf=gdf_raw,
        input_path=input_path,
        elev_override=elev_col_override,
        geom_override=geom_col_override,
        bnd_col_override=bnd_col_override,
        bnd_val_override=bnd_val_override,
        col_map_override=col_map_override,
    )

    geom_col = mapping["geometry"]
    elev_col = mapping["elevation"]
    bnd_col = mapping["boundary_col"]
    bnd_val = mapping["boundary_val"]

    print(f"  Mapped Geometry  : '{geom_col}'")
    print(f"  Mapped Elevation : '{elev_col}' (dtype: {gdf_raw[elev_col].dtype})")
    if bnd_col:
        print(f"  Mapped Boundary  : column '{bnd_col}' (indicator value: '{bnd_val}')")

    # Set active geometry if different
    if gdf_raw.geometry.name != geom_col:
        gdf_raw = gdf_raw.set_geometry(geom_col)

    # Ensure numeric elevations and drop nulls
    gdf_raw[elev_col] = pd.to_numeric(gdf_raw[elev_col], errors="coerce")
    n_before = len(gdf_raw)
    gdf_raw = gdf_raw.dropna(subset=[elev_col]).copy()
    if len(gdf_raw) < n_before:
        print(f"  Dropped {n_before - len(gdf_raw)} feature(s) with invalid/null elevations.")

    # CRS & projection
    if target_epsg_override:
        target_crs = target_epsg_override
    elif gdf_raw.crs is not None and not gdf_raw.crs.is_geographic:
        target_crs = gdf_raw.crs
    else:
        if gdf_raw.crs is None:
            gdf_raw = gdf_raw.set_crs("EPSG:4326")
        target_crs = gdf_raw.estimate_utm_crs()

    print(f"  Projected CRS    : {target_crs}")
    gdf = gdf_raw.to_crs(target_crs)
    gdf["geometry"] = shapely.force_2d(gdf.geometry.values)

    # Elevation summary
    elev_vals = gdf[elev_col].unique()
    print(f"  Elevation range  : {gdf[elev_col].min():.2f} m  →  {gdf[elev_col].max():.2f} m")
    print(f"  Unique elevations: {len(elev_vals)}")

    bnd_poly = None
    bnd_line = None
    if boundary_path and os.path.exists(boundary_path):
        bnd_gdf = gpd.read_file(boundary_path).to_crs(target_crs)
        bnd_poly = clean_polygon(unary_union(bnd_gdf.geometry))
        bnd_line = bnd_poly.boundary
        print(f"  Boundary source  : external file ({boundary_path})")
    else:
        # Detect embedded boundary
        if bnd_col:
            if bnd_val is not None:
                bnd_rows = gdf[gdf[bnd_col].astype(str) == str(bnd_val)]
            else:
                bnd_rows = gdf[gdf[bnd_col].astype(str).str.lower().isin(["boundary", "bnd", "perimeter", "0", "0.0"])]
        else:
            bnd_rows = gdf[gdf[elev_col] == 0.0]

        if len(bnd_rows) > 0 and len(bnd_rows) <= 4:
            geom = bnd_rows.geometry.iloc[0]
            if geom.geom_type in ("Polygon", "MultiPolygon"):
                bnd_poly = clean_polygon(geom)
                bnd_line = bnd_poly.boundary
            elif geom.geom_type == "LineString":
                bnd_line = geom
                bnd_poly = Polygon(geom.coords) if geom.is_closed else Polygon()
            elif geom.geom_type == "MultiLineString":
                bnd_line = unary_union(list(geom.geoms))
                closed = [l for l in geom.geoms if l.is_closed]
                bnd_poly = Polygon(closed[0].coords) if closed else Polygon()

            if bnd_poly is not None and bnd_poly.is_valid and bnd_poly.area > 0:
                print(f"  Boundary source  : auto-detected embedded boundary feature ({bnd_col or elev_col} == {bnd_val if bnd_col else '0.0'})")

    if bnd_poly is not None and bnd_poly.area > 0:
        if bnd_col and bnd_val is not None:
            contours_gdf = gdf[gdf[bnd_col].astype(str) != str(bnd_val)].copy()
        else:
            contours_gdf = gdf[gdf[elev_col] > 0.0].copy()
    else:
        contours_gdf = gdf.copy()
        u_lines = unary_union(contours_gdf.geometry)
        bnd_poly = clean_polygon(u_lines.convex_hull)
        bnd_line = bnd_poly.boundary
        print("  Boundary source  : auto-derived convex envelope from contour extents")

    bnd_poly = clean_polygon(bnd_poly)
    print(f"  Boundary area    : {bnd_poly.area:,.2f} m²  ({bnd_poly.area / 10000.0:.4f} ha)")
    print(f"  Boundary perim.  : {bnd_line.length:,.2f} m")
    print()
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


# ---------------------------------------------------------------------------
# STAGE 2: FOOTPRINT EXTRACTION
# ---------------------------------------------------------------------------

def solve_stage_footprints(contours_gdf, elev_col, bnd_poly, bnd_line, method="auto",
                           close_dist=DEFAULT_CLOSE_DIST, snap_tol=1.0):
    """
    Selects and runs the appropriate solver based on data topology or user choice.
    """
    sep = "=" * 80
    print(sep)
    print("STAGE 2: TOPOLOGICAL CONTOUR SLICING & FOOTPRINT EXTRACTION")
    print(sep)

    unique_elevs = sorted(contours_gdf[elev_col].unique())
    max_elev = max(unique_elevs)
    min_elev = min(unique_elevs)
    print(f"  Elevation range  : {min_elev:.2f} m  →  {max_elev:.2f} m")
    print(f"  Contour stages   : {len(unique_elevs)}")

    # Check crest closure
    crest_rows = contours_gdf[contours_gdf[elev_col] == max_elev]
    crest_lines = []
    for g in crest_rows.geometry:
        crest_lines.extend(_all_lines(g))
    has_closed_crest = any(l.is_ring for l in crest_lines if hasattr(l, "is_ring"))

    # Boundary compactness (isoperimetric quotient)
    bnd_area = bnd_poly.area
    bnd_perim = bnd_line.length
    compactness = (4.0 * np.pi * bnd_area) / (bnd_perim ** 2) if bnd_perim > 0 else 0.0

    # Auto-detection
    if method == "auto":
        if has_closed_crest:
            chosen = "ring"
            reason = "closed crest ring detected → closed basin / pit model"
        elif compactness < 0.1:
            chosen = "band"
            reason = f"elongated corridor morphology (compactness={compactness:.4f} < 0.1) → open bund model"
        else:
            chosen = "split"
            reason = f"compact concession block (compactness={compactness:.4f} >= 0.1) → boundary-cut model"
    else:
        chosen = method
        reason = f"explicitly requested via --method {method}"

    print(f"  Solver           : {chosen.upper()} ({reason})")

    if chosen == "ring":
        try:
            cumul_polys = _solve_ring_snap(contours_gdf, elev_col, bnd_line, unique_elevs, max_elev)
        except Exception as e:
            print(f"  Ring solver error: {e}  → falling back to SPLIT solver.")
            cumul_polys = _solve_boundary_split(contours_gdf, elev_col, bnd_poly, unique_elevs, max_elev)
    elif chosen == "band":
        print(f"  Close distance   : {close_dist:.1f} m")
        cumul_polys = _solve_corridor_band(contours_gdf, elev_col, bnd_poly, unique_elevs, close_dist=close_dist)
    else:
        cumul_polys = _solve_boundary_split(contours_gdf, elev_col, bnd_poly, unique_elevs, max_elev)

    # Drop empty stages
    cumul_polys = {el: clean_polygon(p) for el, p in cumul_polys.items()
                   if p is not None and not p.is_empty and p.area > 0}

    elevs_asc = sorted(cumul_polys.keys())

    # ── Stage table ──────────────────────────────────────────────────────────
    print()
    hdr = f"  {'Stage':>5}  {'Elevation (m)':>13}  {'Area (m²)':>14}  {'Area (ha)':>10}"
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for idx, el in enumerate(elevs_asc, start=1):
        pa = cumul_polys[el].area
        print(f"  {idx:>5}  {el:>13.2f}  {pa:>14,.2f}  {pa / 10000.0:>10.4f}")
    print()

    return elevs_asc, cumul_polys


# ---------------------------------------------------------------------------
# STAGE 3: VOLUMETRICS
# ---------------------------------------------------------------------------

def compute_volumetrics(elevs_asc, stage_polys, bnd_poly, crs_str):
    """
    Calculate multi-layer prismoidal frustum and end-area volumes.
    """
    sep = "=" * 80
    print(sep)
    print("STAGE 3: VOLUMETRIC COMPUTATION (PRISMOIDAL FRUSTUM)")
    print(sep)

    n_stages = len(elevs_asc)
    areas_m2 = [stage_polys[el].area for el in elevs_asc]

    stage_records = []
    layer_records = []

    cumul_frustum_vol = 0.0
    cumul_endarea_vol = 0.0

    base_elev = elevs_asc[0]
    base_area = areas_m2[0]

    stage_records.append({
        "Stage_ID": 1,
        "Elevation_m": base_elev,
        "Stage_Depth_m": 0.0,
        "Contour_Area_m2": round(base_area, 2),
        "Contour_Area_ha": round(base_area / 10000.0, 4),
        "Slice_Frustum_Vol_m3": 0.0,
        "Slice_Frustum_Vol_CuFt": 0.0,
        "Cumul_Frustum_Vol_m3": 0.0,
        "Cumul_Frustum_Vol_1000m3": 0.0,
        "Cumul_Frustum_Vol_AcreFeet": 0.0,
        "Cumul_Frustum_Vol_CuFt": 0.0,
        "Slice_EndArea_Vol_m3": 0.0,
        "Slice_EndArea_Vol_CuFt": 0.0,
        "Cumul_EndArea_Vol_m3": 0.0,
        "Cumul_EndArea_Vol_CuFt": 0.0,
        "Delta_Vol_m3": 0.0,
        "Delta_Percent": 0.0,
    })

    # ── Layer computation table ──────────────────────────────────────────────
    col_w = [6, 10, 11, 7, 14, 14, 11, 19]
    header = (
        f"  {'Layer':<{col_w[0]}} {'Z_Low (m)':<{col_w[1]}} {'Z_High (m)':<{col_w[2]}} "
        f"{'dH (m)':<{col_w[3]}} {'Frustum (m³)':<{col_w[4]}} {'End-Area (m³)':<{col_w[5]}} "
        f"{'Diff (m³)':<{col_w[6]}} {'Cumul Frustum (m³)':<{col_w[7]}}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

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

        print(
            f"  L{k+1:<{col_w[0]-1}} {z_low:<{col_w[1]}.2f} {z_high:<{col_w[2]}.2f} "
            f"{dh:<{col_w[3]}.2f} {v_frustum:<{col_w[4]},.2f} {v_endarea:<{col_w[5]},.2f} "
            f"{diff_vol:<+{col_w[6]}.2f} {cumul_frustum_vol:<{col_w[7]},.2f}"
        )

        slice_geom = clean_polygon(stage_polys[z_low].difference(stage_polys[z_high]))

        layer_records.append({
            "STAGE_ID": k + 1,
            "Z_LOW": z_low,
            "Z_HIGH": z_high,
            "DELTA_H": dh,
            "A_LOW_M2": round(a_low, 2),
            "A_HIGH_M2": round(a_high, 2),
            "VOL_M3": round(v_frustum, 2),
            "VOL_CUFT": round(v_frustum * M3_TO_CUFT, 2),
            "CUMUL_M3": round(cumul_frustum_vol, 2),
            "CUM_CUFT": round(cumul_frustum_vol * M3_TO_CUFT, 2),
            "geometry": slice_geom,
        })

        stage_records.append({
            "Stage_ID": k + 2,
            "Elevation_m": z_high,
            "Stage_Depth_m": stage_depth,
            "Contour_Area_m2": round(a_high, 2),
            "Contour_Area_ha": round(a_high / 10000.0, 4),
            "Slice_Frustum_Vol_m3": round(v_frustum, 2),
            "Slice_Frustum_Vol_CuFt": round(v_frustum * M3_TO_CUFT, 2),
            "Cumul_Frustum_Vol_m3": round(cumul_frustum_vol, 2),
            "Cumul_Frustum_Vol_1000m3": round(cumul_frustum_vol / 1000.0, 3),
            "Cumul_Frustum_Vol_AcreFeet": round(cumul_frustum_vol * M3_TO_ACRE_FEET, 3),
            "Cumul_Frustum_Vol_CuFt": round(cumul_frustum_vol * M3_TO_CUFT, 2),
            "Slice_EndArea_Vol_m3": round(v_endarea, 2),
            "Slice_EndArea_Vol_CuFt": round(v_endarea * M3_TO_CUFT, 2),
            "Cumul_EndArea_Vol_m3": round(cumul_endarea_vol, 2),
            "Cumul_EndArea_Vol_CuFt": round(cumul_endarea_vol * M3_TO_CUFT, 2),
            "Delta_Vol_m3": round(diff_vol, 2),
            "Delta_Percent": round(diff_pct, 3),
        })

    cumul_records = []
    for idx, el in enumerate(elevs_asc):
        cumul_records.append({
            "STAGE_ID": idx + 1,
            "ELEVATION": el,
            "AREA_M2": round(stage_polys[el].area, 2),
            "AREA_HA": round(stage_polys[el].area / 10000.0, 4),
            "DEPTH_M": round(el - base_elev, 2),
            "geometry": stage_polys[el],
        })

    report_df = pd.DataFrame(stage_records)
    layers_gdf = gpd.GeoDataFrame(layer_records, crs=crs_str)
    cumul_gdf = gpd.GeoDataFrame(cumul_records, crs=crs_str)

    # ── Volume totals ────────────────────────────────────────────────────────
    print("  " + "-" * (len(header) - 2))
    print(f"\n  Total Frustum Volume   : {cumul_frustum_vol:>15,.2f} m³")
    print(f"                           {cumul_frustum_vol * M3_TO_CUFT:>15,.2f} cu ft")
    print(f"                           {cumul_frustum_vol * M3_TO_ACRE_FEET:>15,.3f} acre-ft")
    print(f"  Total End-Area Volume  : {cumul_endarea_vol:>15,.2f} m³")
    diff_tot = cumul_endarea_vol - cumul_frustum_vol
    diff_pct_tot = (diff_tot / cumul_frustum_vol * 100.0) if cumul_frustum_vol > 0 else 0.0
    print(f"  Difference (EA - F)    : {diff_tot:>+15,.2f} m³  ({diff_pct_tot:+.3f}%)")
    print()

    return report_df, layers_gdf, cumul_gdf, cumul_frustum_vol, cumul_endarea_vol


# ---------------------------------------------------------------------------
# STAGE 4: EXPORT
# ---------------------------------------------------------------------------

def export_deliverables(output_dir, prefix, report_df, layers_gdf, cumul_gdf, bnd_poly):
    """
    Write all 5 standard engineering deliverables.
    """
    sep = "=" * 80
    print(sep)
    print("STAGE 4: EXPORTING DELIVERABLES")
    print(sep)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Frustum slice polygons shapefile
    slice_shp = os.path.join(output_dir, f"{prefix}_frustum_slice_polygons.shp")
    layers_gdf.to_file(slice_shp)
    print(f"  [1/5] Slice polygons shapefile       : {slice_shp}")

    # 2. Cumulative stage footprints shapefile
    cumul_shp = os.path.join(output_dir, f"{prefix}_frustum_cumulative_polygons.shp")
    cumul_gdf.to_file(cumul_shp)
    print(f"  [2/5] Cumulative polygons shapefile  : {cumul_shp}")

    # 3. CSV Report
    report_csv = os.path.join(output_dir, f"{prefix}_frustum_volumetric_report.csv")
    report_df.to_csv(report_csv, index=False)
    print(f"  [3/5] Volumetric schedule CSV        : {report_csv}")

    # 4. Stage-Storage Curves Plot
    curves_png = os.path.join(output_dir, f"{prefix}_stage_storage_curves.png")
    fig, ax1 = plt.subplots(figsize=(10, 6), dpi=300)
    elevations = report_df["Elevation_m"]
    areas = report_df["Contour_Area_m2"]
    vols = report_df["Cumul_Frustum_Vol_m3"]

    color1 = "#1f77b4"
    ax1.set_xlabel("Contour Elevation (m)", fontweight="bold")
    ax1.set_ylabel("Stage Footprint Area (m²)", color=color1, fontweight="bold")
    line1 = ax1.plot(elevations, areas, color=color1, marker="o", markersize=3, label="Stage Area (m²)", linewidth=2)
    ax1.tick_params(axis="y", labelcolor=color1)
    ax1.grid(True, linestyle="--", alpha=0.5)

    ax2 = ax1.twinx()
    color2 = "#d62728"
    ax2.set_ylabel("Cumulative Frustum Volume (m³)", color=color2, fontweight="bold")
    line2 = ax2.plot(elevations, vols, color=color2, marker="s", markersize=3, label="Cumul. Volume (m³)", linewidth=2)
    ax2.tick_params(axis="y", labelcolor=color2)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax1.legend(lines, labels, loc="center left", framealpha=0.9)
    plt.title(f"Stage-Area & Stage-Storage Curves — {prefix.upper()}", fontweight="bold", pad=12)
    fig.tight_layout()
    plt.savefig(curves_png)
    plt.close()
    print(f"  [4/5] Stage-storage curves plot      : {curves_png}")

    # 5. Planimetric 2D Slices Map
    map_png = os.path.join(output_dir, f"{prefix}_contour_slices_map.png")
    fig, ax = plt.subplots(figsize=(10, 8), dpi=300)
    norm = Normalize(vmin=cumul_gdf["ELEVATION"].min(), vmax=cumul_gdf["ELEVATION"].max())
    cmap = cm.viridis

    for _, row in cumul_gdf.sort_values("ELEVATION", ascending=True).iterrows():
        color = cmap(norm(row["ELEVATION"]))
        g = row.geometry
        if g.geom_type == "Polygon":
            ax.plot(*g.exterior.xy, color=color, linewidth=1.2)
        elif g.geom_type == "MultiPolygon":
            for p in g.geoms:
                ax.plot(*p.exterior.xy, color=color, linewidth=1.2)

    if bnd_poly.geom_type == "Polygon":
        ax.plot(*bnd_poly.exterior.xy, color="black", linewidth=2.0, linestyle="--", label="Boundary")
    elif bnd_poly.geom_type == "MultiPolygon":
        for p in bnd_poly.geoms:
            ax.plot(*p.exterior.xy, color="black", linewidth=2.0, linestyle="--", label="Boundary")

    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Contour Elevation (m)", fontweight="bold")

    ax.set_aspect("equal", "box")
    ax.set_title(f"Watertight Contour Stage Footprints — {prefix.upper()}", fontweight="bold", pad=12)
    ax.set_xlabel("UTM Easting (m)", fontweight="bold")
    ax.set_ylabel("UTM Northing (m)", fontweight="bold")
    ax.grid(True, linestyle=":", alpha=0.6)
    fig.tight_layout()
    plt.savefig(map_png)
    plt.close()
    print(f"  [5/5] Planimetric contour slices map : {map_png}")
    print()


# ---------------------------------------------------------------------------
# SUMMARY BLOCK
# ---------------------------------------------------------------------------

def print_summary(input_path, output_dir, prefix, elev_col,
                  cumul_frustum_vol, cumul_endarea_vol, n_stages,
                  elev_min, elev_max, bnd_area_m2):
    """Print a structured SUMMARY block for easy parsing / downstream ingestion."""
    sep = "=" * 80
    print(sep)
    print("SUMMARY")
    print(sep)
    print(f"  input_file              : {input_path}")
    print(f"  elevation_column        : {elev_col}")
    print(f"  output_directory        : {output_dir}")
    print(f"  output_prefix           : {prefix}")
    print(f"  contour_stages          : {n_stages}")
    print(f"  elevation_min_m         : {elev_min:.2f}")
    print(f"  elevation_max_m         : {elev_max:.2f}")
    print(f"  boundary_area_m2        : {bnd_area_m2:,.2f}")
    print(f"  boundary_area_ha        : {bnd_area_m2 / 10000.0:.4f}")
    print(f"  total_frustum_vol_m3    : {cumul_frustum_vol:,.2f}")
    print(f"  total_frustum_vol_cuft  : {cumul_frustum_vol * M3_TO_CUFT:,.2f}")
    print(f"  total_frustum_vol_acft  : {cumul_frustum_vol * M3_TO_ACRE_FEET:.3f}")
    print(f"  total_endarea_vol_m3    : {cumul_endarea_vol:,.2f}")
    diff = cumul_endarea_vol - cumul_frustum_vol
    diff_pct = (diff / cumul_frustum_vol * 100.0) if cumul_frustum_vol > 0 else 0.0
    print(f"  method_diff_m3          : {diff:+,.2f}")
    print(f"  method_diff_percent     : {diff_pct:+.3f}")
    print(sep)
    print("STATUS: SUCCESS — all deliverables generated.")
    print(sep)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    input_path = os.path.abspath(args.input)

    input_stem = os.path.splitext(os.path.basename(input_path))[0]
    prefix = args.prefix.strip().lower() if args.prefix else input_stem.lower()

    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        parent_dir = os.path.dirname(input_path)
        site_name = os.path.basename(parent_dir)
        grandparent_dir = os.path.dirname(parent_dir)
        grandparent_name = os.path.basename(grandparent_dir).lower()
        if grandparent_name in ("inputs", "input"):
            project_root = os.path.dirname(grandparent_dir)
            output_dir = os.path.join(project_root, "outputs", site_name)
        elif site_name.lower() in ("input", "inputs"):
            output_dir = os.path.join(grandparent_dir, "outputs")
        else:
            output_dir = os.path.join(parent_dir, "outputs", site_name)

    # ── Pipeline ─────────────────────────────────────────────────────────────
    gdf, contours_gdf, elev_col, bnd_poly, bnd_line, crs_str = analyze_and_load(
        input_path=input_path,
        boundary_path=args.boundary,
        elev_col_override=args.elev_col,
        geom_col_override=args.geom_col,
        bnd_col_override=args.bnd_col,
        bnd_val_override=args.bnd_val,
        col_map_override=args.col_map,
        target_epsg_override=args.target_epsg,
    )

    elevs_asc, stage_polys = solve_stage_footprints(
        contours_gdf=contours_gdf,
        elev_col=elev_col,
        bnd_poly=bnd_poly,
        bnd_line=bnd_line,
        method=args.method,
        close_dist=args.close_dist,
        snap_tol=args.snap_tol,
    )

    report_df, layers_gdf, cumul_gdf, cumul_frustum_vol, cumul_endarea_vol = compute_volumetrics(
        elevs_asc=elevs_asc,
        stage_polys=stage_polys,
        bnd_poly=bnd_poly,
        crs_str=crs_str,
    )

    export_deliverables(
        output_dir=output_dir,
        prefix=prefix,
        report_df=report_df,
        layers_gdf=layers_gdf,
        cumul_gdf=cumul_gdf,
        bnd_poly=bnd_poly,
    )

    print_summary(
        input_path=input_path,
        output_dir=output_dir,
        prefix=prefix,
        elev_col=elev_col,
        cumul_frustum_vol=cumul_frustum_vol,
        cumul_endarea_vol=cumul_endarea_vol,
        n_stages=len(elevs_asc),
        elev_min=elevs_asc[0],
        elev_max=elevs_asc[-1],
        bnd_area_m2=bnd_poly.area,
    )


if __name__ == "__main__":
    main()
