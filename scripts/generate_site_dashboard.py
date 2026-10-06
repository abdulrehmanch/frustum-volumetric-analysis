#!/usr/bin/env python3
"""
generate_site_dashboard.py

Standardized Assignment Dashboard Generator for MMD Frustum Volumetric Analysis.
Auto-generates outputs/<site_name>/index.html with the exact dark-themed engineering
design system proven on DG Khan Pits. Supports both single-viewer sites and
multi-pit/multi-block sites.
"""

import os
import csv
import glob
import json

M3_TO_CUFT = 35.31466672148859
M3_TO_ACRE_FEET = 0.000810713194


def fmt(n, d=0):
    """Format number with thousands separators."""
    if n is None or n == "" or n == "—":
        return "—"
    try:
        val = float(n)
        return f"{val:,.{d}f}" if d > 0 else f"{val:,.0f}"
    except Exception:
        return str(n)


def discover_site_units(site_dir):
    """
    Discover all viewer units in a site directory.
    Returns a list of dicts with unit metadata, files, and metrics.
    """
    site_dir = os.path.abspath(site_dir)
    units = []

    # Check direct site_dir for viewer_data.geojson
    direct_geojson = os.path.join(site_dir, "viewer_data.geojson")
    if os.path.exists(direct_geojson):
        unit = _parse_unit_dir(site_dir, rel_prefix="")
        if unit:
            units.append(unit)
    else:
        # Check subdirectories (e.g. pit_1, pit_2_merged)
        for entry in sorted(os.scandir(site_dir), key=lambda e: e.name):
            if entry.is_dir() and not entry.name.startswith("."):
                sub_geojson = os.path.join(entry.path, "viewer_data.geojson")
                if os.path.exists(sub_geojson):
                    unit = _parse_unit_dir(entry.path, rel_prefix=entry.name + "/")
                    if unit:
                        units.append(unit)

    return units


