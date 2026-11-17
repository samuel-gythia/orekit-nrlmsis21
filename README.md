# orekit-nrlmsis21

[![License: Mixed (Apache-2.0 Wrapper / NRL-SOF-014-1 Academic Research)](https://img.shields.io/badge/License-Apache--2.0%20Wrapper%20%7C%20NRL--SOF--014--1%20Non--Commercial-blue.svg)](LICENSES/README.md)
[![Java 17](https://img.shields.io/badge/Java-17%20LTS-orange.svg)](https://adoptium.net/)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Platform: Windows | Linux](https://img.shields.io/badge/Platform-Windows%20x86__64%20%7C%20Linux%20x86__64-brightgreen.svg)](https://github.com/samuel-gythia/orekit-nrlmsis21)
[![Orekit 12+](https://img.shields.io/badge/Orekit-12.0%20%7C%2013.1-red.svg)](https://www.orekit.org/)

**Native NRLMSIS 2.1 Empirical Thermosphere Integration for Orekit and Orekit-JPype (Astrodynamics, Orbit Determination & Space Situational Awareness).**

> **Mandatory NRLMSIS 2.1 Attribution & Non-Commercial Restriction (`NRL-SOF-014-1`):**  
> "This software incorporates the MSIS® empirical atmospheric model software designed and provided by NRL. Use is governed by the Open Source Academic Research License Agreement contained in the file nrlmsis2.1_license.txt."  
> - **Academic / Non-Profit Research Only**: Upstream NRLMSIS 2.1 (`NRL-SOF-014-1`) is authorized **solely for research, academic, and non-profit purposes**. Any commercial use—or selling, licensing, or transferring for a fee the Software, derivative works, or generated data products—is prohibited without prior written consent from IP Counsel for the U.S. Naval Research Laboratory.
> - **No Upstream NRL Code or Binaries Bundled**: This repository contains **no** upstream NRLMSIS 2.1 Fortran source, **no** `msis21.parm`, and **no** precompiled NRL binaries (`.dll`/`.so`). End users obtain NRLMSIS 2.1 independently from the official NRL distribution page (`https://map.nrl.navy.mil/map/pub/nrl/NRLMSIS/NRLMSIS2.1/`) and compile the shared library locally.
> - **File-Level Licensing**: Independently authored Python, Java, build, test, and documentation files are licensed under **Apache-2.0** ([`LICENSES/APACHE-2.0.txt`](LICENSES/APACHE-2.0.txt)); native integration files (`native/nrlmsis21_c_api.F90`, `.h`, `native/nrlmsis21_jni.c`) are conservatively governed by **`NRL-SOF-014-1`** ([`LICENSES/NRL-SOF-014-1.txt`](LICENSES/NRL-SOF-014-1.txt)). See [`LICENSES/README.md`](LICENSES/README.md).

---

## 1. Purpose & Scientific Motivation

Accurate thermospheric drag modeling in Low Earth Orbit (LEO, 200–1,000 km) is essential for orbit propagation, conjunction assessment, and Batch Least Squares (BLS) orbit determination. **NRLMSIS 2.1** improves thermospheric mass density, minor species, and nitric oxide (`NO`) cooling over NRLMSISE-00 and NRLMSIS 2.0, while **Orekit** provides industry-standard numerical propagators and `BatchLSEstimator` variational equations—but does not ship a native NRLMSIS 2.1 model.

Wrapping Python atmospheric models (such as `pymsis`) through JPype Python proxies inside an Orekit `DragForce` requires crossing the JVM $\leftrightarrow$ CPython boundary on every ODE substep ($10^5$–$10^7$ calls per multi-day arc). `orekit-nrlmsis21` eliminates that callback overhead by implementing Orekit's `Atmosphere` and `CssiSpaceWeatherData` interfaces directly in Java backed by an in-process JNI $\rightarrow$ Fortran `ISO_C_BINDING` bridge.

---

## 2. Architecture

```text
Python (python/orekit_nrlmsis21/)
   │  JPype / orekit-jpype (JVM setup & high-level wrapper)
   ▼
Java Orekit Adapters (java/src/main/java/org/ssa/nrlmsis21/)
   │  Nrlmsis21Atmosphere (implements Atmosphere), CssiWeatherProvider, Nrlmsis21Native
   ▼
C JNI Bridge (native/nrlmsis21_jni.c)
   │  OS mutex serialization (INIT_ONCE CRITICAL_SECTION / pthread_mutex_t)
   ▼
Fortran 2003 ISO_C_BINDING C API (native/nrlmsis21_c_api.F90 & .h)
   │  Parameter validation (536,576 B), SAVE-cache flushing, IEEE-754 finite guards
   ▼
User-Supplied Upstream NRLMSIS 2.1 (-DNRLMSIS21_SOURCE_DIR)
   │  8 unmodified .F90 files + msis21.parm (obtained independently from NRL)
```

---

## 3. Orekit & CSSI Space-Weather Integration

- **`Nrlmsis21Atmosphere.java`**: Implements `org.orekit.models.earth.atmosphere.Atmosphere` (`getDensity`, `getVelocity`, and `Field` overloads). Spatial density gradients $\partial\rho/\partial\mathbf{r}$ use 1 m central finite differences; `getVelocity(...)` delegates to `Atmosphere.super.getVelocity(...)` to preserve exact Earth-rotation Coriolis partials.
- **`CssiWeatherProvider.java`**: Adapts Orekit `CssiSpaceWeatherData` directly inside Java, supplying daily $F_{10.7}$, 81-day centered $F_{10.7A}$, and the 7-element geomagnetic $A_p$ history array (`ap[0..6]`) with zero Python callbacks.
- **`Nrlmsis21Native.java`**: Exposes all 6 JNI methods (`init(path, file)`, `init(path, file, stormApMode)`, `setStormApMode`, `isStormApMode`, `isInitialized`, `calc`), defaulting to storm-time 7-element $A_p$ (`switch_legacy(9) = -1.0`) with optional daily-$A_p$ mode (`switch_legacy(9) = +1.0`).

---

## 4. User-Supplied Upstream Source Workflow (One-Step Setup)

After installing the wrapper wheel (`pip install orekit_nrlmsis21-1.0.2-py3-none-any.whl`), users can acquire/verify NRLMSIS 2.1 and compile `libnrlmsis21_jni` locally into `~/.orekit_nrlmsis21/` in one step (requiring `gcc`, `gfortran`, `cmake`, and `JDK 17`):

```bash
# Option A: Interactive NRL download (prompts for explicit "YES" license acceptance) + local CMake build
orekit-nrlmsis21-setup --download

# Option B: From a manually downloaded nrlmsis2.1.tar.gz archive
orekit-nrlmsis21-setup --from-archive /path/to/nrlmsis2.1.tar.gz

# Option C: From an already cloned mirror or local NRLMSIS 2.1 directory
orekit-nrlmsis21-setup --source-dir /path/to/nrlmsis21_mirror
```

On Windows PowerShell with MSYS2 UCRT64, pass `--c-compiler` and `--fortran-compiler`:
```powershell
$env:Path = "C:\msys64\ucrt64\bin;" + $env:Path
orekit-nrlmsis21-setup --source-dir .\nrlmsis21_mirror `
  --c-compiler C:/msys64/ucrt64/bin/gcc.exe `
  --fortran-compiler C:/msys64/ucrt64/bin/gfortran.exe
```

Once complete, `orekit_nrlmsis21.loader` automatically discovers `~/.orekit_nrlmsis21/libnrlmsis21_jni.*` and `~/.orekit_nrlmsis21/msis21.parm` without extra environment variables.

### Manual Acquisition & Verification Only
1. **Official NRL distribution page**: `https://map.nrl.navy.mil/map/pub/nrl/NRLMSIS/NRLMSIS2.1/`
2. **Extract or validate locally** (without building):
   ```bash
   python -m pip install --no-deps -e .
   # From a downloaded archive:
   python -m orekit_nrlmsis21.acquire --from-archive /path/to/nrlmsis2.1.tar.gz --target-dir ./nrlmsis21_upstream
   # Or interactive user-confirmed download from NRL (prompts for explicit "YES"):
   python -m orekit_nrlmsis21.acquire --download --target-dir ./nrlmsis21_upstream
   # Or validate an existing local folder / cloned mirror containing the 8 .F90 files + msis21.parm:
   python -m orekit_nrlmsis21.acquire --verify --target-dir /path/to/nrlmsis21_mirror
   ```
   *(If using an existing cloned mirror directory, simply point `-DNRLMSIS21_SOURCE_DIR=/path/to/nrlmsis21_mirror` and `NRLMSIS21_PARM_PATH=/path/to/nrlmsis21_mirror/msis21.parm` at the subfolder containing the 8 `.F90` files and `msis21.parm`.)*

---

## 5. Build Instructions (Windows & Linux)

### Prerequisites
- GNU `gcc` and `gfortran` (`>= 10`, tested with `15.2.0`)
- `cmake >= 3.20` and `ninja` (or `make`)
- OpenJDK / Eclipse Adoptium **JDK 17 LTS+** (`JAVA_HOME` configured)
- Python `3.10`–`3.14` with `orekit-jpype >= 12.0`, `jpype1 >= 1.4`, `numpy >= 1.20`

### Windows (x86_64 PowerShell + MSYS2 UCRT64)
```powershell
$env:Path = "C:\msys64\ucrt64\bin;" + $env:Path
cmake -S . -B build/win64_jni -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_C_COMPILER=C:/msys64/ucrt64/bin/gcc.exe `
  -DCMAKE_Fortran_COMPILER=C:/msys64/ucrt64/bin/gfortran.exe `
  -DNRLMSIS21_SOURCE_DIR="$PWD/nrlmsis21_upstream"
cmake --build build/win64_jni --target nrlmsis21_jni --config Release

# Compile Java adapter JAR (target/orekit-nrlmsis21-1.0.2.jar)
powershell -ExecutionPolicy Bypass -File .\scripts\build_java.ps1
```

### Linux (x86_64 Bash)
```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
cmake -S . -B build/linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DNRLMSIS21_SOURCE_DIR="$(pwd)/nrlmsis21_upstream"
cmake --build build/linux --target nrlmsis21_jni --config Release

# Compile Java adapter JAR & verify local build
python build_dev.py --nrlmsis-source-dir ./nrlmsis21_upstream --build-dir ./build/linux --no-stage-package-lib
```

---

## 6. Python Package Installation & Runtime Configuration

To build and install the wrapper-only wheel (`py3-none-any`, after compiling `orekit-nrlmsis21-1.0.2.jar`):
```bash
OREKIT_NRLMSIS21_WRAPPER_ONLY=1 python setup.py bdist_wheel sdist
python -m pip install dist/orekit_nrlmsis21-1.0.2-py3-none-any.whl
```

Point the runtime loader to your locally built shared library, `msis21.parm`, and Orekit geophysical data (`python scripts/setup_data.py`):
```powershell
# Windows PowerShell
$env:NRLMSIS21_LIB_PATH  = "$PWD\build\win64_jni\libnrlmsis21_jni.dll"
$env:NRLMSIS21_PARM_PATH = "$PWD\nrlmsis21_upstream\msis21.parm"
$env:OREKIT_DATA_PATH    = "$PWD\orekit-data"
```
```bash
# Linux Bash
export NRLMSIS21_LIB_PATH="$(pwd)/build/linux/libnrlmsis21_jni.so"
export NRLMSIS21_PARM_PATH="$(pwd)/nrlmsis21_upstream/msis21.parm"
export OREKIT_DATA_PATH="$(pwd)/orekit-data"
```

---

## 7. Example: Calculating Atmospheric Density Through Orekit

```python
import orekit_nrlmsis21 as nrl
from org.orekit.models.earth.atmosphere.data import CssiSpaceWeatherData
from org.orekit.time import AbsoluteDate, TimeScalesFactory
from org.orekit.frames import FramesFactory
from org.orekit.bodies import OneAxisEllipsoid
from org.orekit.utils import Constants, IERSConventions
from org.hipparchus.geometry.euclidean.threed import Vector3D
from orekit_jpype.pyhelpers import setup_orekit_data

orekit = nrl.init_vm()
setup_orekit_data("path/to/orekit-data", from_pip_library=False)

utc = TimeScalesFactory.getUTC()
itrf = FramesFactory.getITRF(IERSConventions.IERS_2010, True)
gcrf = FramesFactory.getGCRF()
earth = OneAxisEllipsoid(Constants.WGS84_EARTH_EQUATORIAL_RADIUS,
                         Constants.WGS84_EARTH_FLATTENING, itrf)

cssi = CssiSpaceWeatherData(CssiSpaceWeatherData.DEFAULT_SUPPORTED_NAMES)
provider = nrl.create_cssi_weather_provider(cssi)
atm = nrl.create_atmosphere(earth, provider, utc)

epoch = AbsoluteDate(2024, 1, 15, 12, 0, 0.0, utc)
pos = itrf.getTransformTo(gcrf, epoch).transformPosition(
    Vector3D(Constants.WGS84_EARTH_EQUATORIAL_RADIUS + 400_000.0, 0.0, 0.0)
)
rho = atm.getDensity(epoch, pos, gcrf)
print(f"Density: {rho:.6e} kg/m^3")
```

---

## 8. Validation Summary

Full platform tables and reproduction instructions are in [`docs/VALIDATION.md`](docs/VALIDATION.md) and [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md):
- **200-Vector NRL Reference Benchmark (`tests/test_nrl_reference.py`, `tests/test_c_api.py`)**: Verified `1,812 / 1,812` active outputs and `388 / 388` below-cutoff sentinels (`9.999e-38`) on Windows and Linux (`max rho rel err = 4.3866e-04`, `max T abs err = 4.9629e-03 K`).
- **CSSI Space Weather & `pymsis 2.1` Parity (`tests/test_cssi_adapter_verification.py`, Windows)**: Synthetic storm-`ap[1..6]` spike at 400 km produces `+266.91%` density response in storm mode (`switch_legacy(9) = -1`) and exact invariance in daily mode (`switch_legacy(9) = +1`); `pymsis 2.1` relative difference spans `1.80e-07` to `8.16e-06` across 6 historical solar/geomagnetic epochs.
- **Orekit Atmosphere & `Field` Partials (`tests/test_orekit_atmosphere.py`, Windows)**: `8/8` passing, verifying `150–800 km` density profile, Coriolis `Field` velocity gradient Frobenius norm (`1.031261e-04`), and `DragForce` sensitivity.
- **Batch Least Squares Orbit Determination (`tests/test_batch_least_squares.py`, Windows)**: 12-hour LEO arc (720 Cartesian obs, $\sigma = 1.0\text{ m}$) converged in 4 Gauss-Newton iterations (`Normalized Cost RMS = 0.9950`, recovered `Cd = 2.2000`, `0.0015%` error).
- **JNI Lifecycle, Concurrency & Fault Injection (`tests/test_jni_bridge.py`, `tests/test_fault_injection_regression.py`)**: Passed 10-thread concurrency checks on Windows and Linux OpenJDK 17, plus `100,000`-call HotSpot C2 repeatability and invalid-input guards on Windows.

---

## 9. Known Limitations

1. **Academic / Non-Commercial Upstream Scope (`NRL-SOF-014-1`)**: Requires independent NRLMSIS 2.1 acquisition from NRL and prohibits commercial use or fee-based data products without NRL IP Counsel written consent.
2. **Global Mutex Serialization**: Upstream NRLMSIS 2.1 retains Fortran `SAVE` state; calls serialize via OS mutex (`CRITICAL_SECTION` / `pthread_mutex_t`).
3. **128-Character Parameter Path & Altitude Policy**: Upstream `msisinit` limits `parmpath` to `<= 128` characters; altitudes `< 0 km` clamp to `0 km`, altitudes `> maxAltitudeKm` (default `1000.0 km`) return `0.0 kg/m^3`, and `Field` density gradients use 1 m central differences.
4. **Tested Architectures**: Verified on **x86_64** Windows and Linux; ARM64 requires local compilation and testing.

---

## 10. Scientific Citation & Attribution

If you use `orekit-nrlmsis21` in academic research, please cite both the **NRLMSIS 2.1** empirical model and **Orekit**:
- **NRLMSIS 2.1**: Emmert, J. T., Jones Jr., M., Siskind, D. E., Drob, D. P., Picone, J. M., Stevens, M. H., et al. (2022). *NRLMSIS 2.1: An empirical model of nitric oxide incorporated into MSIS*. Journal of Geophysical Research: Space Physics, 127, e2022JA030896.
- **Orekit**: CS GROUP, *Orekit: An open-source flight dynamics library*, https://www.orekit.org/.

> "This software incorporates the MSIS® empirical atmospheric model software designed and provided by NRL. Use is governed by the Open Source Academic Research License Agreement contained in the file nrlmsis2.1_license.txt."  
> *MSIS® is a registered trademark of the Government of the United States of America, as represented by the Secretary of the Navy.*
