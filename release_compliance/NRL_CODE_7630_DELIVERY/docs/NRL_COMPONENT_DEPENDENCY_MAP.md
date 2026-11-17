# NRLMSIS 2.1 Component Dependency Map (`orekit-nrlmsis21`)

This technical attachment documents the exact source-level, compile-time, link-time, and runtime dependencies between upstream **NRLMSIS 2.1** and each independently authored layer of `orekit-nrlmsis21`.

---

## 1. End-to-End Call Chain

```text
Python (python/orekit_nrlmsis21/)
   │  [JPype / orekit-jpype: in-process JVM bridge; zero NRL code]
   ▼
Java Orekit Adapters (java/src/main/java/org/ssa/nrlmsis21/)
   │  [JNI native method declarations in Nrlmsis21Native.java; zero NRL code]
   ▼
C JNI Bridge (native/nrlmsis21_jni.c)
   │  [#include "nrlmsis21_c_api.h" + OS mutexes; no direct NRL Fortran calls]
   ▼
Fortran 2003 ISO_C_BINDING API (native/nrlmsis21_c_api.F90 & .h)
   │  [Direct Fortran `use msis_constants`, `use msis_init`, `use msis_calc`]
   ▼
User-Supplied Upstream NRLMSIS 2.1 (external/NRLMSIS2.1 or -DNRLMSIS21_SOURCE_DIR)
   │  [8 unmodified .F90 files + 536,576-byte msis21.parm]
```

---

## 2. Layer-by-Layer Technical Coupling Inspection

### Layer 1: Python Package & Source Acquisition Helper (`python/orekit_nrlmsis21/`)
- **Files**: `__init__.py`, `atmosphere.py`, `loader.py`, `acquire.py`, `nrlmsis2.1_license.txt`.
- **Imports / Dependencies**: Python standard library, `jpype1`, `orekit-jpype`.
- **Interaction with Upstream**:
  - `loader.py` locates `orekit-nrlmsis21-1.0.2.jar` (`java_classpaths()`), the user-compiled native library (`NRLMSIS21_LIB_PATH`, `find_native_library()`), and `msis21.parm` (`NRLMSIS21_PARM_PATH`, `find_parameter_file()`, verifying exact byte size `EXPECTED_PARM_BYTES = 536576`), then invokes `Nrlmsis21Native.load(...)` and `Nrlmsis21Native.init(parm_dir, parm_file)` inside the JVM.
  - `acquire.py` validates user-supplied directories (`validate_nrlmsis21_directory`), extracts user archives (`extract_nrlmsis21_archive`), or downloads `https://map.nrl.navy.mil/map/pub/nrl/NRLMSIS/NRLMSIS2.1/nrlmsis2.1.tar.gz` only after explicit interactive `"YES"` confirmation (`download_nrlmsis21_source`).
  - `nrlmsis2.1_license.txt` is included verbatim for license notice compliance.
- **Upstream Code Present**: None.

### Layer 2: Java Orekit Adapters (`java/src/main/java/org/ssa/nrlmsis21/`)
- **Files**: `Nrlmsis21Native.java`, `Nrlmsis21Atmosphere.java`, `CssiWeatherProvider.java`, `ConstantSpaceWeather.java`, `SpaceWeatherProvider.java`.
- **Imports / Dependencies**: Java standard library, Orekit (`org.orekit.*`), Hipparchus (`org.hipparchus.*`).
- **Interaction with Upstream**:
  - `Nrlmsis21Native.java` loads the native library via `System.load` / `System.loadLibrary` and declares 6 `native` methods: `init(String, String)`, `init(String, String, boolean)`, `setStormApMode(boolean)`, `isStormApMode()`, `isInitialized()`, and `calc(...)`.
  - `Nrlmsis21Atmosphere.java` implements Orekit's `Atmosphere` interface (`getDensity`, `getVelocity`, `Field` overloads using `FD_STEP_M = 1.0` m central finite differences for spatial density gradients). It clamps altitudes `< 0.0 km` to `0.0 km` and returns `0.0 kg/m^3` above `maxAltitudeKm` (default `1000.0 km`).
  - `CssiWeatherProvider.java` adapts Orekit `CssiSpaceWeatherData` (`f107`, 81-day `f107Avg`, 7-element `ap`).
