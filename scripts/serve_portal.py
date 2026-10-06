#!/usr/bin/env python3
"""
serve_portal.py

Dynamic Auto-Discovery WebGIS Server for MMD Survey Assignments.
Serves static deliverables from outputs/ and provides a dynamic /api/assignments
endpoint that scans outputs/ in real-time, auto-discovering any new or updated
survey assignment upon page load.
"""

import os
import sys
import json
import glob
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUTS_DIR = os.path.join(REPO_ROOT, "outputs")

# Import dashboard generator to parse units dynamically
sys.path.insert(0, os.path.dirname(__file__))
try:
    from generate_site_dashboard import discover_site_units, generate_site_dashboard
except ImportError:
    discover_site_units = None
    generate_site_dashboard = None


class PortalRequestHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUTPUTS_DIR, **kwargs)

    def do_GET(self):
        # Intercept dynamic auto-discovery API endpoint
        if self.path.startswith("/api/assignments"):
            self._handle_api_assignments()
            return
        super().do_GET()

    def _handle_api_assignments(self):
        try:
            assignments = []
            for entry in sorted(os.scandir(OUTPUTS_DIR), key=lambda e: e.name):
                if entry.is_dir() and not entry.name.startswith("."):
                    geojsons = glob.glob(os.path.join(entry.path, "**", "viewer_data.geojson"), recursive=True)
                    if geojsons:
                        # Auto-generate index.html if missing
                        idx = os.path.join(entry.path, "index.html")
                        if not os.path.exists(idx) and generate_site_dashboard:
                            generate_site_dashboard(entry.path)

                        if discover_site_units:
                            units = discover_site_units(entry.path)
                            tot_m3 = sum(u["vol_m3"] for u in units)
                            tot_cuft = sum(u["vol_cuft"] for u in units)
                            tot_area = sum(u["area_m2"] for u in units)
                            tot_slices = sum(u["num_slices"] for u in units)
                            tot_end = sum(u["endarea_vol_m3"] for u in units)
                            var = ((tot_end - tot_m3) / tot_m3 * 100.0) if tot_m3 > 0 else 0.0

                            assignments.append({
                                "site_name": entry.name,
                                "title": entry.name.replace("_", " ").title(),
                                "index_rel": f"{entry.name}/index.html",
                                "units": units,
                                "total_vol_m3": round(tot_m3, 2),
                                "total_vol_cuft": round(tot_cuft, 2),
                                "total_area_m2": round(tot_area, 2),
                                "total_slices": tot_slices,
                                "overall_var_pct": round(var, 2),
                            })

            payload = {
                "total_sites": len(assignments),
                "total_vol_m3": round(sum(a["total_vol_m3"] for a in assignments), 2),
                "total_vol_cuft": round(sum(a["total_vol_cuft"] for a in assignments), 2),
                "total_area_m2": round(sum(a["total_area_m2"] for a in assignments), 2),
                "total_stages": sum(a["total_slices"] for a in assignments),
                "assignments": assignments,
            }

            resp_data = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp_data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(resp_data)

        except Exception as e:
            err_data = json.dumps({"error": str(e)}).encode("utf-8")
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(err_data)


def main():
    parser = argparse.ArgumentParser(description="MMD Survey Portal Auto-Discovery Server")
    parser.add_argument("--port", "-p", type=int, default=8080, help="Port to listen on (default: 8080)")
    args = parser.parse_args()

    port = args.port
    print("=" * 80)
    print("MMD SURVEY PORTAL DYNAMIC AUTO-DISCOVERY SERVER")
    print("=" * 80)
    print(f"  Serving Directory : {OUTPUTS_DIR}")
    print(f"  Port              : {port}")
    print(f"  Master Portal URL : http://localhost:{port}/")
    print(f"  API Discovery URL : http://localhost:{port}/api/assignments")
    print("=" * 80)

    server = ThreadingHTTPServer(("0.0.0.0", port), PortalRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
