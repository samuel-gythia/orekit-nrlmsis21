\
# Contributing to `orekit-nrlmsis21`

Thank you for your interest in contributing to `orekit-nrlmsis21`!

This project integrates the **NRLMSIS 2.1** empirical neutral thermosphere model into **Orekit** and **Orekit-JPype** via an in-process **Python $\rightarrow$ Java $\rightarrow$ C JNI $\rightarrow$ Fortran 2003 `ISO_C_BINDING`** pipeline, avoiding CPython callback overhead during numerical orbit propagation and Batch Least Squares estimation.

> **Important Pre-Release Notice:** Using **Apache-2.0** for independently authored wrapper components is currently a **candidate approach, NOT an approved legal decision**, and derivative-work questions under `NRL-SOF-014-1` Section 4(b) for `native/nrlmsis21_c_api.F90`, `native/nrlmsis21_c_api.h`, and `native/nrlmsis21_jni.c` remain unresolved (see [`PUBLICATION_MANIFEST.md`](PUBLICATION_MANIFEST.md) and [`RELEASE_BLOCKERS.md`](RELEASE_BLOCKERS.md)).

---

## 1. Development Prerequisites

1. **Compilers & Build Tools**:
   - GNU `gfortran` and `gcc` (`>= 10`): MSYS2 UCRT64 MinGW-w64 on Windows; system `build-essential` + `gfortran` on Linux.
   - `cmake >= 3.20` and `ninja` (or `make`).
2. **Java Development Kit**:
   - OpenJDK 17 LTS+ (e.g., Eclipse Adoptium Temurin) with `JAVA_HOME`, `javac`, and `jar` available.
3. **Python Environment**:
   - Python `3.10`–`3.14` with `orekit-jpype >= 12.0`, `jpype1 >= 1.4`, `numpy >= 1.20`, `setuptools >= 77.0`, `wheel`, and `pytest`.
4. **User-Supplied Upstream Model & Geophysical Data** *(never commit to Git)*:
   - Unmodified NRLMSIS 2.1 Fortran 2003 files and `msis21.parm` (`536,576` bytes) obtained independently from NRL.
   - Standard `orekit-data` directory (`python scripts/setup_data.py`).

---

## 2. Building From a Clean Source Checkout

### Step 1: Obtain & Validate Upstream NRLMSIS 2.1 Source Locally
```bash
python -m pip install --no-deps -e .
python -m orekit_nrlmsis21.acquire --from-archive /path/to/nrlmsis2.1.tar.gz --target-dir ./nrlmsis21_upstream
```

### Step 2: Compile the Native JNI Library & Java Adapter JAR
```powershell
# Windows PowerShell (with MSYS2 UCRT64 on PATH)
$env:Path = "C:\msys64\ucrt64\bin;" + $env:Path
cmake -S . -B build/win64_jni -G Ninja `
  -DCMAKE_BUILD_TYPE=Release `
  -DCMAKE_C_COMPILER=C:/msys64/ucrt64/bin/gcc.exe `
  -DCMAKE_Fortran_COMPILER=C:/msys64/ucrt64/bin/gfortran.exe `
  -DNRLMSIS21_SOURCE_DIR="$PWD/nrlmsis21_upstream"
cmake --build build/win64_jni --target nrlmsis21_jni --config Release
powershell -ExecutionPolicy Bypass -File .\scripts\build_java.ps1
```
```bash
# Linux Bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
python build_dev.py --nrlmsis-source-dir ./nrlmsis21_upstream --build-dir ./build/linux --no-stage-package-lib --no-pip
```

### Step 3: Build Wrapper-Only Wheel & Source Distribution
After building `target/orekit-nrlmsis21-1.0.2.jar` and copying it to `python/orekit_nrlmsis21/lib/orekit-nrlmsis21-1.0.2.jar`:
```bash
OREKIT_NRLMSIS21_WRAPPER_ONLY=1 python setup.py bdist_wheel sdist
```
Never stage `.dll`, `.so*`, `.parm`, or `external/` into a wheel, `sdist`, or Git commit.

---

## 3. Running Verification Suites

```bash
export NRLMSIS21_LIB_PATH="$(pwd)/build/linux/libnrlmsis21_jni.so"   # or .dll on Windows
export NRLMSIS21_PARM_PATH="$(pwd)/nrlmsis21_upstream/msis21.parm"
export OREKIT_DATA_PATH="$(pwd)/orekit-data"

python tests/test_user_supplied_source_and_loader.py
python tests/test_c_api.py . build/linux
python tests/test_jni_bridge.py build/linux
python tests/test_nrl_reference.py
python tests/test_cssi_adapter_verification.py
python tests/test_orekit_atmosphere.py
python tests/test_fault_injection_regression.py
python tests/test_batch_least_squares.py
```

---

## 4. Licensing & Contribution Guidelines

- **Never commit** upstream NRLMSIS 2.1 Fortran sources (`.F90`), `msis21.parm`, compiled binaries (`.dll`, `.so`, `.jar`), `orekit-data/`, personal paths, or credentials.
- Upstream NRLMSIS 2.1 is property of the U.S. Government (`NRL-SOF-014-1`) and restricted to **academic, research, and non-profit use only** unless written NRL IP Counsel consent is obtained.
- All independently authored wrapper contributions are targeted for release under a permissive license (**Apache-2.0 candidate**, subject to final confirmation once NRL Code 7630 derivative-work clarifications are received).