- **Upstream Code Present**: None. Compiled to JVM bytecode (`target/orekit-nrlmsis21-1.0.2.jar`) independently of Fortran compilers and NRLMSIS 2.1 source.

### Layer 3: C JNI Bridge (`native/nrlmsis21_jni.c`)
- **Files**: `native/nrlmsis21_jni.c`.
- **Includes**: `<jni.h>`, `<stdlib.h>`, `<string.h>`, `"nrlmsis21_c_api.h"`, plus `<windows.h>` (`INIT_ONCE` + `CRITICAL_SECTION`) on Windows or `<pthread.h>` (`pthread_mutex_t`) on Linux.
- **Interaction with Upstream**:
  - Source file does **not** `#include` or call any NRL Fortran symbol directly; it calls only the 6 C functions declared in `native/nrlmsis21_c_api.h` (`msis21_init_c`, `msis21_init_ex_c`, `msis21_set_storm_ap_mode_c`, `msis21_get_storm_ap_mode_c`, `msis21_is_initialized_c`, `msis21_calc_c`).
  - **Build/Link Boundary**: In `CMakeLists.txt`, `nrlmsis21_jni.c` is compiled as part of the `nrlmsis21_jni` CMake `SHARED` target alongside `nrlmsis21_c_api.F90` and the 8 user-supplied upstream `.F90` files, producing one combined native library (`libnrlmsis21_jni.dll` / `libnrlmsis21_jni.so`).

### Layer 4: Fortran 2003 `ISO_C_BINDING` C API (`native/nrlmsis21_c_api.F90`, `native/nrlmsis21_c_api.h`)
- **Direct Upstream Module `USE` Statements in `native/nrlmsis21_c_api.F90` (lines 6–8)**:
  - `use msis_constants, only: rp`
  - `use msis_init, only: msisinit, tselec`
  - `use msis_calc, only: msiscalc`
- **Direct Upstream Calls**:
  - `call msisinit(parmpath=f_parmpath, parmfile=f_parmfile, switch_legacy=sw_arr, lzalt_type=.true.)`
  - `call tselec(sw_arr)`
  - `call msiscalc(...)` (both for normal evaluation and `day = -999.0_rp` cache flush on Ap-mode switching)
- **Wrapper-Added Safeguards**:
  - Bounded C-string copy (`MAX_MSIS_PATH_LEN = 128`).
  - Pre-validation of `msis21.parm` (`PARM_FILE_BYTES = 536576`, `PARM_VALUE_COUNT = 67072`, `all(ieee_is_finite(parm_vals))`) before calling `msisinit`, preventing upstream `STOP` or EOF aborts.
  - Per-call zero-initialization (`f_dn = 0.0_rp`, `f_tn = 0.0_rp`, `f_tex = 0.0_rp`), `ieee_is_finite`, and non-negativity checks.
- **Compile/Link Boundary**: Cannot compile without upstream `.mod` files generated from `msis_constants.F90`, `msis_init.F90`, and `msis_calc.F90` under `-cpp -DDBLE`.
- **`native/nrlmsis21_c_api.h`**: Pure C header declaring `extern "C"` prototypes and error macros (`MSIS21_SUCCESS = 0` through `MSIS21_ERR_NOT_INITIALIZED = -4`). Contains no NRL code, but mirrors `nrlmsis21_c_api.F90`'s ABI.

### Layer 5: Build & Packaging Tooling (`CMakeLists.txt`, `build_dev.py`, `setup.py`, `MANIFEST.in`)
- `CMakeLists.txt` requires `-DNRLMSIS21_SOURCE_DIR=<path>` (defaulting in dev checkouts to `external/NRLMSIS2.1`), verifies the presence and module declarations of all 8 upstream `.F90` files (`msis_constants.F90`, `msis_init.F90`, `msis_utils.F90`, `msis_dfn.F90`, `msis_tfn.F90`, `msis_gfn.F90`, `msis_gtd8d.F90`, `msis_calc.F90`), and compiles them with `-cpp -DDBLE -O3 -fPIC`.
- `setup.py` with `OREKIT_NRLMSIS21_WRAPPER_ONLY=1` and `MANIFEST.in` exclude `external/`, `*.dll`, `*.so*`, and `*.parm` from public wrapper wheels (`py3-none-any`) and source distributions (`sdist`).