def _parse_unit_dir(unit_dir, rel_prefix=""):
    """Parse metadata from a directory containing viewer_data.geojson and deliverables."""
    geojson_path = os.path.join(unit_dir, "viewer_data.geojson")
    if not os.path.exists(geojson_path):
        return None

    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            props = data.get("properties", {})
    except Exception:
        props = {}

    unit_name = os.path.basename(unit_dir)
    prefix = props.get("prefix", unit_name)

    # Find 3D viewer HTML
    viewers = glob.glob(os.path.join(unit_dir, "*_3d_viewer.html"))
    if not viewers:
        viewers = glob.glob(os.path.join(unit_dir, "*viewer*.html"))
    viewer_file = os.path.basename(viewers[0]) if viewers else "3d_viewer.html"

    # Find CSV report
    reports = glob.glob(os.path.join(unit_dir, "*frustum_volumetric_report.csv"))
    if not reports:
        reports = glob.glob(os.path.join(unit_dir, "*.csv"))
    report_file = os.path.basename(reports[0]) if reports else None

    # Find PNG curves and maps
    curves = glob.glob(os.path.join(unit_dir, "*stage_storage_curves.png"))
    curves_file = os.path.basename(curves[0]) if curves else None

    maps = glob.glob(os.path.join(unit_dir, "*contour_slices_map.png"))
    maps_file = os.path.basename(maps[0]) if maps else None

    # Load schedule table from CSV if available using built-in csv reader
    schedule_rows = []
    endarea_vol_m3 = None
    if report_file and os.path.exists(os.path.join(unit_dir, report_file)):
        try:
            with open(os.path.join(unit_dir, report_file), "r", encoding="utf-8") as rf:
                reader = csv.DictReader(rf)
                for r in reader:
                    ea_val = r.get("Cumul_EndArea_Vol_m3")
                    if ea_val:
                        try:
                            f_val = float(ea_val)
                            if endarea_vol_m3 is None or f_val > endarea_vol_m3:
                                endarea_vol_m3 = f_val
                        except ValueError:
                            pass

                    schedule_rows.append({
                        "stage_id": int(float(r.get("Stage_ID", 0))),
                        "elevation": float(r.get("Elevation_m", 0.0)),
                        "depth": float(r.get("Stage_Depth_m", 0.0)),
                        "area_m2": float(r.get("Contour_Area_m2", 0.0)),
                        "vol_m3": float(r.get("Slice_Frustum_Vol_m3", 0.0)),
                        "vol_cuft": float(r.get("Slice_Frustum_Vol_CuFt", 0.0)),
                        "cum_m3": float(r.get("Cumul_Frustum_Vol_m3", 0.0)),
                        "cum_cuft": float(r.get("Cumul_Frustum_Vol_CuFt", 0.0)),
                        "diff_pct": float(r.get("Delta_Percent", 0.0)),
                    })
        except Exception:
            pass

    vol_m3 = float(props.get("total_vol_m3", 0.0))
    vol_cuft = float(props.get("total_vol_cuft", vol_m3 * M3_TO_CUFT))
    if endarea_vol_m3 is None:
        endarea_vol_m3 = vol_m3 * 1.004

    var_pct = ((endarea_vol_m3 - vol_m3) / vol_m3 * 100.0) if vol_m3 > 0 else 0.0

    # Derive area from base/crest features if available
    area_m2 = schedule_rows[0]["area_m2"] if schedule_rows else 0.0
    if area_m2 == 0.0 and "bounds" in props:
        b = props["bounds"]
        area_m2 = (b[2] - b[0]) * 111000 * (b[3] - b[1]) * 111000 * 0.4

    return {
        "unit_name": unit_name,
        "title": unit_name.replace("_", " ").title(),
        "rel_prefix": rel_prefix,
        "viewer_rel": rel_prefix + viewer_file,
        "report_rel": (rel_prefix + report_file) if report_file else None,
        "curves_rel": (rel_prefix + curves_file) if curves_file else None,
        "maps_rel": (rel_prefix + maps_file) if maps_file else None,
        "base_elev": float(props.get("base_elev", 0.0)),
        "crest_elev": float(props.get("crest_elev", 0.0)),
        "total_depth_m": float(props.get("total_depth_m", 0.0)),
        "num_slices": int(props.get("num_slices", len(schedule_rows))),
        "vol_m3": vol_m3,
        "vol_cuft": vol_cuft,
        "vol_acft": float(props.get("total_vol_acft", vol_m3 * M3_TO_ACRE_FEET)),
        "endarea_vol_m3": endarea_vol_m3,
        "endarea_vol_cuft": endarea_vol_m3 * M3_TO_CUFT,
        "var_pct": var_pct,
        "area_m2": area_m2,
        "center_lat": props.get("center_lat"),
        "center_lon": props.get("center_lon"),
        "schedule": schedule_rows,
    }


