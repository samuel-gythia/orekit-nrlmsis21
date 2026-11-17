import sys
import os
import time
import math
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str((project_root / "python").resolve()))

import jpype

from orekit_nrlmsis21 import init_vm

# Start the Orekit JVM with the NRLMSIS 2.1 JAR and load the native library.
init_vm()

from orekit_jpype.pyhelpers import setup_orekit_data
from orekit_nrlmsis21 import get_atmosphere_class, get_constant_weather_class

# 1. Bootstrap runtime environment and native NRLMSIS 2.1
data_dir = Path(os.environ.get("OREKIT_DATA_PATH", project_root / "orekit-data"))
setup_orekit_data(filenames=str(data_dir.resolve()), from_pip_library=False)

# Orekit core classes
from org.orekit.time import AbsoluteDate, TimeScalesFactory
from org.orekit.frames import FramesFactory
from org.orekit.bodies import OneAxisEllipsoid, CelestialBodyFactory
from org.orekit.utils import Constants, IERSConventions
from org.orekit.orbits import KeplerianOrbit, OrbitType, PositionAngleType
from org.orekit.propagation import SpacecraftState
from org.orekit.propagation.numerical import NumericalPropagator
from org.orekit.forces.gravity import NewtonianAttraction
from org.orekit.forces.drag import DragForce, IsotropicDrag
from org.hipparchus.ode.nonstiff import DormandPrince853Integrator
from org.hipparchus.geometry.euclidean.threed import Vector3D
from org.orekit.models.earth.atmosphere import (
    NRLMSISE00,
    JB2008,
    NRLMSISE00InputParameters,
    JB2008InputParameters,
)


# 2. JPype Input Parameter Adapters for Constant Weather Normalization
@jpype.JImplements(NRLMSISE00InputParameters)
class ConstantNrlmsise00Params:
    def __init__(self, f107=150.0, f107a=150.0, ap_scalar=15.0):
        self.f107 = float(f107)
        self.f107a = float(f107a)
        self.ap_arr = jpype.JArray(jpype.JDouble)([float(ap_scalar)] * 7)

    @jpype.JOverride
    def getMinDate(self):
        return AbsoluteDate.PAST_INFINITY

    @jpype.JOverride
    def getMaxDate(self):
        return AbsoluteDate.FUTURE_INFINITY

    @jpype.JOverride
    def getDailyFlux(self, date):
        return self.f107

    @jpype.JOverride
    def getAverageFlux(self, date):
        return self.f107a

    @jpype.JOverride
    def getAp(self, date):
        return self.ap_arr


@jpype.JImplements(JB2008InputParameters)
class ConstantJB2008Params:
    def __init__(self, f10=150.0, f10b=150.0, s10=150.0, s10b=150.0,
                 xm10=150.0, xm10b=150.0, y10=150.0, y10b=150.0, dstdtc=0.0):
        self.f10 = float(f10)
        self.f10b = float(f10b)
        self.s10 = float(s10)
        self.s10b = float(s10b)
        self.xm10 = float(xm10)
        self.xm10b = float(xm10b)
        self.y10 = float(y10)
        self.y10b = float(y10b)
        # dstdtc is Delta Tc (temperature increment in Kelvin from Dst). 0.0 K represents quiet/baseline.
        self.dstdtc = float(dstdtc)

    @jpype.JOverride
    def getMinDate(self):
        return AbsoluteDate.PAST_INFINITY

    @jpype.JOverride
    def getMaxDate(self):
        return AbsoluteDate.FUTURE_INFINITY

    @jpype.JOverride
    def getF10(self, date): return self.f10

    @jpype.JOverride
    def getF10B(self, date): return self.f10b

    @jpype.JOverride
    def getS10(self, date): return self.s10

    @jpype.JOverride
    def getS10B(self, date): return self.s10b

    @jpype.JOverride
    def getXM10(self, date): return self.xm10

    @jpype.JOverride
    def getXM10B(self, date): return self.xm10b

    @jpype.JOverride
    def getY10(self, date): return self.y10

    @jpype.JOverride
    def getY10B(self, date): return self.y10b

    @jpype.JOverride
    def getDSTDTC(self, date): return self.dstdtc


