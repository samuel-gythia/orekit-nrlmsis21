import sys
import os
import time
import math
import datetime
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((project_root / "python").resolve()))

# 1. Verify PyMSIS availability
try:
    import pymsis
    from pymsis import msis
    HAS_PYMSIS = True
except ImportError:
    HAS_PYMSIS = False
    print("[WARN] pymsis is not installed. Run 'pip install pymsis' to enable full comparison.")

import jpype

from orekit_nrlmsis21 import init_vm

# Start the Orekit JVM with the NRLMSIS 2.1 JAR and load the native library.
init_vm()

from orekit_jpype.pyhelpers import setup_orekit_data
from orekit_nrlmsis21 import get_atmosphere_class, get_constant_weather_class

# Bootstrap Orekit data and native JNI bridge
data_dir = Path(os.environ.get("OREKIT_DATA_PATH", project_root / "orekit-data"))
setup_orekit_data(filenames=str(data_dir.resolve()), from_pip_library=False)

# Orekit core classes
from org.orekit.time import AbsoluteDate, TimeScalesFactory
from org.orekit.frames import FramesFactory, Frame
from org.orekit.bodies import OneAxisEllipsoid, GeodeticPoint
from org.orekit.utils import Constants, IERSConventions, PVCoordinates
from org.orekit.orbits import KeplerianOrbit, OrbitType, PositionAngleType
from org.orekit.propagation import SpacecraftState
from org.orekit.propagation.numerical import NumericalPropagator
from org.orekit.forces.gravity import NewtonianAttraction
from org.orekit.forces.drag import DragForce, IsotropicDrag
from org.hipparchus.ode.nonstiff import DormandPrince853Integrator
from org.hipparchus.geometry.euclidean.threed import Vector3D
from org.hipparchus.util import FastMath
from org.orekit.models.earth.atmosphere import Atmosphere


# 2. PyMSIS Atmosphere Adapter for Orekit Propagator
@jpype.JImplements(Atmosphere)
class PyMsisAtmosphere:
    """
    Wraps PyMSIS inside Orekit's Atmosphere interface via JPype proxy callbacks.
    Demonstrates the Python-bridge overhead inside an inner ODE solver step.

    The Orekit ``AbsoluteDate`` passed by the integrator is converted to the matching UTC
    ``datetime`` on every call (pymsis itself truncates to whole seconds).
    """
    def __init__(self, earth_body, utc, f107=150.0, f107a=150.0, ap_scalar=15.0):
        self.earth = earth_body
        self.utc = utc
        self.f107 = float(f107)
        self.f107a = float(f107a)
        self.ap = [float(ap_scalar)] * 7

    def _to_datetime(self, date):
        comps = date.getComponents(self.utc)
        d = comps.getDate()
        t = comps.getTime()
        sec = float(t.getSecond())
        isec = min(int(sec), 59)  # clamp leap second 60 -> 59
        micro = min(int((sec - int(sec)) * 1.0e6), 999999)
        return datetime.datetime(int(d.getYear()), int(d.getMonth()), int(d.getDay()),
                                 int(t.getHour()), int(t.getMinute()), isec, micro,
                                 tzinfo=datetime.timezone.utc)

    @jpype.JOverride
    def getFrame(self):
        return self.earth.getBodyFrame()

    @jpype.JOverride
    def getDensity(self, date, position, frame):
        # Transform Cartesian vector to geodetic coordinates
        gp = self.earth.transform(position, frame, date)
        alt_km = gp.getAltitude() * 0.001
        lat_deg = FastMath.toDegrees(gp.getLatitude())
        lon_deg = FastMath.toDegrees(gp.getLongitude())

        if alt_km < 0.0:
            alt_km = 0.0
        elif alt_km > 1000.0:
            return 0.0

        # Convert the *actual* Orekit date to a Python UTC datetime (no frozen epoch!)
        dt_py = self._to_datetime(date)

        # Evaluate PyMSIS in storm-time Ap mode (same mode as the native default in v1.0.2)
        try:
            out = pymsis.calculate(
                dt_py, lon_deg, lat_deg, alt_km,
                self.f107, self.f107a, [self.ap],
                geomagnetic_activity=-1, version=2.1
            )
            rho = float(out.squeeze()[0])
            return 0.0 if (math.isnan(rho) or rho < 0.0) else rho
        except Exception:
            return 0.0

    @jpype.JOverride
    def getVelocity(self, date, position, frame):
        body_to_frame = self.earth.getBodyFrame().getTransformTo(frame, date)
        pos_in_body = body_to_frame.getInverse().transformPosition(position)
        pv_in_body = PVCoordinates(pos_in_body, Vector3D.ZERO)
        return body_to_frame.transformPVCoordinates(pv_in_body).getVelocity()


