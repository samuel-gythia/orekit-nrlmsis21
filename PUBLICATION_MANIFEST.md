# Publication Manifest (`orekit-nrlmsis21` v1.0.2 Release Candidate)

This manifest classifies every component associated with `orekit-nrlmsis21` for public repository readiness and legal review. No legal determination is made by this document; unresolved licensing questions are recorded explicitly and tracked in [`RELEASE_BLOCKERS.md`](RELEASE_BLOCKERS.md).

---

## Summary of Classification Categories

| Category | Meaning | Distribution Readiness |
|---|---|---|
| **A** | Independently authored components potentially eligible for release under our own candidate license (`Apache-2.0` candidate, **not yet an approved decision**) | Pending final license confirmation & replacement of draft metadata placeholders |
| **B** | Components requiring written clarification from NRL Code 7630 / NRL IP Counsel before distribution (`NRL-SOF-014-1` Section 4b) | **`BLOCKED`** pending written NRL clarification |
| **C** | Third-party dependencies and verbatim upstream notices requiring attribution/notices | Attribution/notice compliance required; external libraries are not bundled |
| **D** | Excluded upstream NRLMSIS 2.1 material, precompiled binaries, datasets, and generated artefacts | **Excluded** from `orekit-nrlmsis21-publication-prep` |

---

## Category A — Independently Authored Components (Candidate License Only)

These files were authored specifically for `orekit-nrlmsis21` and contain **no** upstream NRLMSIS 2.1 Fortran source lines, parameter tables (`msis21.parm`), or NRL binaries. Use of a permissive license such as **Apache-2.0** is a **candidate** approach, subject to final review and NRL guidance.

### A.1 Python Wrapper & Source Acquisition Package (`python/orekit_nrlmsis21/`)
- `python/orekit_nrlmsis21/__init__.py` — High-level JVM initialization (`init_vm`), CSSI weather/atmosphere factories (`create_cssi_weather_provider`, `create_atmosphere`), and lazy acquisition exports.
- `python/orekit_nrlmsis21/atmosphere.py` — High-level Python wrapper over the Java `Nrlmsis21Atmosphere` adapter.
- `python/orekit_nrlmsis21/loader.py` — Runtime locator for user-supplied shared libraries (`NRLMSIS21_LIB_PATH`), parameter tables (`NRLMSIS21_PARM_PATH`, `536,576`-byte verification), and Java adapter JAR (`orekit-nrlmsis21-1.0.2.jar`).
- `python/orekit_nrlmsis21/acquire.py` — `pymsis`-inspired user-controlled NRL source acquisition and validation helper (`validate_nrlmsis21_directory`, `extract_nrlmsis21_archive`, `download_nrlmsis21_source` requiring explicit interactive `"YES"` confirmation).
- `python/orekit_nrlmsis21/lib/.gitkeep` — Empty directory placeholder for locally compiled JAR/native artifacts.

### A.2 Java Orekit Atmosphere & Space-Weather Adapter (`java/src/main/java/org/ssa/nrlmsis21/`)
- `SpaceWeatherProvider.java` — Pure Java interface for $F_{10.7}$ and 7-element $A_p$ arrays.
- `CssiWeatherProvider.java` — Zero-callback Java adapter over Orekit `CssiSpaceWeatherData` (converts historical 3-hour $A_p$ records and 81-day centered $F_{10.7A}$).
- `ConstantSpaceWeather.java` — Constant space-weather calibration/verification provider.
- `Nrlmsis21Atmosphere.java` — Full implementation of Orekit `org.orekit.models.earth.atmosphere.Atmosphere` (including `Field` finite-difference density gradients and Coriolis velocity partials).
- `Nrlmsis21Native.java` — Java class declaring the 6 `native` JNI entry points (`load`, 2-arg/3-arg `init`, `setStormApMode`, `isStormApMode`, `isInitialized`, `calc`). *Note: Because `Nrlmsis21Native.java` defines the Java side of the JNI boundary into Category B native code, Question Q1 in [`docs/NRL_CODE_7630_DELIVERY_AND_LEGAL_INQUIRY.md`](docs/NRL_CODE_7630_DELIVERY_AND_LEGAL_INQUIRY.md) also explicitly requests NRL confirmation that pure Java adapters calling JNI remain independently distributable.*

