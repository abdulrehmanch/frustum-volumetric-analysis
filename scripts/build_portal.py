#!/usr/bin/env python3
"""
build_portal.py

Automated Master Project Portal & Auto-Discovery Builder.
Scans outputs/, refreshes each assignment's dashboard (outputs/<site>/index.html),
writes outputs/assignments.json, and generates the master portfolio portal
(outputs/index.html) with dynamic auto-discovery.
"""

import os
import json
import glob
from generate_site_dashboard import generate_site_dashboard, fmt, M3_TO_CUFT, M3_TO_ACRE_FEET

OUTPUTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "outputs"))


def scan_and_build_all(outputs_dir=OUTPUTS_DIR):
    """
    Scan all sites in outputs/, generate their index.html, and compile master portal.
    """
    outputs_dir = os.path.abspath(outputs_dir)
    print("=" * 80)
    print("PORTAL AUTO-DISCOVERY & COMPILATION ENGINE")
    print("=" * 80)
    print(f"  Target Outputs Directory: {outputs_dir}")

    assignments = []
    for entry in sorted(os.scandir(outputs_dir), key=lambda e: e.name):
        if entry.is_dir() and not entry.name.startswith("."):
            # Check if directory or any subfolder has viewer_data.geojson
            geojsons = glob.glob(os.path.join(entry.path, "**", "viewer_data.geojson"), recursive=True)
            if geojsons:
                print(f"\nProcessing assignment: {entry.name}")
                site_meta = generate_site_dashboard(entry.path)
                if site_meta:
                    assignments.append(site_meta)

    # Calculate portfolio totals
    total_portfolio_vol_m3 = sum(a["total_vol_m3"] for a in assignments)
    total_portfolio_vol_cuft = sum(a["total_vol_cuft"] for a in assignments)
    total_portfolio_vol_acft = sum(a["total_vol_acft"] for a in assignments)
    total_portfolio_area_m2 = sum(a["total_area_m2"] for a in assignments)
    total_portfolio_stages = sum(a["total_slices"] for a in assignments)

    portal_manifest = {
        "timestamp": str(pd_timestamp() if False else ""),
        "total_sites": len(assignments),
        "total_vol_m3": round(total_portfolio_vol_m3, 2),
        "total_vol_cuft": round(total_portfolio_vol_cuft, 2),
        "total_vol_acft": round(total_portfolio_vol_acft, 2),
        "total_area_m2": round(total_portfolio_area_m2, 2),
        "total_stages": total_portfolio_stages,
        "assignments": assignments,
    }

    # Write assignments.json
    manifest_path = os.path.join(outputs_dir, "assignments.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(portal_manifest, f, indent=2)
    print(f"\n✓ Generated manifest: {manifest_path}")

    # Build master outputs/index.html
    master_html_path = os.path.join(outputs_dir, "index.html")
    build_master_html(portal_manifest, master_html_path)
    print(f"✓ Generated Master Portal: {master_html_path}")
    print("=" * 80)
    print(f"STATUS: SUCCESS — {len(assignments)} assignments indexed & published.")
    print("=" * 80)
    return portal_manifest


def pd_timestamp():
    from datetime import datetime
    return datetime.now().isoformat()


def build_master_html(manifest, output_path):
    """Generate the executive master portal HTML with dynamic auto-discovery."""
    assignments = manifest["assignments"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MMD Survey & Earthwork Portfolio — Master Command Center</title>
    <style>
        :root {{
            --bg-primary: #0a0f1d;
            --bg-surface: #111827;
            --bg-card: #1f2937;
            --text-primary: #f9fafb;
            --text-secondary: #9ca3af;
            --accent-blue: #38bdf8;
            --accent-cyan: #06b6d4;
            --accent-emerald: #10b981;
            --accent-amber: #f59e0b;
            --border-color: #374151;
            --border-subtle: rgba(255,255,255,0.08);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 3rem 1.5rem;
            min-height: 100vh;
        }}
        .container {{
            max-width: 1240px;
            margin: 0 auto;
        }}
        header {{
            margin-bottom: 2.5rem;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1.75rem;
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
            flex-wrap: gap;
            gap: 1rem;
        }}
        .brand-badge {{
            display: inline-block;
            font-size: 0.75rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.1em;
            color: var(--accent-blue);
            background: rgba(56, 189, 248, 0.1);
            border: 1px solid rgba(56, 189, 248, 0.25);
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            margin-bottom: 0.5rem;
        }}
        h1 {{
            font-size: 2.25rem;
            font-weight: 800;
            letter-spacing: -0.02em;
            color: var(--text-primary);
            line-height: 1.2;
        }}
        .subtitle {{
            color: var(--text-secondary);
            font-size: 1.05rem;
            margin-top: 0.25rem;
        }}
        .live-status {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.85rem;
            color: var(--accent-emerald);
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            padding: 0.4rem 0.8rem;
            border-radius: 0.5rem;
        }}
        .pulse-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--accent-emerald);
            box-shadow: 0 0 10px var(--accent-emerald);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ transform: scale(0.95); opacity: 0.8; }}
            50% {{ transform: scale(1.2); opacity: 1; }}
            100% {{ transform: scale(0.95); opacity: 0.8; }}
        }}
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.25rem;
            margin-bottom: 3rem;
        }}
        .kpi-card {{
            background: linear-gradient(145deg, #161f30, #111827);
            border: 1px solid var(--border-color);
            border-radius: 0.875rem;
            padding: 1.5rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.25);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            border-color: rgba(56, 189, 248, 0.4);
        }}
        .kpi-label {{
            font-size: 0.8rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            color: var(--text-secondary);
            margin-bottom: 0.4rem;
        }}
        .kpi-val {{
            font-size: 2rem;
            font-weight: 800;
            color: var(--accent-blue);
            line-height: 1.1;
        }}
        .kpi-sub {{
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: 0.5rem;
        }}
        .section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1.5rem;
        }}
        .section-title {{
            font-size: 1.4rem;
            font-weight: 700;
            letter-spacing: -0.01em;
        }}
        .refresh-btn {{
            background: transparent;
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.4rem 0.8rem;
            border-radius: 0.5rem;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.15s ease;
        }}
        .refresh-btn:hover {{
            background: var(--bg-card);
            color: var(--accent-blue);
            border-color: var(--accent-blue);
        }}
        .assignments-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 1.5rem;
        }}
        .assignment-card {{
            background: var(--bg-surface);
            border: 1px solid var(--border-color);
            border-radius: 0.875rem;
            padding: 1.5rem;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            transition: all 0.2s ease;
        }}
        .assignment-card:hover {{
            border-color: var(--accent-blue);
            box-shadow: 0 8px 30px rgba(0,0,0,0.35);
            transform: translateY(-2px);
        }}
        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.75rem;
        }}
        .site-title {{
            font-size: 1.35rem;
            font-weight: 700;
            color: var(--text-primary);
        }}
        .site-badge {{
            font-size: 0.75rem;
            font-weight: 600;
            background: rgba(56, 189, 248, 0.15);
            color: var(--accent-blue);
            padding: 0.2rem 0.5rem;
            border-radius: 0.25rem;
        }}
        .metric-table {{
            margin: 1rem 0;
            border-top: 1px solid var(--border-subtle);
            border-bottom: 1px solid var(--border-subtle);
            padding: 0.5rem 0;
        }}
        .metric-item {{
            display: flex;
            justify-content: space-between;
            padding: 0.35rem 0;
            font-size: 0.9rem;
        }}
        .metric-lbl {{ color: var(--text-secondary); }}
        .metric-num {{ font-weight: 600; color: var(--text-primary); }}
        .btn-launch {{
            display: block;
            text-align: center;
            background: linear-gradient(135deg, #0284c7, #0369a1);
            color: white;
            text-decoration: none;
            padding: 0.75rem 1rem;
            border-radius: 0.5rem;
            font-weight: 600;
            font-size: 0.95rem;
            margin-top: 1rem;
            transition: all 0.2s ease;
        }}
        .btn-launch:hover {{
            background: linear-gradient(135deg, #38bdf8, #0284c7);
            box-shadow: 0 4px 15px rgba(2, 132, 199, 0.35);
        }}
        footer {{
            margin-top: 4rem;
            border-top: 1px solid var(--border-color);
            padding-top: 1.5rem;
            text-align: center;
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <span class="brand-badge">MMD Earthwork Analytics</span>
                <h1>Survey Project Portfolio</h1>
                <p class="subtitle">Unified Prismoidal Frustum Engine & Interactive 3D WebGIS Inspection Center</p>
            </div>
            <div class="live-status">
                <span class="pulse-dot"></span>
                <span>Auto-Discovery Live</span>
            </div>
        </header>

        <div class="kpi-grid">
            <div class="kpi-card">
                <div class="kpi-label">Portfolio Earthwork</div>
                <div class="kpi-val" id="kpiVol">{fmt(manifest['total_vol_m3'])} m³</div>
                <div class="kpi-sub" id="kpiCuft">{fmt(manifest['total_vol_cuft'])} cu ft &bull; {fmt(manifest['total_vol_acft'], 2)} ac·ft</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Total Survey Footprint</div>
                <div class="kpi-val" id="kpiArea">{fmt(manifest['total_area_m2'])} m²</div>
                <div class="kpi-sub" id="kpiHa">{fmt(manifest['total_area_m2'] / 10000.0, 3)} hectares</div>
            </div>
            <div class="kpi-card">
                <div class="kpi-label">Active Assignments</div>
                <div class="kpi-val" id="kpiSites">{manifest['total_sites']} Sites</div>
                <div class="kpi-sub" id="kpiStages">{manifest['total_stages']} discrete 3D stages</div>
            </div>
        </div>

        <div class="section-header">
            <h2 class="section-title">Survey Assignments</h2>
            <button class="refresh-btn" onclick="fetchLiveAssignments()">&#x21bb; Check New Assignments</button>
        </div>

        <div class="assignments-grid" id="assignmentsGrid">
"""

    for a in assignments:
        units_count = len(a["units"])
        unit_label = f"{units_count} Units" if units_count > 1 else "Single Unit"
        html += f"""            <div class="assignment-card">
                <div>
                    <div class="card-header">
                        <div class="site-title">{a['title']}</div>
                        <span class="site-badge">{unit_label}</span>
                    </div>
                    <div class="metric-table">
                        <div class="metric-item"><span class="metric-lbl">Frustum Volume</span><span class="metric-num">{fmt(a['total_vol_m3'])} m³</span></div>
                        <div class="metric-item"><span class="metric-lbl">Cubic Feet</span><span class="metric-num">{fmt(a['total_vol_cuft'])} cu ft</span></div>
                        <div class="metric-item"><span class="metric-lbl">Footprint Area</span><span class="metric-num">{fmt(a['total_area_m2'])} m²</span></div>
                        <div class="metric-item"><span class="metric-lbl">Discrete Stages</span><span class="metric-num">{a['total_slices']} layers</span></div>
                        <div class="metric-item"><span class="metric-lbl">Method Variance</span><span class="metric-num">{a['overall_var_pct']:+.2f}%</span></div>
                    </div>
                </div>
                <a href="{a['index_rel']}" class="btn-launch">Open Assignment Dashboard &rarr;</a>
            </div>
"""

    html += """        </div>

        <footer>
            MMD Frustum Volumetric Analysis Engine &bull; Auto-Discovery WebGIS Architecture &bull; Local Server Port 8080
        </footer>
    </div>

    <!-- Client-side dynamic auto-discovery script -->
    <script>
    async function fetchLiveAssignments() {
        try {
            // Attempt dynamic API fetch first; fallback to assignments.json
            let resp = await fetch('/api/assignments');
            if (!resp.ok) {
                resp = await fetch('./assignments.json');
            }
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data || !data.assignments) return;

            // Re-render KPI metrics
            if (data.total_vol_m3) {
                document.getElementById('kpiVol').textContent = Number(data.total_vol_m3).toLocaleString(undefined, {maximumFractionDigits:0}) + ' m³';
                document.getElementById('kpiCuft').textContent = Number(data.total_vol_cuft).toLocaleString(undefined, {maximumFractionDigits:0}) + ' cu ft';
                document.getElementById('kpiArea').textContent = Number(data.total_area_m2).toLocaleString(undefined, {maximumFractionDigits:0}) + ' m²';
                document.getElementById('kpiHa').textContent = (Number(data.total_area_m2) / 10000).toFixed(3) + ' hectares';
                document.getElementById('kpiSites').textContent = data.total_sites + ' Sites';
                document.getElementById('kpiStages').textContent = data.total_stages + ' discrete 3D stages';
            }

            // Re-render cards dynamically
            const grid = document.getElementById('assignmentsGrid');
            grid.innerHTML = '';
            data.assignments.forEach(a => {
                const uCount = a.units ? a.units.length : 1;
                const uLabel = uCount > 1 ? uCount + ' Units' : 'Single Unit';
                const card = document.createElement('div');
                card.className = 'assignment-card';
                card.innerHTML = `
                    <div>
                        <div class="card-header">
                            <div class="site-title">${a.title}</div>
                            <span class="site-badge">${uLabel}</span>
                        </div>
                        <div class="metric-table">
                            <div class="metric-item"><span class="metric-lbl">Frustum Volume</span><span class="metric-num">${Number(a.total_vol_m3).toLocaleString(undefined, {maximumFractionDigits:0})} m³</span></div>
                            <div class="metric-item"><span class="metric-lbl">Cubic Feet</span><span class="metric-num">${Number(a.total_vol_cuft).toLocaleString(undefined, {maximumFractionDigits:0})} cu ft</span></div>
                            <div class="metric-item"><span class="metric-lbl">Footprint Area</span><span class="metric-num">${Number(a.total_area_m2).toLocaleString(undefined, {maximumFractionDigits:0})} m²</span></div>
                            <div class="metric-item"><span class="metric-lbl">Discrete Stages</span><span class="metric-num">${a.total_slices} layers</span></div>
                            <div class="metric-item"><span class="metric-lbl">Method Variance</span><span class="metric-num">${a.overall_var_pct >= 0 ? '+' : ''}${Number(a.overall_var_pct).toFixed(2)}%</span></div>
                        </div>
                    </div>
                    <a href="${a.index_rel}" class="btn-launch">Open Assignment Dashboard &rarr;</a>
                `;
                grid.appendChild(card);
            });
        } catch (e) {
            console.log('Auto-discovery polling:', e);
        }
    }

    // Run dynamic discovery immediately on page load
    window.addEventListener('DOMContentLoaded', fetchLiveAssignments);
    </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    scan_and_build_all()