def build_propagator(orbit, mass_kg, atm_model, area_m2=2.0, cd=2.2):
    initial_state = SpacecraftState(orbit, mass_kg)
    min_step = 0.001
    max_step = 60.0
    pos_error = 10.0
    tolerances = NumericalPropagator.tolerances(pos_error, orbit, OrbitType.CARTESIAN)

    integrator = DormandPrince853Integrator(min_step, max_step, tolerances[0], tolerances[1])
    propagator = NumericalPropagator(integrator)
    propagator.setOrbitType(OrbitType.CARTESIAN)
    propagator.setInitialState(initial_state)
    propagator.addForceModel(NewtonianAttraction(orbit.getMu()))
    propagator.addForceModel(DragForce(atm_model, IsotropicDrag(area_m2, cd)))
    return propagator


def main():
    print("==========================================================================")
    print("  NRLMSIS 2.1 BENCHMARK: Native JNI Integration vs PyMSIS 2.1")
    print("==========================================================================")

    utc = TimeScalesFactory.getUTC()
    itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    gcrf = FramesFactory.getGCRF()
    earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                             Constants.WGS84_EARTH_FLATTENING, itrf)
    epoch = AbsoluteDate(2026, 10, 25, 12, 0, 0.0, utc)
    py_date = datetime.datetime(2026, 10, 25, 12, 0, 0, tzinfo=datetime.timezone.utc)

    # Initialize Native Atmosphere Model
    Nrlmsis21Atmosphere = get_atmosphere_class()
    ConstantSpaceWeather = get_constant_weather_class()
    sw = ConstantSpaceWeather(150.0, 150.0, 15.0)
    atm_native = Nrlmsis21Atmosphere(earth, sw, utc)

    # -------------------------------------------------------------------------
    # PART 1: Altitude Density Profile & Numerical Parity Check
    # -------------------------------------------------------------------------
    print("\n--- 1. Numerical Parity Across Altitudes (Equator, Lon = 0 deg) ---")
    altitudes_km = np.linspace(150.0, 800.0, 27)
    rho_native_list = []
    rho_pymsis_list = []

    print(f"{'Alt (km)':>8} | {'Native (kg/m3)':>18} | {'PyMSIS (kg/m3)':>18} | {'Rel Diff (%)':>14}")
    print("-" * 66)

    for alt in altitudes_km:
        r_m = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + alt * 1000.0
        pos_gcrf = itrf.getTransformTo(gcrf, epoch).transformPosition(Vector3D(r_m, 0.0, 0.0))

        # Native JNI density
        rho_nat = atm_native.getDensity(epoch, pos_gcrf, gcrf)
        rho_native_list.append(rho_nat)

        # PyMSIS density
        if HAS_PYMSIS:
            out_py = pymsis.calculate(
                py_date, 0.0, 0.0, alt, 150.0, 150.0, [[15.0] * 7], version=2.1
            )
            rho_py = float(out_py.squeeze()[0])
            rho_pymsis_list.append(rho_py)
            rel_diff = abs(rho_nat - rho_py) / rho_nat * 100.0 if rho_nat > 0 else 0.0
        else:
            rho_py = float("nan")
            rho_pymsis_list.append(rho_py)
            rel_diff = 0.0

        if alt in [150.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]:
            print(f"{alt:8.1f} | {rho_nat:18.5e} | {rho_py:18.5e} | {rel_diff:13.4e}%")

    max_rel_diff = np.nanmax(np.abs(np.array(rho_native_list) - np.array(rho_pymsis_list)) / np.array(rho_native_list)) * 100.0
    print(f"\nMaximum relative discrepancy across profile: {max_rel_diff:.4e}%")

    # -------------------------------------------------------------------------
    # PART 2: Point-by-Point Evaluation Latency (Inner ODE Solver Pattern)
    # -------------------------------------------------------------------------
    print("\n--- 2. Evaluation Latency Benchmark (1,000 Sequential State Queries) ---")
    n_evals = 1000
    pos_sample = itrf.getTransformTo(gcrf, epoch).transformPosition(
        Vector3D(Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400000.0, 0.0, 0.0)
    )

    # Warmup
    for _ in range(50):
        _ = atm_native.getDensity(epoch, pos_sample, gcrf)

    # Native JNI benchmark
    t0 = time.perf_counter()
    for _ in range(n_evals):
        _ = atm_native.getDensity(epoch, pos_sample, gcrf)
    t_native = time.perf_counter() - t0
    lat_native_us = (t_native / n_evals) * 1e6

    print(f"Native JNI Adapter : {t_native*1000.0:6.2f} ms total | {lat_native_us:6.2f} us per evaluation")

    if HAS_PYMSIS:
        # PyMSIS scalar loop benchmark (simulating Python-level ODE callback)
        t0 = time.perf_counter()
        for _ in range(n_evals):
            _ = pymsis.calculate(py_date, 0.0, 0.0, 400.0, 150.0, 150.0, [[15.0] * 7], version=2.1)
        t_pymsis = time.perf_counter() - t0
        lat_pymsis_us = (t_pymsis / n_evals) * 1e6
        speedup = lat_pymsis_us / lat_native_us
        print(f"PyMSIS Scalar Loop : {t_pymsis*1000.0:6.2f} ms total | {lat_pymsis_us:6.2f} us per evaluation")
        print(f"Native Acceleration: {speedup:6.1f}x faster than scalar PyMSIS")
    else:
        lat_pymsis_us = 0.0

    # -------------------------------------------------------------------------
    # PART 3: 1-Orbit Propagation Comparison
    # -------------------------------------------------------------------------
    print("\n--- 3. Numerical Orbit Propagation (1 Orbit ~ 92.5 min) ---")
    mu = Constants.WGS84_EARTH_MU
    a0 = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0
    orbit = KeplerianOrbit(a0, 0.001, math.radians(51.6), 0.0, 0.0, 0.0,
                           PositionAngleType.TRUE, gcrf, epoch, mu)
    mass_kg = 500.0
    period_s = 2.0 * math.pi * math.sqrt(a0**3 / mu)
    target_1rev = epoch.shiftedBy(period_s)

    # Propagate with Native JNI
    prop_native = build_propagator(orbit, mass_kg, atm_native)
    t0 = time.perf_counter()
    st_nat = prop_native.propagate(target_1rev)
    t_prop_nat = time.perf_counter() - t0
    decay_nat = st_nat.getOrbit().getA() - a0

    print(f"Native JNI Propagator : Run Time = {t_prop_nat*1000.0:6.2f} ms | Semi-Major Axis Decay = {decay_nat:7.3f} m")

    if HAS_PYMSIS:
        # Propagate with PyMSIS adapter (JPype callback)
        atm_pymsis = PyMsisAtmosphere(earth, 150.0, 150.0, 15.0)
        prop_py = build_propagator(orbit, mass_kg, atm_pymsis)
        t0 = time.perf_counter()
        st_py = prop_py.propagate(target_1rev)
        t_prop_py = time.perf_counter() - t0
        decay_py = st_py.getOrbit().getA() - a0

        print(f"PyMSIS Proxy Propagator: Run Time = {t_prop_py*1000.0:6.2f} ms | Semi-Major Axis Decay = {decay_py:7.3f} m")
        print(f"Decay Difference (Native vs PyMSIS): {abs(decay_nat - decay_py):.4e} m")
        print(f"Propagation Speedup              : {t_prop_py / t_prop_nat:.1f}x faster")
    else:
        t_prop_py = 0.0
        decay_py = 0.0

    # -------------------------------------------------------------------------
    # PART 4: Diagnostic Visualizations
    # -------------------------------------------------------------------------
    fig, axs = plt.subplots(1, 3, figsize=(16, 5))

    # Subplot 1: Altitude Density Profiles
    axs[0].semilogy(altitudes_km, rho_native_list, label="Native NRLMSIS 2.1 (JNI)", color="#1f77b4", lw=2.5)
    if HAS_PYMSIS:
        axs[0].semilogy(altitudes_km, rho_pymsis_list, label="PyMSIS 2.1", color="#d62728", ls="--", lw=1.8)
    axs[0].set_title("Altitude Density Profile", fontweight="bold")
    axs[0].set_xlabel("Altitude [km]")
    axs[0].set_ylabel(r"Density $\rho$ [$\mathrm{kg/m^3}$]")
    axs[0].grid(True, which="both", ls="--", alpha=0.5)
    axs[0].legend()

    # Subplot 2: Relative Parity Error
    if HAS_PYMSIS:
        diff_pct = (np.abs(np.array(rho_native_list) - np.array(rho_pymsis_list)) / np.array(rho_native_list)) * 100.0
        axs[1].plot(altitudes_km, diff_pct, color="#2ca02c", lw=2.0)
        axs[1].set_yscale("log")
        axs[1].set_title(r"Absolute Relative Difference ($|\Delta\rho| / \rho$)", fontweight="bold")
        axs[1].set_xlabel("Altitude [km]")
        axs[1].set_ylabel("Difference [%]")
        axs[1].grid(True, which="both", ls="--", alpha=0.5)

    # Subplot 3: Latency Comparison
    labels = ["Native JNI", "PyMSIS"]
    times = [lat_native_us, lat_pymsis_us if HAS_PYMSIS else 0.0]
    bars = axs[2].bar(labels, times, color=["#1f77b4", "#d62728"], width=0.5)
    axs[2].set_yscale("log")
    axs[2].set_title("Evaluation Latency (Single State Query)", fontweight="bold")
    axs[2].set_ylabel(r"Latency [$\mu\mathrm{s}$ / call]")
    axs[2].grid(True, axis="y", ls="--", alpha=0.5)

    for bar, val in zip(bars, times):
        axs[2].text(bar.get_x() + bar.get_width() / 2.0, val * 1.15,
                    f"{val:.1f} us", ha="center", va="bottom", fontweight="bold")

    plt.tight_layout()
    out_png = project_root / "benchmark_nrlmsis21_vs_pymsis.png"
    plt.savefig(out_png, dpi=300)
    plt.close()
    print(f"\n[OK] Benchmark plot saved to: {out_png.resolve()}")


if __name__ == "__main__":
    main()