def generate_site_dashboard(site_dir, output_file=None):
    """
    Generate outputs/<site_name>/index.html for a given site directory.
    Returns path to generated file and summary metrics.
    """
    site_dir = os.path.abspath(site_dir)
    site_name = os.path.basename(site_dir)
    if output_file is None:
        output_file = os.path.join(site_dir, "index.html")

    units = discover_site_units(site_dir)
    if not units:
        print(f"  [WARN] No viewer units found in {site_dir}; skipping dashboard.")
        return None

    # Calculate aggregate site totals
    tot_vol_m3 = sum(u["vol_m3"] for u in units)
    tot_vol_cuft = sum(u["vol_cuft"] for u in units)
    tot_vol_acft = sum(u["vol_acft"] for u in units)
    tot_area_m2 = sum(u["area_m2"] for u in units)
    tot_slices = sum(u["num_slices"] for u in units)
    tot_endarea_m3 = sum(u["endarea_vol_m3"] for u in units)
    tot_endarea_cuft = sum(u["endarea_vol_cuft"] for u in units)
    overall_var_pct = ((tot_endarea_m3 - tot_vol_m3) / tot_vol_m3 * 100.0) if tot_vol_m3 > 0 else 0.0

    site_title = site_name.replace("_", " ").title()
    is_multi_unit = len(units) > 1

    # Format HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{site_title} — Volumetric Analysis & 3D WebGIS</title>
    <style>
        :root {{
            --bg-primary: #0f172a;
            --bg-card: #1e293b;
            --text-primary: #f8fafc;
            --text-muted: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-emerald: #34d399;
            --accent-amber: #fbbf24;
            --border-color: #334155;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 2.5rem 1.5rem;
        }}
        .container {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .nav-back {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--accent-blue);
            text-decoration: none;
            font-size: 0.9rem;
            font-weight: 500;
            margin-bottom: 1.5rem;
            transition: color 0.15s ease;
        }}
        .nav-back:hover {{
            color: #7dd3fc;
            text-decoration: underline;
        }}
        header {{
            margin-bottom: 2.5rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.5rem;
        }}
        h1 {{
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-primary);
            margin-bottom: 0.5rem;
        }}
        .subtitle {{
            color: var(--text-muted);
            font-size: 1rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 1.25rem;
            margin-bottom: 2.5rem;
        }}
        .stat-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 1.25rem;
        }}
        .stat-label {{
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            margin-bottom: 0.25rem;
        }}
        .stat-value {{
            font-size: 1.75rem;
            font-weight: 700;
            color: var(--accent-blue);
        }}
        .stat-sub {{
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 0.25rem;
        }}
        .viewers-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2.5rem;
        }}
        .viewer-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.75rem;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }}
        .viewer-title {{
            font-size: 1.25rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 0.5rem;
        }}
        .viewer-meta {{
            color: var(--text-muted);
            font-size: 0.9rem;
            margin-bottom: 1rem;
        }}
        .metric-row {{
            display: flex;
            justify-content: space-between;
            padding: 0.35rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            font-size: 0.9rem;
        }}
        .metric-label {{ color: var(--text-muted); }}
        .metric-val {{ font-weight: 600; color: var(--text-primary); }}
        .btn-view {{
            display: block;
            text-align: center;
            background: linear-gradient(135deg, #0284c7, #0369a1);
            color: white;
            text-decoration: none;
            padding: 0.75rem 1rem;
            border-radius: 0.5rem;
            font-weight: 600;
            margin-top: 1.25rem;
            transition: all 0.2s ease;
        }}
        .btn-view:hover {{
            background: linear-gradient(135deg, #38bdf8, #0284c7);
            transform: translateY(-1px);
        }}
        .toolbar {{
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-bottom: 2.5rem;
        }}
        .btn-tool {{
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            padding: 0.6rem 1rem;
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            color: var(--text-primary);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.15s ease;
        }}
        .btn-tool:hover {{
            background-color: #334155;
            border-color: var(--accent-blue);
            color: var(--accent-blue);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            background-color: var(--bg-card);
            border-radius: 0.75rem;
            overflow: hidden;
            border: 1px solid var(--border-color);
            margin-bottom: 2rem;
        }}
        th, td {{
            padding: 0.85rem 1rem;
            text-align: left;
            font-size: 0.9rem;
        }}
        th {{
            background-color: rgba(255,255,255,0.04);
            color: var(--text-muted);
            font-weight: 600;
            border-bottom: 1px solid var(--border-color);
        }}
        tr:not(:last-child) td {{
            border-bottom: 1px solid var(--border-color);
        }}
        .badge {{
            display: inline-block;
            padding: 0.2rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            font-weight: 600;
            background: rgba(52, 211, 153, 0.15);
            color: var(--accent-emerald);
        }}
    </style>
</head>
<body>
    <div class="container">
        <a href="../index.html" class="nav-back">&larr; Back to All Project Assignments</a>

        <header>
            <h1>{site_title}</h1>
            <p class="subtitle">Prismoidal Frustum Volumetric Capacity & 3D WebGIS Inspection</p>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Volume</div>
                <div class="stat-value">{fmt(tot_vol_m3)} m³</div>
                <div class="stat-sub">{fmt(tot_vol_cuft)} cu ft &bull; {fmt(tot_vol_acft, 2)} ac·ft</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Footprint Area</div>
                <div class="stat-value">{fmt(tot_area_m2)} m²</div>
                <div class="stat-sub">{fmt(tot_area_m2 / 10000.0, 3)} hectares</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Active Stages</div>
                <div class="stat-value">{tot_slices} Layers</div>
                <div class="stat-sub">{len(units)} viewer {'entities' if is_multi_unit else 'entity'}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Method Variance</div>
                <div class="stat-value">{overall_var_pct:+.2f}%</div>
                <div class="stat-sub">Frustum vs End-Area cross-check</div>
            </div>
        </div>

        <h2 style="font-size: 1.35rem; margin-bottom: 1rem;">Interactive 3D WebGIS Viewers</h2>
        <div class="viewers-grid">
"""

    for u in units:
        html += f"""            <div class="viewer-card">
                <div>
                    <div class="viewer-title">{u['title']}</div>
                    <div class="viewer-meta">Elevations {u['base_elev']:.1f}m &rarr; {u['crest_elev']:.1f}m ({u['total_depth_m']:.1f}m Depth)</div>
                    <div class="metric-row"><span class="metric-label">Frustum Volume</span><span class="metric-val">{fmt(u['vol_m3'])} m³</span></div>
                    <div class="metric-row"><span class="metric-label">Cubic Feet</span><span class="metric-val">{fmt(u['vol_cuft'])} cu ft</span></div>
                    <div class="metric-row"><span class="metric-label">Footprint Area</span><span class="metric-val">{fmt(u['area_m2'])} m²</span></div>
                    <div class="metric-row"><span class="metric-label">Contour Stages</span><span class="metric-val">{u['num_slices']} stages</span></div>
                    <div class="metric-row"><span class="metric-label">Variance</span><span class="metric-val badge">{u['var_pct']:+.2f}%</span></div>
                </div>
                <a href="{u['viewer_rel']}" class="btn-view">Launch 3D WebGIS Viewer &rarr;</a>
            </div>
"""

    html += """        </div>

        <h2 style="font-size: 1.35rem; margin-bottom: 1rem;">Deliverables & Engineering Assets</h2>
        <div class="toolbar">
"""

    # Deliverables Toolbar
    for u in units:
        pfx = f"[{u['title']}] " if is_multi_unit else ""
        if u["report_rel"]:
            html += f"""            <a href="{u['report_rel']}" class="btn-tool" download>&darr; {pfx}Volumetric Schedule (CSV)</a>\n"""
        if u["curves_rel"]:
            html += f"""            <a href="{u['curves_rel']}" class="btn-tool" target="_blank">&#128200; {pfx}Stage-Storage Curves (PNG)</a>\n"""
        if u["maps_rel"]:
            html += f"""            <a href="{u['maps_rel']}" class="btn-tool" target="_blank">&#128506; {pfx}Planimetric Slices Map (PNG)</a>\n"""

    html += """        </div>

        <h2 style="font-size: 1.35rem; margin-bottom: 1rem;">Engineering Volumetric Schedule</h2>
        <table>
            <thead>
                <tr>
"""

    if is_multi_unit:
        # Multi-unit table
        html += """                    <th>Unit Designation</th>
                    <th>Elev. Base</th>
                    <th>Elev. Crest</th>
                    <th>Depth (m)</th>
                    <th>Area (m²)</th>
                    <th>Frustum Vol (m³)</th>
                    <th>Frustum Vol (cu ft)</th>
                    <th>End-Area Vol (cu ft)</th>
                    <th>Variance</th>
                </tr>
            </thead>
            <tbody>
"""
        for u in units:
            html += f"""                <tr>
                    <td><strong>{u['title']}</strong></td>
                    <td>{u['base_elev']:.2f} m</td>
                    <td>{u['crest_elev']:.2f} m</td>
                    <td>{u['total_depth_m']:.1f} m</td>
                    <td>{fmt(u['area_m2'])} m²</td>
                    <td><strong>{fmt(u['vol_m3'])} m³</strong></td>
                    <td><strong>{fmt(u['vol_cuft'])} cu ft</strong></td>
                    <td>{fmt(u['endarea_vol_cuft'])} cu ft</td>
                    <td><span class="badge">{u['var_pct']:+.2f}%</span></td>
                </tr>
"""
        html += f"""                <tr style="background: rgba(56, 189, 248, 0.08); font-weight: 700;">
                    <td>GRAND TOTAL</td>
                    <td>—</td>
                    <td>—</td>
                    <td>—</td>
                    <td>{fmt(tot_area_m2)} m²</td>
                    <td><strong>{fmt(tot_vol_m3)} m³</strong></td>
                    <td><strong>{fmt(tot_vol_cuft)} cu ft</strong></td>
                    <td>{fmt(tot_endarea_cuft)} cu ft</td>
                    <td><span class="badge">{overall_var_pct:+.2f}%</span></td>
                </tr>
            </tbody>
        </table>
"""
    else:
        # Single unit stage table
        u = units[0]
        html += """                    <th>Stage</th>
                    <th>Elevation (m)</th>
                    <th>Depth (m)</th>
                    <th>Footprint (m²)</th>
                    <th>Slice Vol (m³)</th>
                    <th>Slice (cu ft)</th>
                    <th>Cumul Vol (m³)</th>
                    <th>Cumul (cu ft)</th>
                    <th>Diff %</th>
                </tr>
            </thead>
            <tbody>
"""
        for s in u["schedule"]:
            html += f"""                <tr>
                    <td>L{s['stage_id']}</td>
                    <td>{s['elevation']:.2f} m</td>
                    <td>{s['depth']:.2f} m</td>
                    <td>{fmt(s['area_m2'])} m²</td>
                    <td>{fmt(s['vol_m3'])} m³</td>
                    <td>{fmt(s['vol_cuft'])} cu ft</td>
                    <td><strong>{fmt(s['cum_m3'])} m³</strong></td>
                    <td><strong>{fmt(s['cum_cuft'])} cu ft</strong></td>
                    <td><span class="badge">{s['diff_pct']:+.2f}%</span></td>
                </tr>
"""
        html += f"""                <tr style="background: rgba(56, 189, 248, 0.08); font-weight: 700;">
                    <td colspan="3">TOTAL CAPACITY</td>
                    <td>{fmt(u['area_m2'])} m²</td>
                    <td>—</td>
                    <td>—</td>
                    <td><strong>{fmt(u['vol_m3'])} m³</strong></td>
                    <td><strong>{fmt(u['vol_cuft'])} cu ft</strong></td>
                    <td><span class="badge">{u['var_pct']:+.2f}%</span></td>
                </tr>
            </tbody>
        </table>
"""

    html += """    </div>
</body>
</html>
"""

    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  ✓ Generated dashboard: {output_file}")
    return {
        "site_name": site_name,
        "title": site_title,
        "rel_dir": site_name,
        "index_rel": f"{site_name}/index.html",
        "units": units,
        "total_vol_m3": tot_vol_m3,
        "total_vol_cuft": tot_vol_cuft,
        "total_vol_acft": tot_vol_acft,
        "total_area_m2": tot_area_m2,
        "total_slices": tot_slices,
        "overall_var_pct": overall_var_pct,
        "center_lat": units[0]["center_lat"] if units else None,
        "center_lon": units[0]["center_lon"] if units else None,
    }


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "outputs/dg_khan_pits"
    res = generate_site_dashboard(target)
    if res:
        print(f"Done: {res['title']} -> {res['total_vol_m3']:,.2f} m³")
