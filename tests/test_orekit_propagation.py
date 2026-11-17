"""
Numerical orbit propagation with NRLMSIS 2.1 drag (Orekit NumericalPropagator).

Platform independent: JVM, JAR, JNI library and ``msis21.parm`` are resolved by
``orekit_nrlmsis21.init_vm()``; Orekit data via ``OREKIT_DATA_PATH`` or ``orekit-data/``.
Runs under pytest or directly (``python tests/test_orekit_propagation.py``, exit code 0/1).
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Prefer an installed wheel; fall back to repo python/. Drop the repo root from sys.path because
# <root>/java (Maven sources) would shadow JPype's java.* namespace.
sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != REPO_ROOT]
try:
    import orekit_nrlmsis21  # noqa: F401
except ImportError:
    sys.path.insert(0, str((REPO_ROOT / "python").resolve()))

import orekit_nrlmsis21 as nrl  # noqa: E402


def _find_orekit_data() -> Path:
    candidates = []
    if os.environ.get("OREKIT_DATA_PATH"):
        candidates.append(Path(os.environ["OREKIT_DATA_PATH"]))
    candidates += [REPO_ROOT / "orekit-data", Path.cwd() / "orekit-data"]
    for c in candidates:
        if c.is_dir():
            return c.resolve()
    raise FileNotFoundError("Orekit data folder not found: " + ", ".join(str(c) for c in candidates))


def _build_propagator(orbit, mass_kg, atm, area_m2=2.0, cd=2.2):
    from org.hipparchus.ode.nonstiff import DormandPrince853Integrator
    from org.orekit.forces.drag import DragForce, IsotropicDrag
    from org.orekit.forces.gravity import NewtonianAttraction
    from org.orekit.orbits import OrbitType
    from org.orekit.propagation import SpacecraftState
    from org.orekit.propagation.numerical import NumericalPropagator

    tolerances = NumericalPropagator.tolerances(10.0, orbit, OrbitType.CARTESIAN)
    integrator = DormandPrince853Integrator(0.001, 60.0, tolerances[0], tolerances[1])
    propagator = NumericalPropagator(integrator)
    propagator.setOrbitType(OrbitType.CARTESIAN)
    propagator.setInitialState(SpacecraftState(orbit, mass_kg))
    propagator.addForceModel(NewtonianAttraction(orbit.getMu()))
    propagator.addForceModel(DragForce(atm, IsotropicDrag(area_m2, cd)))
    return propagator


def test_propagation_with_nrlmsis21_drag():
    nrl.init_vm()
    from orekit_jpype.pyhelpers import setup_orekit_data
    setup_orekit_data(filenames=str(_find_orekit_data()), from_pip_library=False)

    from org.orekit.bodies import OneAxisEllipsoid
    from org.orekit.frames import FramesFactory
    from org.orekit.orbits import KeplerianOrbit, PositionAngleType
    from org.orekit.time import AbsoluteDate, TimeScalesFactory
    from org.orekit.utils import Constants, IERSConventions

    utc = TimeScalesFactory.getUTC()
    itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    gcrf = FramesFactory.getGCRF()
    earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS, Constants.WGS84_EARTH_FLATTENING, itrf)

    atm21 = nrl.create_atmosphere(earth, nrl.create_constant_weather(150.0, 150.0, 15.0), utc)

    epoch = AbsoluteDate(2026, 10, 25, 12, 0, 0.0, utc)
    mu = Constants.WGS84_EARTH_MU
    a0 = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0
    orbit = KeplerianOrbit(a0, 0.001, math.radians(51.6), 0.0, 0.0, 0.0,
                           PositionAngleType.TRUE, gcrf, epoch, mu)
    mass_kg = 500.0
    period_s = 2.0 * math.pi * math.sqrt(a0 ** 3 / mu)

    t0 = time.perf_counter()
    state_1rev = _build_propagator(orbit, mass_kg, atm21).propagate(epoch.shiftedBy(period_s))
    dt_1rev = time.perf_counter() - t0
    delta_a_1rev = float(state_1rev.getOrbit().getA()) - a0

    t0 = time.perf_counter()
    state_24h = _build_propagator(orbit, mass_kg, atm21).propagate(epoch.shiftedBy(86400.0))
    dt_24h = time.perf_counter() - t0
    delta_a_24h = float(state_24h.getOrbit().getA()) - a0

    print(f"\n  period {period_s:.1f} s | 1 rev: da={delta_a_1rev:.3f} m ({dt_1rev * 1e3:.0f} ms)"
          f" | 24 h: da={delta_a_24h:.2f} m ({dt_24h:.2f} s)")

    assert delta_a_1rev < 0.0 and delta_a_24h < 0.0, "orbit did not decay under atmospheric drag"
    assert -500.0 < delta_a_24h < -10.0, f"24 h decay {delta_a_24h:.2f} m outside physical expectations"
    # ~-143.7 m reference at these conditions on all supported platforms (no silent drag dropouts)
    assert -160.0 < delta_a_24h < -130.0, f"24 h decay {delta_a_24h:.2f} m deviates from reference (~-143.7 m)"


if __name__ == "__main__":
    try:
        test_propagation_with_nrlmsis21_drag()
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        sys.exit(1)
    print("[PASS] propagation with NRLMSIS 2.1 drag")
    sys.exit(0)
