# Contributing to Frustum Volumetric Analysis

Thank you for your interest in contributing to **Frustum Volumetric Analysis**! We welcome bug reports, feature suggestions, documentation enhancements, and pull requests from civil engineers, surveyors, and geospatial developers.

---

## 🛠 Development Workflow

### 1. Prerequisites
- Python 3.10+
- [`uv`](https://docs.astral.sh/uv/) (recommended) or standard `pip` / `venv`
- Geospatial libraries (GDAL/GEOS system dependencies if building C extensions, or standard wheels via `uv`)

### 2. Setting Up the Environment
```bash
# Clone repository
git clone https://github.com/abdulrehmanch/frustum-volumetric-analysis.git
cd frustum-volumetric-analysis

# Install dependencies using uv
uv sync --all-extras --dev
```

### 3. Running Tests
```bash
# Run test suite with pytest
uv run pytest -v

# Or using standard unittest
python3 -m unittest discover tests
```

---

## 📐 Engineering Principles & Code Guidelines

1. **No Fallback / Silent Guessing:**
   - Always fail loudly with clear diagnostic error messages if an expected attribute, CRS, or boundary geometry is invalid.
   - Do not silently fabricate volume over un-surveyed ground.
2. **Strict Downward Monotonicity:**
   - For all volumetric calculation logic, lower contour stage footprints must spatially enclose higher stages ($A(Z_k) \ge A(Z_{k+1})$).
3. **Reproducibility:**
   - Calculations must be dataset-agnostic and metric UTM projected (EPSG:32643, etc.).
   - All tests against known analytical geometries must match with strict precision (`rel_tol <= 1e-9`).

---

## 🚀 Submitting Pull Requests

1. Create a descriptive feature branch:
   ```bash
   git checkout -b feature/improved-split-mode
   ```
2. Commit your changes with clear, semantic commit messages:
   ```bash
   git commit -m "feat: add multi-polygon handling for split solver mode"
   ```
3. Ensure all tests pass before pushing:
   ```bash
   uv run pytest
   ```
4. Push to your fork and open a Pull Request.
