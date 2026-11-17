"""
Scientifically validated Batch Least Squares orbit determination test for Orekit
with native NRLMSIS 2.1 atmospheric drag acceleration and Cd estimation.
"""
from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path
import numpy as np

project_root = Path(__file__).resolve().parent.parent.resolve()
try:
    import orekit_nrlmsis21  # noqa: F401
except ImportError:
    sys.path.insert(0, str((project_root / "python").resolve()))

import jpype
import orekit_jpype as orekit
from orekit_nrlmsis21 import init_vm, create_atmosphere, create_constant_weather


def _resolve_orekit_data() -> Path:
    env_path = os.environ.get("OREKIT_DATA_PATH")
    candidates = []
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend([
        project_root / "orekit-data",
        Path("orekit-data"),
    ])
    for candidate in candidates:
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        "Could not locate orekit-data directory. Set OREKIT_DATA_PATH or place orekit-data/ in repo root."
    )


def _setup_runtime() -> None:
    if not jpype.isJVMStarted():
        orekit.initVM()
    init_vm()
    from orekit_jpype.pyhelpers import setup_orekit_data

    setup_orekit_data(filenames=str(_resolve_orekit_data()), from_pip_library=False)


def run_batch_least_squares_test() -> int:
    _setup_runtime()

    from org.orekit.time import AbsoluteDate, TimeScalesFactory
    from org.orekit.frames import FramesFactory
    from org.orekit.bodies import OneAxisEllipsoid
    from org.orekit.utils import Constants, IERSConventions, PVCoordinates
    from org.orekit.orbits import KeplerianOrbit, CartesianOrbit, OrbitType, PositionAngleType
    from org.orekit.propagation import SpacecraftState
    from org.orekit.propagation.numerical import NumericalPropagator
    from org.orekit.forces.gravity import NewtonianAttraction
    from org.orekit.forces.drag import DragForce, IsotropicDrag
    from org.hipparchus.ode.nonstiff import DormandPrince853Integrator
    from org.hipparchus.linear import QRDecomposer
    from org.hipparchus.optim.nonlinear.vector.leastsquares import GaussNewtonOptimizer
    from org.orekit.estimation.leastsquares import BatchLSEstimator
    from org.orekit.propagation.conversion import DormandPrince853IntegratorBuilder, NumericalPropagatorBuilder
    from org.orekit.estimation.measurements import Position, ObservableSatellite
    from org.hipparchus.geometry.euclidean.threed import Vector3D

    print("==========================================================================")
    print("  BATCH LEAST SQUARES ORBIT DETERMINATION (NRLMSIS 2.1)")
    print("==========================================================================")

    utc = TimeScalesFactory.getUTC()
    itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
    gcrf = FramesFactory.getGCRF()
    earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                             Constants.WGS84_EARTH_FLATTENING, itrf)
    epoch = AbsoluteDate(2026, 10, 25, 12, 0, 0.0, utc)
    mu = Constants.WGS84_EARTH_MU

    # 1. Truth Trajectory Specification
    # Spacecraft: 500 kg, Area = 2.0 m^2, Cd = 2.20 in 400 km circular LEO (i = 51.6 deg)
    true_cd = 2.20
    true_area = 2.0
    mass_kg = 500.0
    a0 = Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0
    true_orbit = KeplerianOrbit(a0, 0.001, math.radians(51.6), 0.0, 0.0, 0.0,
                                PositionAngleType.TRUE, gcrf, epoch, mu)

    sw = create_constant_weather(150.0, 150.0, 15.0)
    atm21 = create_atmosphere(earth, sw, utc)

    # Tight ODE integrator tolerance (dP = 1 mm) to eliminate numerical truncation error
    ode_tol_m = 0.001
    tolerances = NumericalPropagator.tolerances(ode_tol_m, true_orbit, OrbitType.CARTESIAN)
    integrator = DormandPrince853Integrator(0.001, 60.0, tolerances[0], tolerances[1])
    truth_prop = NumericalPropagator(integrator)
    truth_prop.setOrbitType(OrbitType.CARTESIAN)
    truth_prop.setInitialState(SpacecraftState(true_orbit, mass_kg))
    truth_prop.addForceModel(NewtonianAttraction(mu))
    truth_prop.addForceModel(DragForce(atm21, IsotropicDrag(true_area, true_cd)))

    # 2. Synthetic Cartesian Position Observations (12 Hours, dt = 60s, sigma = 1.0 m)
    duration_s = 43200.0
    sample_step_s = 60.0
    n_meas = int(duration_s / sample_step_s)
    print(f"Generating {n_meas} synthetic Cartesian position observations across 12-hour arc...")

    sat = ObservableSatellite(0)
    pos_sigma = 1.0  # 1.0 m 1-sigma per component
    base_weight = 1.0
    measurements = []

    rng = np.random.default_rng(42)
    obs_epochs = []
    obs_positions = []

    # Generate observations directly at discrete integration steps (no interpolation artifacts)
    for i in range(n_meas):
        t_meas = epoch.shiftedBy(float(i * sample_step_s))
        true_pos = truth_prop.propagate(t_meas).getPosition()
        noise = rng.normal(0.0, pos_sigma, 3)
        noisy_pos = Vector3D(true_pos.getX() + float(noise[0]),
                             true_pos.getY() + float(noise[1]),
                             true_pos.getZ() + float(noise[2]))

        meas = Position(t_meas, noisy_pos, pos_sigma, base_weight, sat)
        measurements.append(meas)
        obs_epochs.append(t_meas)
        obs_positions.append(noisy_pos)

    print(f"[OK] Generated {len(measurements)} position observations with sigma = {pos_sigma} m.")

    # 3. A Priori State and Drag Parameter Perturbation
    # Operational LEO a priori offsets: ~173 m position, ~0.17 m/s velocity, Cd guess = 1.60
    pos_offset = Vector3D(100.0, -100.0, 100.0)
    vel_offset = Vector3D(0.1, -0.1, 0.1)
    init_pv = true_orbit.getPVCoordinates()
    corrupted_pos = init_pv.getPosition().add(pos_offset)
    corrupted_vel = init_pv.getVelocity().add(vel_offset)

    a_priori_orbit = CartesianOrbit(PVCoordinates(corrupted_pos, corrupted_vel), gcrf, epoch, mu)
    a_priori_cd = 1.60

    print("\n--- A Priori Parameter Setup ---")
    print(f"  True Initial Orbit     : a = {true_orbit.getA()/1000.0:.3f} km, Cd = {true_cd:.2f}")
    print(f"  A Priori Guess         : a = {a_priori_orbit.getA()/1000.0:.3f} km, Cd = {a_priori_cd:.2f}")
    print(f"  A Priori Position Err  : {pos_offset.getNorm():.3f} m")
    print(f"  A Priori Velocity Err  : {vel_offset.getNorm():.5f} m/s")

    # 4. Estimator Configuration
    integrator_builder = DormandPrince853IntegratorBuilder(0.001, 60.0, ode_tol_m)
    prop_builder = NumericalPropagatorBuilder(a_priori_orbit, integrator_builder, PositionAngleType.TRUE, 1.0)
    prop_builder.setMass(mass_kg)
    prop_builder.addForceModel(NewtonianAttraction(mu))

    est_drag = IsotropicDrag(true_area, a_priori_cd)
    est_drag_force = DragForce(atm21, est_drag)
    prop_builder.addForceModel(est_drag_force)

    cd_driver = None
    for driver in est_drag_force.getParametersDrivers():
        if "drag coefficient" in driver.getName().lower() or "cd" in driver.getName().lower():
            driver.setSelected(True)
            driver.setScale(1.0)
            cd_driver = driver
            print(f"  Selected Parameter     : {driver.getName()} (Scale = 1.0, Initial = {driver.getValue():.2f})")

    decomposer = QRDecomposer(1.0e-11)
    optimizer = GaussNewtonOptimizer(decomposer, False)
    estimator = BatchLSEstimator(optimizer, prop_builder)
    estimator.setMaxIterations(15)
    estimator.setMaxEvaluations(30)
    estimator.setParametersConvergenceThreshold(1.0e-3)

    for m in measurements:
        estimator.addMeasurement(m)

    # 5. Execute Least Squares Differential Correction
    print("\nExecuting Gauss-Newton Differential Correction...")
    t0 = time.perf_counter()
    estimated_propagators = estimator.estimate()
    fit_duration = time.perf_counter() - t0

    # 6. Extraction of Results and State Verification
    calibrated_propagator = estimated_propagators[0]
    final_orbit = calibrated_propagator.getInitialState().getOrbit()
    final_pv = final_orbit.getPVCoordinates()

    final_pos_err = final_pv.getPosition().subtract(init_pv.getPosition()).getNorm()
    final_vel_err = final_pv.getVelocity().subtract(init_pv.getVelocity()).getNorm()
    recovered_cd = cd_driver.getValue() if cd_driver else None

    # 7. Residual Analysis
    res_x, res_y, res_z = [], [], []
    for t_m, y_obs in zip(obs_epochs, obs_positions):
        y_est = calibrated_propagator.propagate(t_m).getPosition()
        diff = y_obs.subtract(y_est)
        res_x.append(diff.getX())
        res_y.append(diff.getY())
        res_z.append(diff.getZ())

    res_x = np.array(res_x)
    res_y = np.array(res_y)
    res_z = np.array(res_z)
    res_3d = np.sqrt(res_x**2 + res_y**2 + res_z**2)
    res_3d_rms = np.sqrt(np.mean(res_3d**2))

    # 8. Physical Covariance and Formal Uncertainties
    optimum = estimator.getOptimum()
    normalized_rms = optimum.getRMS()
    cov_normalized = np.array(optimum.getCovariances(1.0e-11).getData())

    # Extract parameter driver scales to convert normalized covariance to physical units
    scales = []
    for driver in prop_builder.getOrbitalParametersDrivers().getDrivers():
        scales.append(float(driver.getScale()))
    scales.append(float(cd_driver.getScale()))
    scales = np.array(scales)

    cov_physical = cov_normalized * np.outer(scales, scales)
    formal_stds = np.sqrt(np.diag(cov_physical))
    formal_pos_1sigma = np.sqrt(np.sum(formal_stds[0:3]**2))
    formal_vel_1sigma = np.sqrt(np.sum(formal_stds[3:6]**2))
    formal_cd_1sigma = formal_stds[6]

    print("\n==========================================================================")
    print("  ESTIMATION METRICS & SCIENTIFIC VERIFICATION")
    print("==========================================================================")
    print(f"  Convergence Runtime    : {fit_duration:.3f} s (informational)")
    print(f"  Iterations / Evals     : {estimator.getIterationsCount()} / {estimator.getEvaluationsCount()}")
    print(f"  Normalized Cost RMS    : {normalized_rms:.4f} (Theoretical expectation: ~1.000)")
    print(f"  Position Residual RMS  : {res_3d_rms:.3f} m (Theoretical 3D noise: ~1.732 m)")
    print(f"  Residual Mean (X,Y,Z)  : [{res_x.mean():+.3f}, {res_y.mean():+.3f}, {res_z.mean():+.3f}] m")
    print(f"  Residual Std  (X,Y,Z)  : [{res_x.std():.3f}, {res_y.std():.3f}, {res_z.std():.3f}] m")
    print("\n--- Orbit & Parameter Recovery vs Known Truth ---")
    print(f"  Initial Position Error : {pos_offset.getNorm():8.3f} m  --> Final: {final_pos_err:6.3f} m (Formal 3-sigma: {3*formal_pos_1sigma:.3f} m)")
    print(f"  Initial Velocity Error : {vel_offset.getNorm():8.5f} m/s--> Final: {final_vel_err:6.5f} m/s (Formal 3-sigma: {3*formal_vel_1sigma:.5f} m/s)")
    cd_err_pct = None
    if recovered_cd is not None:
        cd_err = abs(recovered_cd - true_cd)
        cd_err_pct = (cd_err / true_cd) * 100.0
        print(f"  Recovered Cd Parameter : {recovered_cd:8.4f} (True: {true_cd:.2f}, Error: {cd_err_pct:.4f}%, Formal 3-sigma: {3*formal_cd_1sigma:.4f})")

    # Rigorous physical and statistical assertions (hardware wall-clock timing is logged only):
    assert estimator.getIterationsCount() <= 6, f"Required excessive iterations: {estimator.getIterationsCount()}"

    # Residuals must follow the 1.0 m Gaussian observation distribution
    assert 0.90 <= normalized_rms <= 1.10, f"Normalized RMS {normalized_rms:.3f} indicates unmodeled signal or bias"

    # State and Cd recovery must fall within formal 3-sigma statistical confidence
    assert final_pos_err <= 3.0 * formal_pos_1sigma, f"Final position error {final_pos_err:.3f}m exceeds 3-sigma bound {3*formal_pos_1sigma:.3f}m"
    assert final_vel_err <= 3.0 * formal_vel_1sigma, f"Final velocity error {final_vel_err:.5f}m/s exceeds 3-sigma bound {3*formal_vel_1sigma:.5f}m"
    if recovered_cd is not None:
        assert cd_err_pct < 0.50, f"Cd relative error {cd_err_pct:.4f}% exceeds 0.5% tolerance"
        assert abs(recovered_cd - true_cd) <= 3.0 * formal_cd_1sigma, (
            f"Cd error {abs(recovered_cd - true_cd):.5f} exceeds 3-sigma bound {3*formal_cd_1sigma:.5f}"
        )

    print("\n[PASS] Batch Least Squares estimation successfully validated with rigorous statistics.")
    return 0


def test_batch_least_squares() -> None:
    assert run_batch_least_squares_test() == 0


if __name__ == "__main__":
    sys.exit(run_batch_least_squares_test())