### A.3 Build Scripts, Packaging & CI Configuration
- `CMakeLists.txt` — Configurable CMake build script accepting external `-DNRLMSIS21_SOURCE_DIR=<path>`, verifying all 8 upstream `.F90` files at configure time, and compiling `nrlmsis21_jni`. *(Note: references upstream NRLMSIS 2.1 filenames as user-supplied external build inputs; no upstream code is embedded.)*
- `pom.xml`, `pyproject.toml`, `setup.py`, `MANIFEST.in`, `build_dev.py`, `.github/workflows/ci.yml`, `.gitignore`.
- `scripts/acquire_nrlmsis21.py`, `scripts/build_java.ps1`, `scripts/run_milestone1.ps1`, `scripts/run_milestone2.ps1`, `scripts/run_milestone3.ps1`, `scripts/benchmark_suite.py`, `scripts/check_orekit_env.py`, `scripts/compare_atmosphere_models.py`, `scripts/compare_nrlmsis21_vs_pymsis.py`, `scripts/download_data.py`, `scripts/inspect_jars.py`, `scripts/setup_data.py`.

### A.4 Documentation & Verification Tests
- `README.md`, `CONTRIBUTING.md`, `PUBLICATION_MANIFEST.md`, `THIRD_PARTY_NOTICES.md`, `RELEASE_BLOCKERS.md`.
- `docs/PROJECT_OVERVIEW.md`, `docs/ARCHITECTURE.md`, `docs/VALIDATION.md`, `docs/REPRODUCIBILITY.md`, `docs/NRL_CODE_7630_DELIVERY_AND_LEGAL_INQUIRY.md`.
- `tests/*.py` (`compare_ref_dp.py`, `test_c_api.py`, `test_jni_bridge.py`, `test_nrl_reference.py`, `test_cssi_adapter_verification.py`, `test_orekit_atmosphere.py`, `test_orekit_propagation.py`, `test_batch_least_squares.py`, `test_fault_injection_regression.py`, `test_user_supplied_source_and_loader.py`). *(Note: regression tests verify numerical parity against reference tables obtained separately by the user; zero NRL reference files are bundled.)*

### A.5 Existing Working-Draft License/Notice Files Preserved Unaltered
- `LICENSE` and `NOTICE` — Preserved verbatim from the development repository without modification (per release-preparation rules). Both still reflect pre-confirmation `Apache-2.0` composite wording and unverified `[removed legacy placeholder]` / `[removed legacy placeholder]` placeholders; they must be reviewed and replaced prior to actual publication.

---

## Category B — Components Requiring Written NRL Clarification Before Distribution

Under `NRL-SOF-014-1` Section 4(b), modifications and derivative works of the MSIS® Software carry mandatory open-source release, change-notice, U.S. Government license, and **NRL Code 7630 delivery** obligations. Whether linking or interfacing with NRLMSIS 2.1 Fortran modules triggers Section 4(b) is **not legally resolved**.

| Component | Technical Coupling Assessment | Unresolved Legal Questions |
|---|---|---|
| **`native/nrlmsis21_c_api.F90`** | Directly executes Fortran `use msis_constants, only: rp`, `use msis_init, only: msisinit, tselec`, and `use msis_calc, only: msiscalc`, and invokes `msisinit`, `tselec`, and `msiscalc`. Exports 6 `bind(C)` symbols (`msis21_init_c`, `msis21_init_ex_c`, `msis21_set_storm_ap_mode_c`, `msis21_get_storm_ap_mode_c`, `msis21_is_initialized_c`, `msis21_calc_c`) plus `msis21.parm` finite/size validation and `NaN` guards. | Does a Fortran `ISO_C_BINDING` wrapper that `USE`s NRLMSIS 2.1 modules constitute a "derivative work of the Software" under `NRL-SOF-014-1` Section 4(b)? May it be distributed under our own permissive license, or must Section 4(b) delivery and `NRL-SOF-014-1` flow-down apply? |
| **`native/nrlmsis21_c_api.h`** | Pure C header (`extern "C"` prototypes + integer status macros `MSIS21_SUCCESS` .. `MSIS21_ERR_NOT_INITIALIZED`). Contains zero NRL Fortran code or upstream symbol names, but defines the exact C ABI matching `native/nrlmsis21_c_api.F90`. | Clarify whether this ABI header is separable from `nrlmsis21_c_api.F90` for independent licensing/distribution or follows `nrlmsis21_c_api.F90` under Section 4(b). |
| **`native/nrlmsis21_jni.c`** | Pure C source including `<jni.h>`, Win32/POSIX mutex headers (`CRITICAL_SECTION` / `pthread_mutex_t`), and `"nrlmsis21_c_api.h"`. Implements the 6 JNI C functions matching `Nrlmsis21Native.java`. Contains zero direct calls to NRL Fortran symbols in source form, **however** when built via `CMakeLists.txt` it is compiled and linked together with `nrlmsis21_c_api.F90` and the user-supplied upstream NRLMSIS `.F90` object files into a single shared library (`libnrlmsis21_jni.dll`/`.so`). | Can `native/nrlmsis21_jni.c` be distributed independently in source form under a permissive license if it only includes `nrlmsis21_c_api.h`, and what Section 4(b)/4(c) obligations attach once an end user compiles/links it with NRLMSIS 2.1 locally? |

