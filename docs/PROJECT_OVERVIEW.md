# Project Overview: `orekit-nrlmsis21`

## 1. Research Objective & Motivation

Accurate non-gravitational force modeling in Low Earth Orbit (LEO, 200–1,000 km) depends heavily on empirical thermospheric mass density predictions during solar and geomagnetic variability. While **Orekit** is the reference open-source astrodynamics library for precision orbit propagation and Batch Least Squares (BLS) orbit determination, it does not ship a native **NRLMSIS 2.1** implementation. Meanwhile, external Python wrappers such as `pymsis` cannot execute directly inside Orekit's Java force-model loop without crossing the JVM $\leftrightarrow$ CPython boundary on every Runge-Kutta integrator substep ($10^5$–$10^7$ calls per multi-day arc).

`orekit-nrlmsis21` solves this gap by connecting upstream **NRLMSIS 2.1** Fortran 2003 directly to Orekit's `Atmosphere` and `CssiSpaceWeatherData` interfaces in-process via:

**Python (`orekit-jpype`) $\rightarrow$ Java (`Nrlmsis21Atmosphere`, `CssiWeatherProvider`) $\rightarrow$ C JNI Bridge $\rightarrow$ Fortran 2003 `ISO_C_BINDING` C API $\rightarrow$ NRLMSIS 2.1**

---

## 2. Independently Authored Engineering Contributions

All integration layers in the public wrapper distribution were authored specifically for this project:
1. **Fortran 2003 `ISO_C_BINDING` Layer (`native/nrlmsis21_c_api.F90`, `.h`)**: Exposes six stable C ABI entry points compiled in `-DDBLE` double precision, pre-validating the 536,576-byte `msis21.parm` table, normalizing directory strings, per-call zero-initializing output arrays, and preventing upstream Fortran `STOP` / EOF process aborts.
2. **Thread-Safe C JNI Bridge (`native/nrlmsis21_jni.c`)**: Serializes JVM access with race-free Windows `INIT_ONCE` `CRITICAL_SECTION` / Linux `pthread_mutex_t` synchronization over upstream Fortran `SAVE` state.
3. **Java Orekit `Atmosphere` & CSSI Space-Weather Adapters (`java/src/main/java/org/ssa/nrlmsis21/`)**: Full `getDensity`, `getVelocity`, `Field` Coriolis velocity partials, `Field` central-difference density gradients ($\Delta r = 1\text{ m}$), and zero-callback `CssiWeatherProvider` binding to Orekit historical $F_{10.7}$ and 7-element $A_p$ records.
4. **Python Runtime & `pymsis`-Style Source Acquisition Layer (`python/orekit_nrlmsis21/`)**: Separated wrapper-only packaging (`OREKIT_NRLMSIS21_WRAPPER_ONLY=1`), user-controlled source acquisition/validation CLI (`acquire.py`), configurable build system (`NRLMSIS21_SOURCE_DIR`), and runtime overrides (`NRLMSIS21_LIB_PATH`, `NRLMSIS21_PARM_PATH`).
5. **Scientific & Fault-Injection Verification Suite (`tests/`)**: Cross-platform verification against NRL's 200-vector double-precision benchmark, `pymsis 2.1`, Orekit `Field` derivatives, 100,000-call HotSpot C2 repeatability, and 12-hour LEO Gauss-Newton BLS $C_d$ estimation.

---

## 3. Research Applications Enabled (SSA / SDA & Orbit Determination)

- **Thermospheric Density Modeling**: High-cadence in-JVM sampling of NRLMSIS 2.1 across solar minima, moderate cycles, and extreme geomagnetic storms (Halloween 2003, Gannon May 2024).
- **Drag & Ballistic Coefficient ($C_d$) Estimation**: Direct integration with Orekit `BatchLSEstimator` and `Field` state transition matrices (`DragForce`), demonstrated by recovering $C_d = 2.2000$ ($0.0015\%$ error) from noisy 1 m Cartesian tracking over a 12-hour LEO arc.
- **Space-Weather Sensitivity & Storm-Ap Studies**: Native toggling between storm-time 7-element $A_p$ history (`switch_legacy(9) = -1`) and daily $A_p$ (`switch_legacy(9) = +1`), demonstrating `+266.91%` synthetic storm response and `2.4%`–`30.7%` historical storm deltas.
- **Space Situational & Domain Awareness (SSA/SDA)**: Enables reproducible Monte Carlo conjunction screening, orbit prediction decay sensitivity analyses, and empirical vs. physical density model comparisons inside standard Orekit workflows.

---

## 4. Five-Component Licensing & Attribution Boundary

| Layer / Component | Paths | Governing License / Legal Boundary |
|---|---|---|
| **1. Python Wrapper & Acquisition CLI** | `python/orekit_nrlmsis21/*.py`, `scripts/*.py`, `tests/*.py` | Project-authored under **Apache License, Version 2.0**. Contains no NRL code or data. |
| **2. Pure Java Orekit Adapters** | `java/src/main/java/org/ssa/nrlmsis21/*.java` | Project-authored under **Apache License, Version 2.0**. Calls generic JNI signature; contains no NRL code. |
| **3. C JNI Bridge** | `native/nrlmsis21_jni.c` | Project-authored (`Apache-2.0`); includes only `native/nrlmsis21_c_api.h`, though locally linked with Fortran objects into one shared library. |
| **4. Fortran `ISO_C_BINDING` C API** | `native/nrlmsis21_c_api.F90`, `.h` | Directly `USE`s NRL modules (`msis_constants`, `msis_init`, `msis_calc`). **Unresolved Legal Status:** Whether this constitutes a derivative work under `NRL-SOF-014-1` Section 4(b) awaits written NRL Code 7630 response ([NRL_CODE_7630_DELIVERY_AND_LEGAL_INQUIRY.md](NRL_CODE_7630_DELIVERY_AND_LEGAL_INQUIRY.md)); **not legally cleared**. |
| **5. Upstream NRLMSIS 2.1 & `msis21.parm`** | Obtained separately by end user | U.S. Government property (**`NRL-SOF-014-1`**): **non-commercial research, academic, and non-profit use only**. Excluded from public wrapper distributions. |
