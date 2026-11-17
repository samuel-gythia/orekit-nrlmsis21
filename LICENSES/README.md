# File-Level Licensing Structure (`orekit-nrlmsis21`)

`orekit-nrlmsis21` uses a transparent, component-level licensing structure that separates independently authored integration code from components that directly interface with or incorporate **NRLMSIS 2.1** (`NRL-SOF-014-1`).

> "This software incorporates the MSIS® empirical atmospheric model software designed and provided by NRL. Use is governed by the Open Source Academic Research License Agreement contained in the file nrlmsis2.1_license.txt."

---

## A. Independently Authored Components (`Apache-2.0`)

The following components were authored independently for `orekit-nrlmsis21`, contain no copied upstream NRLMSIS 2.1 code, and are licensed under the **Apache License, Version 2.0** ([`APACHE-2.0.txt`](APACHE-2.0.txt)):

- `python/orekit_nrlmsis21/__init__.py`
- `python/orekit_nrlmsis21/acquire.py`
- `python/orekit_nrlmsis21/atmosphere.py`
- `python/orekit_nrlmsis21/loader.py`
- `java/src/main/java/org/ssa/nrlmsis21/SpaceWeatherProvider.java`
- `java/src/main/java/org/ssa/nrlmsis21/CssiWeatherProvider.java`
- `java/src/main/java/org/ssa/nrlmsis21/ConstantSpaceWeather.java`
- `java/src/main/java/org/ssa/nrlmsis21/Nrlmsis21Atmosphere.java`
- `java/src/main/java/org/ssa/nrlmsis21/Nrlmsis21Native.java`
- Build scripts, packaging configuration, tests, and documentation (`CMakeLists.txt`, `pom.xml`, `pyproject.toml`, `setup.py`, `MANIFEST.in`, `build_dev.py`, `.github/workflows/ci.yml`, `scripts/*`, `tests/*`, `docs/*`, `README.md`, `CONTRIBUTING.md`).

*(Note: When compiled or executed together with user-supplied NRLMSIS 2.1, end users remain bound by `NRL-SOF-014-1` for all model execution and outputs.)*

---

## B. NRLMSIS Integration Components (Treated Conservatively Under `NRL-SOF-014-1`)

The following native bridge files are treated conservatively as NRLMSIS derivative/integration components under **`NRL-SOF-014-1`** ([`NRL-SOF-014-1.txt`](NRL-SOF-014-1.txt) and [`../python/orekit_nrlmsis21/nrlmsis2.1_license.txt`](../python/orekit_nrlmsis21/nrlmsis2.1_license.txt)) unless independent status is established in writing by NRL:

- `native/nrlmsis21_c_api.F90` — Fortran 2003 `ISO_C_BINDING` API that directly `USE`s upstream `msis_constants`, `msis_init`, and `msis_calc`.
- `native/nrlmsis21_c_api.h` — C ABI header defining the `msis21_*_c` interface to `nrlmsis21_c_api.F90`.
- `native/nrlmsis21_jni.c` — C JNI bridge linked into the same native shared library (`libnrlmsis21_jni`) as `nrlmsis21_c_api.F90` and user-supplied NRLMSIS 2.1.

Each file carries a prominent Section 4(b) notice stating its purpose, integration changes, change date (`2026-11-17`), and the fact that upstream NRLMSIS 2.1 source itself remains unmodified.

---

## C. Third-Party Dependencies

See [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) for external runtime and build dependencies (Orekit, Hipparchus, `orekit-jpype`, `JPype1`, `NumPy`, and GNU GCC/GFortran runtime libraries).
