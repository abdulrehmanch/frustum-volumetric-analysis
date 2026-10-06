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
import sqlite3
import hashlib
import hmac
import secrets
from http.cookies import SimpleCookie
from urllib.parse import parse_qs
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUTS_DIR = os.path.join(REPO_ROOT, "outputs")
AUTH_DB_PATH = os.path.join(REPO_ROOT, "auth.db")

# In-memory session secret for signed login tokens
SESSION_SECRET = secrets.token_hex(32)

def generate_session_token(username: str) -> str:
    sig = hmac.new(SESSION_SECRET.encode(), username.encode(), hashlib.sha256).hexdigest()
    return f"{username}:{sig}"

def verify_session_token(token: str) -> bool:
    if not token or ":" not in token:
        return False
    username, sig = token.split(":", 1)
    expected = hmac.new(SESSION_SECRET.encode(), username.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected)

def verify_credentials(username, password) -> bool:
    if not os.path.exists(AUTH_DB_PATH):
        # Auto-create if missing
        conn = sqlite3.connect(AUTH_DB_PATH)
        conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT)")
        conn.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", ("admin", hashlib.sha256("mmd2026!".encode()).hexdigest()))
        conn.commit()
        conn.close()

    try:
        conn = sqlite3.connect(AUTH_DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username = ?", (username,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return False
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        return hmac.compare_digest(row[0], pwd_hash)
    except Exception:
        return False

LOGIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MMD Portal — Restricted Access Gate</title>
    <style>
        :root {
            --bg-primary: #0a0f1d;
            --bg-card: #111827;
            --accent-blue: #38bdf8;
            --border-color: #374151;
            --text-primary: #f9fafb;
            --text-secondary: #9ca3af;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-primary);
            color: var(--text-primary);
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            padding: 1.5rem;
        }
        .login-card {
            background: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 0.875rem;
            padding: 2.5rem;
            width: 100%;
            max-width: 420px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.5);
        }
        .brand-badge {
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
            margin-bottom: 0.75rem;
        }
        h1 {
            font-size: 1.6rem;
            font-weight: 800;
            margin-bottom: 0.35rem;
        }
        p.subtitle {
            color: var(--text-secondary);
            font-size: 0.9rem;
            margin-bottom: 1.75rem;
        }
        .form-group {
            margin-bottom: 1.25rem;
        }
        label {
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-secondary);
            margin-bottom: 0.4rem;
        }
        input[type="text"], input[type="password"] {
            width: 100%;
            padding: 0.75rem 1rem;
            background: #0d1322;
            border: 1px solid var(--border-color);
            border-radius: 0.5rem;
            color: var(--text-primary);
            font-size: 0.95rem;
            outline: none;
            transition: border-color 0.2s;
        }
        input[type="text"]:focus, input[type="password"]:focus {
            border-color: var(--accent-blue);
        }
        .btn-submit {
            width: 100%;
            padding: 0.85rem;
            background: linear-gradient(135deg, #0284c7, #0369a1);
            color: white;
            border: none;
            border-radius: 0.5rem;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            margin-top: 0.75rem;
            transition: opacity 0.2s;
        }
        .btn-submit:hover {
            opacity: 0.9;
        }
        .error-msg {
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #ef4444;
            font-size: 0.85rem;
            padding: 0.6rem 0.8rem;
            border-radius: 0.4rem;
            margin-bottom: 1.25rem;
        }
    </style>
</head>
<body>
    <div class="login-card">
        <span class="brand-badge">MMD Earthwork Analytics</span>
        <h1>Sign In to Portal</h1>
        <p class="subtitle">Enter credentials to access 3D inspection and survey calculations.</p>
        __ERROR_PLACEHOLDER__
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required autofocus autocomplete="username">
            </div>
            <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="btn-submit">Access Portal &rarr;</button>
        </form>
    </div>
</body>
</html>
"""

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

    def _is_authenticated(self) -> bool:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return False
        cookie = SimpleCookie()
        try:
            cookie.load(cookie_header)
            if "mmd_session" in cookie:
                token = cookie["mmd_session"].value
                return verify_session_token(token)
        except Exception:
            return False
        return False

    def _serve_login_page(self, error: str = ""):
        err_html = f'<div class="error-msg">{error}</div>' if error else ""
        content = LOGIN_HTML.replace("__ERROR_PLACEHOLDER__", err_html).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def do_HEAD(self):
        if self.path.startswith("/api/assignments"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        if self.path == "/login":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            return
        clean_path = self.path.split("?")[0]
        if clean_path.endswith(".html") or clean_path.endswith("/") or clean_path == "":
            if not self._is_authenticated():
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                return
        super().do_HEAD()

    def do_POST(self):
        if self.path == "/login":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            params = parse_qs(body)
            username = params.get("username", [""])[0].strip()
            password = params.get("password", [""])[0].strip()

            if verify_credentials(username, password):
                token = generate_session_token(username)
                self.send_response(303)
                self.send_header("Location", "/")
                # Set cookie valid for 7 days
                self.send_header("Set-Cookie", f"mmd_session={token}; Path=/; HttpOnly; Max-Age=604800; SameSite=Lax")
                self.end_headers()
            else:
                self._serve_login_page("Invalid username or password.")
            return

        super().do_POST()

    def do_GET(self):
        # Open endpoints: API and login page
        if self.path == "/login":
            if self._is_authenticated():
                self.send_response(303)
                self.send_header("Location", "/")
                self.end_headers()
                return
            self._serve_login_page()
            return

        if self.path.startswith("/api/assignments"):
            self._handle_api_assignments()
            return

        # Check login gate for HTML pages and root
        clean_path = self.path.split("?")[0]
        if clean_path.endswith(".html") or clean_path.endswith("/") or clean_path == "":
            if not self._is_authenticated():
                self._serve_login_page()
                return

        # If requesting a site directory or its index.html, ensure its dashboard is generated
        clean_path_rel = clean_path.strip("/")
        parts = clean_path_rel.split("/")
        if len(parts) >= 1 and parts[0] and not parts[0].startswith("."):
            site_candidate = os.path.join(OUTPUTS_DIR, parts[0])
            if os.path.isdir(site_candidate):
                geojsons = glob.glob(os.path.join(site_candidate, "**", "viewer_data.geojson"), recursive=True)
                if geojsons:
                    site_idx = os.path.join(site_candidate, "index.html")
                    if (not os.path.exists(site_idx) or self.path.endswith("index.html") or len(parts) == 1) and generate_site_dashboard:
                        try:
                            generate_site_dashboard(site_candidate)
                        except Exception:
                            pass

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
