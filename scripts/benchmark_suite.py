import os
import sys
import time
import math
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((project_root / "python").resolve()))

import jpype

from orekit_nrlmsis21 import init_vm

# Start the Orekit JVM with the NRLMSIS 2.1 JAR and load the native library.
init_vm()

from orekit_jpype.pyhelpers import setup_orekit_data
from orekit_nrlmsis21 import create_atmosphere, create_constant_weather

setup_orekit_data(filenames=str(Path(os.environ.get("OREKIT_DATA_PATH", project_root / "orekit-data")).resolve()), from_pip_library=False)

from org.orekit.time import AbsoluteDate, TimeScalesFactory
from org.orekit.frames import FramesFactory
from org.orekit.bodies import OneAxisEllipsoid
from org.orekit.utils import Constants, IERSConventions
from org.orekit.orbits import KeplerianOrbit, OrbitType, PositionAngleType
from org.orekit.propagation import SpacecraftState
from org.orekit.propagation.numerical import NumericalPropagator
from org.orekit.forces.gravity import NewtonianAttraction
from org.orekit.forces.drag import DragForce, IsotropicDrag
from org.hipparchus.ode.nonstiff import DormandPrince853Integrator
from org.hipparchus.geometry.euclidean.threed import Vector3D


def run_benchmarks():
    print("==========================================================================")
    print("  NRLMSIS 2.1 MULTI-TIER ASTRODYNAMICS BENCHMARK SUITE")
    print("==========================================================================")

    utc = TimeScalesFactory.getUTC()
    itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    gcrf = FramesFactory.getGCRF()
    earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                             Constants.WGS84_EARTH_FLATTENING, itrf)
    epoch = AbsoluteDate(2026, 10, 25, 12, 0, 0.0, utc)
    sw = create_constant_weather(150.0, 150.0, 15.0)
    atm = create_atmosphere(earth, sw, utc)

    # -------------------------------------------------------------------------
    # Tier 1: Micro-Benchmarking Single-Point Evaluation Latency
    # -------------------------------------------------------------------------
    print("\n[Tier 1] Single-Point Density Evaluation Latency (10,000 queries)")
    test_pos = itrf.getTransformTo(gcrf, epoch).transformPosition(
        Vector3D(Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0, 0.0, 0.0)
    )

    # Warmup
    for _ in range(100):
        _ = atm.getDensity(epoch, test_pos, gcrf)

    n_samples = 10000
    t0 = time.perf_counter()
    for _ in range(n_samples):
        _ = atm.getDensity(epoch, test_pos, gcrf)
    dt_eval = time.perf_counter() - t0
    us_per_call = (dt_eval / n_samples) * 1e6
    evals_per_sec = n_samples / dt_eval

    print(f"  Total Time        : {dt_eval*1000.0:.2f} ms")
    print(f"  Mean Latency      : {us_per_call:.2f} us / evaluation")
    print(f"  Throughput        : {evals_per_sec:,.0f} calls / second")

    # -------------------------------------------------------------------------
    # Tier 2: Multi-Arc Numerical Propagation Runtime
    # -------------------------------------------------------------------------
    print("\n[Tier 2] Multi-Arc Numerical Propagation Runtime (LEO 400 km, 51.6 deg)")
    mu = Constants.WGS84_EARTH_MU
    a0 = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0
    orbit = KeplerianOrbit(a0, 0.001, math.radians(51.6), 0.0, 0.0, 0.0,
                           PositionAngleType.TRUE, gcrf, epoch, mu)
    mass_kg = 500.0
    area = 2.0
    cd = 2.2

    arcs_days = [1, 3, 7]
    print(f"{'Arc (Days)':>10} | {'Wall Time (s)':>14} | {'Final a (km)':>14} | {'Total Decay (m)':>16} | {'Speed Ratio':>14}")
    print("-" * 76)

    for days in arcs_days:
        tolerances = NumericalPropagator.tolerances(10.0, orbit, OrbitType.CARTESIAN)
        integrator = DormandPrince853Integrator(0.01, 60.0, tolerances[0], tolerances[1])
        prop = NumericalPropagator(integrator)
        prop.setOrbitType(OrbitType.CARTESIAN)
        prop.setInitialState(SpacecraftState(orbit, mass_kg))
        prop.addForceModel(NewtonianAttraction(mu))
        prop.addForceModel(DragForce(atm, IsotropicDrag(area, cd)))

        duration = days * 86400.0
        t0 = time.perf_counter()
        final_state = prop.propagate(epoch.shiftedBy(duration))
        run_time = time.perf_counter() - t0

        final_a = final_state.getOrbit().getA()
        decay = final_a - a0
        speed_ratio = duration / run_time

        print(f"{days:10d} | {run_time:14.3f} | {final_a/1000.0:14.4f} | {decay:16.2f} | {speed_ratio:13.0f}x")

    print("\n[OK] Benchmark suite completed successfully.")

if __name__ == "__main__":
    run_benchmarks()
