# Reproducible Build & Validation Guide (`orekit-nrlmsis21`)

This guide provides the exact commands to reproduce the wrapper installation, user-supplied NRLMSIS 2.1 source acquisition, local native compilation, Java JAR packaging, and scientific validation benchmarks on Windows x86_64 and Linux x86_64.

> **Important Note on `pip install`**: Installing the wrapper-only package (`orekit_nrlmsis21-1.0.2-py3-none-any.whl`) installs **only** the Python wrapper, acquisition helper, and Java adapter JAR (`orekit-nrlmsis21-1.0.2.jar`). It does **not** install the upstream NRLMSIS 2.1 model, `msis21.parm`, or compiled binaries.

---

## Step 1: Install Prerequisites & Wrapper Package

### Prerequisites
- **Windows x86_64**: MSYS2 UCRT64 64-bit `gcc` and `gfortran` (`C:\msys64\ucrt64\bin` on `PATH`), CMake `>= 3.20`, Ninja, Eclipse Adoptium JDK 17+ (`JAVA_HOME`), Python `3.10`–`3.14`.
- **Linux x86_64**: `build-essential`, `gfortran`, `cmake` `>= 3.20`, `ninja-build`, `openjdk-17-jdk` (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`), Python `3.10`–`3.14`.
- **Python Dependencies**: `orekit-jpype>=12.0`, `jpype1>=1.4`, `numpy>=1.20`.

### Install Wrapper Only
```bash
python -m pip install orekit_nrlmsis21-1.0.2-py3-none-any.whl
# Or editable source checkout without copying native binaries:
python -m pip install --no-deps -e .
```

---

## Step 2: Obtain NRLMSIS 2.1 Independently from NRL

Users are responsible for reviewing and complying with NRL's `NRL-SOF-014-1` Open Source Academic Research License Agreement (non-commercial research, academic, and non-profit use unless written NRL IP Counsel consent is held).

### Option A: Manual Download & Extraction (Recommended)
1. Download `nrlmsis2.1.tar.gz` directly from the official U.S. Naval Research Laboratory directory:
   - `https://map.nrl.navy.mil/map/pub/nrl/NRLMSIS/NRLMSIS2.1/nrlmsis2.1.tar.gz`
2. Extract and validate the 8 Fortran files (`msis_constants.F90`–`msis_calc.F90`), `msis21.parm` (`536,576` bytes), and `nrlmsis2.1_license.txt` without overwriting existing files:
```bash
python -m orekit_nrlmsis21.acquire --from-archive /path/to/nrlmsis2.1.tar.gz --target-dir ./nrlmsis21_upstream
```

### Option B: Interactive User-Confirmed Download
```bash
python -m orekit_nrlmsis21.acquire --download --target-dir ./nrlmsis21_upstream
# Prompts interactively for explicit "YES" confirmation of NRL-SOF-014-1 terms.
```

### Validate an Existing Directory
```bash
python -m orekit_nrlmsis21.acquire --verify --target-dir ./nrlmsis21_upstream
```

---

## Step 3: Compile the Native Bridge Locally (`NRLMSIS21_SOURCE_DIR`)

Build into a separate local build directory (never copying upstream Fortran files into the wrapper package).

### Linux (Bash)
```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
cmake -S . -B build/local_linux -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DNRLMSIS21_SOURCE_DIR="$(pwd)/nrlmsis21_upstream"
cmake --build build/local_linux --target nrlmsis21_jni --config Release
```

### Windows (PowerShell with MSYS2 UCRT64 on `PATH`)
```powershell
$env:Path = "C:\msys64\ucrt64\bin;" + $env:Path
cmake -S . -B build/local_win64 -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_C_COMPILER=C:/msys64/ucrt64/bin/gcc.exe `
  -DCMAKE_Fortran_COMPILER=C:/msys64/ucrt64/bin/gfortran.exe `
  -DNRLMSIS21_SOURCE_DIR="$PWD/nrlmsis21_upstream"
cmake --build build/local_win64 --target nrlmsis21_jni --config Release
```

*(Alternatively, run `python build_dev.py --nrlmsis-source-dir ./nrlmsis21_upstream --build-dir ./build/local_jni --no-stage-package-lib --no-pip` to validate upstream sources, compile C/Fortran, and build `target/orekit-nrlmsis21-1.0.2.jar` in one step.)*

---

## Step 4: Configure Runtime Environment Variables

Point the Python loader at your local compiled shared library, `msis21.parm`, and Orekit geophysical data (`python scripts/setup_data.py`):

```bash
# Linux
export NRLMSIS21_LIB_PATH="$(pwd)/build/local_linux/libnrlmsis21_jni.so"
export NRLMSIS21_PARM_PATH="$(pwd)/nrlmsis21_upstream/msis21.parm"
export OREKIT_DATA_PATH="$(pwd)/orekit-data"
```
```powershell
# Windows PowerShell
$env:NRLMSIS21_LIB_PATH  = "$PWD\build\local_win64\libnrlmsis21_jni.dll"
$env:NRLMSIS21_PARM_PATH = "$PWD\nrlmsis21_upstream\msis21.parm"
$env:OREKIT_DATA_PATH    = "$PWD\orekit-data"
```

---

## Step 5: Execute Reproducibility & Validation Suites

```bash
# 1. Source acquisition, loader overrides, CMake external dir, and wrapper-only exclusion checks:
python tests/test_user_supplied_source_and_loader.py

# 2. Direct C-API numerical verification (200 reference vectors):
python tests/test_c_api.py . build/local_win64   # or build/local_linux on Linux

# 3. Java/JNI lifecycle, storm/daily Ap modes, 200-vector ref & 10-thread stress:
python tests/test_jni_bridge.py build/local_win64 # requires orekit-jpype in Python env

# 4. Full 200-vector NRL benchmark (all 10 species/rho, T, 388 sentinels):
python tests/test_nrl_reference.py

# 5. CSSI adapter, storm vs daily Ap & pymsis 2.1 parity:
python tests/test_cssi_adapter_verification.py

# 6. Orekit Atmosphere, Field Coriolis & spatial density gradients:
python tests/test_orekit_atmosphere.py

# 7. Fault-injection guards & 100,000-call HotSpot C2 repeatability:
python tests/test_fault_injection_regression.py

# 8. 12-hour LEO Gauss-Newton Batch Least Squares Cd estimation:
python tests/test_batch_least_squares.py
```

See [VALIDATION.md](VALIDATION.md) for the verified Windows and Linux numerical outputs from each test.