def build_propagator(orbit, mass_kg, atm_model, area_m2=2.0, cd=2.2):
    """Instantiates a clean NumericalPropagator with Dormand-Prince 8(5,3)."""
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
    print("  ATMOSPHERIC MODEL BENCHMARK: NRLMSIS 2.1 vs NRLMSISE-00 vs JB2008")
    print("==========================================================================")

    # Coordinate frames & celestial bodies
    utc = TimeScalesFactory.getUTC()
    itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    gcrf = FramesFactory.getGCRF()
    earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                             Constants.WGS84_EARTH_FLATTENING, itrf)
    sun = CelestialBodyFactory.getSun()
    epoch = AbsoluteDate(2026, 10, 25, 12, 0, 0.0, utc)

    # Initialize all three models with identical solar activity (F10.7=150, Ap=15, Delta Tc=0)
    Nrlmsis21Atmosphere = get_atmosphere_class()
    ConstantSpaceWeather = get_constant_weather_class()
    sw21 = ConstantSpaceWeather(150.0, 150.0, 15.0)

    atm_models = {
        "NRLMSIS 2.1": Nrlmsis21Atmosphere(earth, sw21, utc),
        "NRLMSISE-00": NRLMSISE00(ConstantNrlmsise00Params(150.0, 150.0, 15.0), sun, earth),
        "JB2008":      JB2008(ConstantJB2008Params(150.0, 150.0, dstdtc=0.0), sun, earth)
    }

    # -------------------------------------------------------------------------
    # PART 1: Altitude Density Profile Comparison (150 km to 800 km)
    # -------------------------------------------------------------------------
    altitudes_km = np.linspace(150.0, 800.0, 27)
    profile_data = {name: [] for name in atm_models}

    print("\n--- 1. Altitude Density Profiles (Equatorial Sub-Solar Meridian) ---")
    print(f"{'Alt (km)':>8} | {'NRLMSIS 2.1 (kg/m3)':>20} | {'NRLMSISE-00':>20} | {'JB2008':>20} | {'2.1 vs 00 (%)':>13}")
    print("-" * 92)

    for alt in altitudes_km:
        r_m = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + alt * 1000.0
        pos_itrf = Vector3D(r_m, 0.0, 0.0)
        pos_gcrf = itrf.getTransformTo(gcrf, epoch).transformPosition(pos_itrf)

        rho_21 = atm_models["NRLMSIS 2.1"].getDensity(epoch, pos_gcrf, gcrf)
        rho_00 = atm_models["NRLMSISE-00"].getDensity(epoch, pos_gcrf, gcrf)
        rho_jb = atm_models["JB2008"].getDensity(epoch, pos_gcrf, gcrf)

        profile_data["NRLMSIS 2.1"].append(rho_21)
        profile_data["NRLMSISE-00"].append(rho_00)
        profile_data["JB2008"].append(rho_jb)

        rel_diff_00 = ((rho_21 - rho_00) / rho_00) * 100.0 if rho_00 > 0 else 0.0
        if alt in [150.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0]:
            print(f"{alt:8.1f} | {rho_21:20.4e} | {rho_00:20.4e} | {rho_jb:20.4e} | {rel_diff_00:+12.2f}%")

    # -------------------------------------------------------------------------
    # PART 2: 24-Hour Orbit Propagation & Drag Decay
    # -------------------------------------------------------------------------
    print("\n--- 2. 24-Hour Numerical Orbit Propagation Benchmark ---")
    mu = Constants.WGS84_EARTH_MU
    a0 = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0  # 400 km circular
    orbit = KeplerianOrbit(a0, 0.001, math.radians(51.6), 0.0, 0.0, 0.0,
                           PositionAngleType.TRUE, gcrf, epoch, mu)
    mass_kg = 500.0
    area_m2 = 2.0
    cd = 2.2
    duration_s = 86400.0
    target_date = epoch.shiftedBy(duration_s)

    prop_results = {}
    time_steps_s = np.linspace(0.0, duration_s, 289)  # 5-minute sampling

    for name, model in atm_models.items():
        propagator = build_propagator(orbit, mass_kg, model, area_m2, cd)
        ephem_gen = propagator.getEphemerisGenerator()

        t0 = time.perf_counter()
        final_state = propagator.propagate(target_date)
        wall_time = time.perf_counter() - t0

        ephemeris = ephem_gen.getGeneratedEphemeris()
        a_final = final_state.getOrbit().getA()
        total_decay_m = a_final - a0

        # Sample orbital elements and in-situ density along the arc
        history_a = []
        history_rho = []
        for dt in time_steps_s:
            st = ephemeris.propagate(epoch.shiftedBy(float(dt)))
            history_a.append(st.getOrbit().getA() - a0)
            rho_t = model.getDensity(st.getDate(), st.getPosition(), gcrf)
            history_rho.append(rho_t)

        prop_results[name] = {
            "wall_time": wall_time,
            "final_a": a_final,
            "decay_m": total_decay_m,
            "history_a": np.array(history_a),
            "history_rho": np.array(history_rho)
        }

        print(f"[{name:<11}] Run Time: {wall_time:6.3f}s | Final a: {a_final/1000.0:9.4f} km | 24h Decay: {total_decay_m:7.2f} m")

    # -------------------------------------------------------------------------
    # PART 3: Publication-Grade Multi-Panel Plot
    # -------------------------------------------------------------------------
    fig, axs = plt.subplots(2, 2, figsize=(14, 10))
    colors = {"NRLMSIS 2.1": "#1f77b4", "NRLMSISE-00": "#d62728", "JB2008": "#2ca02c"}

    # Subplot 1: Altitude Density Profile (Semi-log)
    ax1 = axs[0, 0]
    for name in atm_models:
        ax1.semilogy(altitudes_km, profile_data[name], label=name, color=colors[name], lw=2.0)
    ax1.set_title("Equatorial Neutral Density Profile", fontsize=12, fontweight="bold")
    ax1.set_xlabel("Altitude [km]")
    ax1.set_ylabel(r"Total Mass Density $\rho$ [$\mathrm{kg/m^3}$]")
    ax1.grid(True, which="both", ls="--", alpha=0.5)
    ax1.legend(loc="upper right")

    # Subplot 2: Relative Density Discrepancy w.r.t. NRLMSIS 2.1
    ax2 = axs[0, 1]
    rho_ref = np.array(profile_data["NRLMSIS 2.1"])
    for name in ["NRLMSISE-00", "JB2008"]:
        diff_pct = ((np.array(profile_data[name]) - rho_ref) / rho_ref) * 100.0
        ax2.plot(altitudes_km, diff_pct, label=f"({name} - 2.1) / 2.1", color=colors[name], lw=2.0)
    ax2.axhline(0, color="black", lw=1.0, ls=":")
    ax2.set_title("Relative Discrepancy vs NRLMSIS 2.1", fontsize=12, fontweight="bold")
    ax2.set_xlabel("Altitude [km]")
    ax2.set_ylabel(r"Relative Difference [$\%$]")
    ax2.grid(True, ls="--", alpha=0.5)
    ax2.legend(loc="lower left")

    # Subplot 3: Semi-Major Axis Orbital Decay Arc
    ax3 = axs[1, 0]
    time_hours = time_steps_s / 3600.0
    for name in atm_models:
        ax3.plot(time_hours, prop_results[name]["history_a"], label=name, color=colors[name], lw=2.0)
    ax3.set_title(r"24-Hour Semi-Major Axis Decay ($400\ \mathrm{km}$ Circular LEO)", fontsize=12, fontweight="bold")
    ax3.set_xlabel("Elapsed Time [hours]")
    ax3.set_ylabel(r"$\Delta a$ Decay [$\mathrm{m}$]")
    ax3.grid(True, ls="--", alpha=0.5)
    ax3.legend(loc="lower left")

    # Subplot 4: In-Situ Density Along Propagation Orbit
    ax4 = axs[1, 1]
    sample_window = time_hours <= 6.0  # First 4 orbits
    for name in atm_models:
        ax4.plot(time_hours[sample_window], prop_results[name]["history_rho"][sample_window],
                 label=name, color=colors[name], lw=1.5, alpha=0.85)
    ax4.set_title("In-Situ Density Variation Across First 4 Orbits (Diurnal Bulge)", fontsize=12, fontweight="bold")
    ax4.set_xlabel("Elapsed Time [hours]")
    ax4.set_ylabel(r"Orbital Density $\rho$ [$\mathrm{kg/m^3}$]")
    ax4.grid(True, ls="--", alpha=0.5)
    ax4.legend(loc="upper right")

    plt.tight_layout()
    output_png = project_root / "comparison_msis21_msise00_jb2008.png"
    plt.savefig(output_png, dpi=300)
    plt.close()
    print(f"\n[OK] Comparative figure saved to: {output_png.resolve()}")


if __name__ == "__main__":
    main()