---

## Category C — Third-Party Dependencies & Mandatory Notices

| Dependency | File / Source | License / Obligations |
|---|---|---|
| **Upstream NRLMSIS 2.1** (user-supplied) | `python/orekit_nrlmsis21/nrlmsis2.1_license.txt` (bundled verbatim) | `NRL-SOF-014-1` Open Source Academic Research License Agreement. Strict **non-commercial research/academic/non-profit only** restriction; written NRL IP Counsel consent required for any commercial use or fee-based data products (Section 4a); mandatory Section 4c statement and `MSIS®` trademark notice (Section 3). |
| **Orekit & Hipparchus** | External Java/pip runtime (`orekit-jpype >= 12.0`) | `Apache License, Version 2.0`. Not bundled in source repo. |
| **JPype1** | External Python/C++ dependency (`jpype1 >= 1.4`) | `Apache License, Version 2.0`. Not bundled in source repo. |
| **NumPy** | External Python dependency (`numpy >= 1.20`) | `BSD 3-Clause License`. Not bundled in source repo. |
| **GNU GCC / GFortran Runtime** | Build toolchain / local shared-library linking | `GPL-3.0-or-later WITH GCC-exception-3.1`. Applies when compiling local `libnrlmsis21_jni` shared libraries or redistributing binaries containing `libgfortran`/`libgcc`. |

---

## Category D — Excluded Upstream Material & Generated Artefacts

All of the following exist in the private development repository (`orekit-nrlmsis21`) or prior build outputs and are **intentionally excluded** from `orekit-nrlmsis21-publication-prep`:

1. **Upstream NRLMSIS 2.1 Sources, Data & Reference Files (`external/NRLMSIS2.1/`)**:
   - `msis_constants.F90`, `msis_init.F90`, `msis_utils.F90`, `msis_dfn.F90`, `msis_tfn.F90`, `msis_gfn.F90`, `msis_gtd8d.F90`, `msis_calc.F90`, `msis2.1_test.F90`
   - `msis21.parm` (`536,576` bytes), `msis2.1_test_in.txt`, `msis2.1_test_ref_dp.txt`, `readme.txt`, `subroutine_dir.png`, `nrlmsis2.1_license..txt`, `nrlmsis2.1_license.txt`
2. **Compiled Binaries & Duplicate Runtime Files**:
   - `python/orekit_nrlmsis21/lib/libnrlmsis21_jni.dll`, `libnrlmsis21_jni.so`, `libgfortran.so.5`, `libquadmath.so.0`, `msis21.parm`
   - `python/orekit_nrlmsis21/lib/orekit-nrlmsis21-1.0.jar`, `python/orekit_nrlmsis21/lib/orekit-nrlmsis21-1.0.2.jar` (built locally from `java/` sources instead of committing binary JARs)
   - Duplicate `python/orekit_nrlmsis21/LICENSE-NRLMSIS2.1.txt` (superseded by canonical `python/orekit_nrlmsis21/nrlmsis2.1_license.txt`)
3. **Git History Containing Tracked Upstream/Binary Commits**:
   - `.git/` directory omitted (commits `75ca07c` and `622140c` in the development repository tracked `external/NRLMSIS2.1/*`, `msis21.parm`, `.dll`, and `.so` binaries).
4. **Geophysical Datasets, Build Caches, Diagnostics & Internal Audits**:
   - `orekit-data/`, `orekit_classpath.txt`, `build/`, `target/`, `dist/`, `python/orekit_nrlmsis21.egg-info/`, `__pycache__/`
   - `audit_reports/`, `scripts/diagnostics/`, `tests/test_batch_least_squares.py.bak`, `*.png`, `*.csv`.
