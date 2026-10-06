---
name: fr-deploy
description: >-
  Deploy and manage the containerized MMD Frustum Volumetric Portal on remote servers via Docker Compose.
  Synchronize survey assignments with live host-mounted volumes for instant zero-restart updates.
---

# Deploy Portal Docker Skill

This skill guides the containerized deployment of the MMD Survey & Earthwork Portfolio onto a remote server using Docker Compose and rsync.

---

## 1. Architecture: Live Host Volume Mount

The portal runs inside a single Docker container (`mmd_portal`), mapping the host's `./outputs` folder directly into the container:

```text
[Local Machine]                                [Remote Server: devserver]
 outputs/<assignment>/                          ~/mmd_frustum_portal/
       │                                        ├── docker-compose.yml (Port 8085:8080)
       │                                        ├── Dockerfile
       │  rsync                                 ├── scripts/
       └───────────────────────────────────────►└── outputs/  <─── (Host Volume Mount)
                                                         │
                                                [Container mmd_portal]
                                                 Auto-detects updates live
```

Because `./outputs` is mounted from the host filesystem, **no container restarts or rebuilds are ever needed when pushing new survey data**.

---

## 2. Server Initial Setup (Run Once)

You do **not** need to clone the entire git repository on the server.

### Step 1: Create Remote Directory
```bash
ssh devserver "mkdir -p ~/mmd_frustum_portal/scripts ~/mmd_frustum_portal/outputs"
```

### Step 2: Sync Docker & Framework Files
From the local repository root:
```bash
rsync -avz Dockerfile docker-compose.yml .dockerignore devserver:~/mmd_frustum_portal/
rsync -avz scripts/serve_portal.py scripts/generate_site_dashboard.py devserver:~/mmd_frustum_portal/scripts/
rsync -avz outputs/index.html devserver:~/mmd_frustum_portal/outputs/
```

### Step 3: Launch the Container
```bash
ssh devserver "cd ~/mmd_frustum_portal && docker compose up --build -d"
```

Verify that the container is running:
```bash
ssh devserver "docker ps --filter 'name=mmd_portal'"
```

---

## 3. Pushing Assignments to the Server (Live Updates)

Whenever you calculate and export a new survey site or block locally, push its outputs folder using `rsync`:

```bash
# Push an existing or new assignment:
rsync -avz outputs/<assignment_name>/ devserver:~/mmd_frustum_portal/outputs/<assignment_name>/

# Examples:
rsync -avz outputs/bund_calculations/ devserver:~/mmd_frustum_portal/outputs/bund_calculations/
rsync -avz outputs/dg_khan_pits/ devserver:~/mmd_frustum_portal/outputs/dg_khan_pits/
rsync -avz outputs/hassan_abdal/ devserver:~/mmd_frustum_portal/outputs/hassan_abdal/
```

**Zero Docker Commands Needed**:
- The running container immediately sees the new folder through the volume mount.
- When any user visits the server portal or clicks **`↻ Refresh Data`**, the portal scans the folder, updates all portfolio totals, and compiles the site dashboard on the fly.

---

## 4. Remote Verification & Access URLs

### Check API Status Remotely:
```bash
ssh devserver "curl -s http://localhost:8085/api/assignments | python3 -m json.tool"
```

### Remote Access URLs (Port 8085):
- **Master Portfolio Command Center:**
  `http://geoforger-dev.tail9edb81.ts.net:8085/`
- **Dynamic API Discovery:**
  `http://geoforger-dev.tail9edb81.ts.net:8085/api/assignments`
- **Assignment Landing Dashboard:**
  `http://geoforger-dev.tail9edb81.ts.net:8085/<assignment_name>/`
- **3D WebGIS Viewer:**
  `http://geoforger-dev.tail9edb81.ts.net:8085/<assignment_name>/<unit_name>/<prefix>_3d_viewer.html`
