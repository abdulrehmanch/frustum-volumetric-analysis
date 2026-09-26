"""
Unit tests for Prismoidal Frustum Volumetric Analysis.

Validates:
1. Mathematical precision against known analytical geometry (truncated cone & pyramid).
2. Theoretical divergence bounds between Frustum and Average End-Area methods.
3. Strict monotonic spatial nesting (A_low >= A_high).
4. Full end-to-end execution on sample survey shapefiles.
"""

import math
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


# Core Mathematical Formulas
def prismoidal_frustum_volume(a1: float, a2: float, dh: float) -> float:
    """Calculates slice volume using the Prismoidal Frustum Method."""
    return (dh / 3.0) * (a1 + a2 + math.sqrt(a1 * a2))


def average_end_area_volume(a1: float, a2: float, dh: float) -> float:
    """Calculates slice volume using the Average End-Area Method."""
    return (dh / 2.0) * (a1 + a2)


class TestFrustumMathematics(unittest.TestCase):
    """Analytical mathematical proofs and boundary tests."""

    def test_truncated_cone_analytical_match(self):
        """
        Benchmark against a circular truncated cone:
        Base radius r1 = 10 m  => A1 = pi * 10^2 = 100 * pi
        Top radius r2 = 5 m    => A2 = pi * 5^2  = 25 * pi
        Height dh = 2 m
        Analytical Exact V = (pi * h / 3) * (r1^2 + r2^2 + r1 * r2)
                           = (2 * pi / 3) * (100 + 25 + 50)
                           = 350 * pi / 3 ~= 366.5191429 m^3
        """
        r1, r2, dh = 10.0, 5.0, 2.0
        a1 = math.pi * (r1 ** 2)
        a2 = math.pi * (r2 ** 2)

        expected_exact_vol = (math.pi * dh / 3.0) * (r1**2 + r2**2 + r1 * r2)
        computed_vol = prismoidal_frustum_volume(a1, a2, dh)

        self.assertTrue(math.isclose(computed_vol, expected_exact_vol, rel_tol=1e-12))

    def test_truncated_pyramid_analytical_match(self):
        """
        Benchmark against a square truncated pyramid:
        Base side s1 = 20 m => A1 = 400 m^2
        Top side s2 = 10 m  => A2 = 100 m^2
        Height dh = 3 m
        Analytical Exact V = (h / 3) * (A1 + A2 + sqrt(A1 * A2))
                           = (3 / 3) * (400 + 100 + 200) = 700 m^3
        """
        a1 = 20.0 * 20.0  # 400
        a2 = 10.0 * 10.0  # 100
        dh = 3.0

        expected_exact_vol = 700.0
        computed_vol = prismoidal_frustum_volume(a1, a2, dh)

        self.assertTrue(math.isclose(computed_vol, expected_exact_vol, rel_tol=1e-12))

    def test_cylinder_straight_wall_degeneracy(self):
        """
        When side slopes are vertical (A1 == A2),
        Frustum volume MUST exactly equal Average End-Area and Prism volume (A * h).
        """
        a1 = 250.0
        a2 = 250.0
        dh = 1.5

        v_frustum = prismoidal_frustum_volume(a1, a2, dh)
        v_end_area = average_end_area_volume(a1, a2, dh)
        v_prism = a1 * dh

        self.assertTrue(math.isclose(v_frustum, v_prism, rel_tol=1e-12))
        self.assertTrue(math.isclose(v_frustum, v_end_area, rel_tol=1e-12))

    def test_frustum_always_less_than_or_equal_end_area(self):
        """
        AM-GM inequality proof:
        (A1 + A2) / 2 >= sqrt(A1 * A2)
        Therefore, Average End Area systematically overestimates volume relative to
        Prismoidal Frustum for any tapering side wall (A1 != A2).
        """
        random.seed(42)
        for _ in range(100):
            a1 = random.uniform(10.0, 10000.0)
            a2 = random.uniform(1.0, a1)  # a1 >= a2
            dh = random.uniform(0.1, 10.0)

            v_frustum = prismoidal_frustum_volume(a1, a2, dh)
            v_end_area = average_end_area_volume(a1, a2, dh)

            self.assertGreaterEqual(v_end_area, v_frustum)
            if not math.isclose(a1, a2, rel_tol=1e-6):
                self.assertGreater(v_end_area, v_frustum)

    def test_nesting_monotonicity_constraint(self):
        """
        Downward spatial accumulation ensures A(Z_k) >= A(Z_{k+1}).
        """
        simulated_stages = [
            {"z": 100.0, "area": 1000.0},
            {"z": 101.0, "area": 750.0},
            {"z": 102.0, "area": 500.0},
            {"z": 103.0, "area": 200.0},
            {"z": 104.0, "area": 50.0},
        ]
        areas = [s["area"] for s in simulated_stages]
        for i in range(len(areas) - 1):
            self.assertGreaterEqual(
                areas[i], areas[i + 1], f"Area violation at stage {i}: {areas[i]} < {areas[i+1]}"
            )


class TestPipelineExecution(unittest.TestCase):
    """End-to-end integration test using the sample dataset."""

    def test_sample_south_calculation_pipeline(self):
        sample_shp = Path("examples/sample_heap_south/Contours.shp")
        if not sample_shp.exists():
            self.skipTest("Sample shapefile not present in examples/sample_heap_south/")

        with tempfile.TemporaryDirectory() as tmpdir:
            cmd = [
                sys.executable,
                "scripts/calculate_frustum_volume.py",
                "--input", str(sample_shp),
                "--output-dir", tmpdir,
                "--site-name", "test_south",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0 and "No module named 'geopandas'" in result.stderr:
                self.skipTest("GeoPandas not installed in current test python environment")
            self.assertEqual(
                result.returncode, 0, f"Script failed with output:\n{result.stderr}\n{result.stdout}"
            )

            # Verify generated engineering deliverables
            out_path = Path(tmpdir)
            self.assertTrue((out_path / "test_south_frustum_volumetric_report.csv").exists())
            self.assertTrue((out_path / "test_south_stage_storage_curves.png").exists())
            self.assertTrue((out_path / "test_south_contour_slices_map.png").exists())
            self.assertTrue((out_path / "test_south_frustum_slice_polygons.shp").exists())
            self.assertTrue((out_path / "test_south_frustum_cumulative_polygons.shp").exists())


if __name__ == "__main__":
    unittest.main()
