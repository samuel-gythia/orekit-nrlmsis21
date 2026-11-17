# Formal NRL Code 7630 & NRL IP Counsel Licensing Inquiry (`orekit-nrlmsis21`)

**Project:** `orekit-nrlmsis21` (v1.0.2 Release Candidate — Publication Preparation)  
**Upstream Software:** MSIS® / NRLMSIS 2.1 (`NRL-SOF-014-1`)  
**Status:** **DRAFT FOR REVIEW — DO NOT SEND OR PUBLISH**  
**Immediate Intended Use:** Academic research and scientific software development (Astrodynamics, Orbit Determination, and Space Situational Awareness).  
**Commercial Permission Status:** No commercial permission is held or claimed.

---

## 1. Component-Level Licensing Question Table

This table summarizes the technical role, upstream coupling, and unresolved legal questions for each layer of `orekit-nrlmsis21` across the pipeline:

`Python → JPype → Java → JNI C bridge → Fortran ISO_C_BINDING API → NRLMSIS 2.1`

No component is declared legally independent or legally derivative herein; all classifications below are presented for written clarification from NRL Code 7630 and NRL IP Counsel.

| Component & Files | What It Does | Copied Upstream Code? | Directly Calls / Depends on Upstream Model Modules? | Compiled into Same Native Binary (`libnrlmsis21_jni`)? | Why Derivative-Work Status Is Uncertain | Specific `NRL-SOF-014-1` Clauses That May Apply |
|---|---|---|---|---|---|---|
| **Python Package & Loader** (`python/orekit_nrlmsis21/__init__.py`, `atmosphere.py`, `loader.py`, `acquire.py`) | Starts/attaches to the JVM via `JPype`/`orekit-jpype`, registers `orekit-nrlmsis21-1.0.2.jar` on the classpath, locates user-supplied shared libraries (`NRLMSIS21_LIB_PATH`) and `msis21.parm` (`NRLMSIS21_PARM_PATH`, `536,576`-byte check), and provides `acquire.py` to validate/extract/download NRLMSIS 2.1 with explicit `"YES"` confirmation. | **No.** Independently authored Python code. (`nrlmsis2.1_license.txt` is included verbatim for notice compliance.) | **No direct Fortran/C calls.** Interacts only with Java classes via `JPype` and validates local file paths/sizes at runtime. Cannot execute atmospheric density evaluations without a user-supplied NRLMSIS 2.1 build. | **No.** Pure Python modules (`.py`). | As pure Python wrapper code without upstream source, it may be separable, **but** it is specifically designed to load and drive NRLMSIS 2.1 and bundle `nrlmsis2.1_license.txt`. Its status under Section 4(c) ("package that incorporates the MSIS® Software or derivative work") when distributed without NRL binaries is uncertain. | **Section 2** (research/academic/non-profit scope), **Section 3** (`MSIS®` trademark in package/class names), **Section 4(c)** (notices and `nrlmsis2.1_license.txt` inclusion). |
| **Java Orekit Adapter** (`java/src/main/java/org/ssa/nrlmsis21/Nrlmsis21Atmosphere.java`, `Nrlmsis21Native.java`, `CssiWeatherProvider.java`, `ConstantSpaceWeather.java`, `SpaceWeatherProvider.java`) | Implements Orekit's `Atmosphere` interface (`getDensity`, `getVelocity`, `Field` finite-difference spatial density gradients, Coriolis velocity partials), adapts `CssiSpaceWeatherData`, clamps `< 0 km` to `0.0 km`, returns `0.0` above `maxAltitudeKm` (`1000.0 km`), and declares `native` JNI methods in `Nrlmsis21Native.java`. | **No.** Independently authored Java code. | **Indirectly via JNI.** Contains zero NRL Fortran code, but `Nrlmsis21Native.java` declares the `native` signatures (`init`, `setStormApMode`, `isStormApMode`, `isInitialized`, `calc`) bound at runtime to `libnrlmsis21_jni`. | **No.** Compiled to JVM bytecode (`orekit-nrlmsis21-1.0.2.jar`), separate from native `.dll`/`.so` binaries. | Contains no upstream code and binds only by JNI method signature, **yet** `Nrlmsis21Native` and `Nrlmsis21Atmosphere` are purpose-built around NRLMSIS 2.1's `parmpath`/`parmfile`, `stormApMode` (`switch_legacy(9)`), and 10-species/temperature outputs, and bear the `Nrlmsis21` name. | **Section 2**, **Section 3** (`Nrlmsis21*` naming / `MSIS®`), **Section 4(b)** (whether bridging constitutes a derivative work or domain clamping triggers "substantially change the model output"), **Section 4(c)**. |
| **JNI C Bridge** (`native/nrlmsis21_jni.c`) | Implements the 6 JNI C entry points matching `Nrlmsis21Native.java`, marshals JVM `jstring` and `jdoubleArray` buffers, and serializes access with OS mutexes (`INIT_ONCE` `CRITICAL_SECTION` on Windows; `pthread_mutex_t` on Linux) over upstream Fortran `SAVE` state. | **No.** Independently authored C11 code. | **Indirectly via `nrlmsis21_c_api.h`.** Includes `<jni.h>`, OS threading headers, and `"nrlmsis21_c_api.h"`. Does not reference NRL Fortran symbols or modules in C source form. | **Yes (at local build time).** Compiled and linked by `CMakeLists.txt` with `nrlmsis21_c_api.F90` and the 8 upstream `.F90` files into `libnrlmsis21_jni.dll`/`.so`. | In source form it only calls the project-authored C header `nrlmsis21_c_api.h`, **but** at compile/link time it is statically linked with `nrlmsis21_c_api.F90` and upstream NRLMSIS 2.1 object code into one shared library. | **Section 2**, **Section 4(a)**, **Section 4(b)** (whether source is independent or becomes part of a combined derivative work when linked), **Section 4(c)**. |
| **Fortran `ISO_C_BINDING` C API** (`native/nrlmsis21_c_api.F90`, `native/nrlmsis21_c_api.h`) | `nrlmsis21_c_api.F90` exposes 6 `bind(C)` procedures (`msis21_init_c`, `msis21_init_ex_c`, `msis21_set_storm_ap_mode_c`, `msis21_get_storm_ap_mode_c`, `msis21_is_initialized_c`, `msis21_calc_c`), validates `msis21.parm` (`536,576` bytes, IEEE-754 finite), enforces `128`-char path bounds, zero-initializes outputs, and flushes `SAVE` cache (`day = -999.0`) on Ap-mode switches. `nrlmsis21_c_api.h` declares the C prototypes and status codes. | **No.** Independently authored Fortran 2003 and C header code; no upstream NRLMSIS `.F90` files are copied or edited. | **Yes (`nrlmsis21_c_api.F90` directly `USE`s upstream modules):** `use msis_constants, only: rp`, `use msis_init, only: msisinit, tselec`, and `use msis_calc, only: msiscalc`, and calls `msisinit`, `tselec`, and `msiscalc`. (`nrlmsis21_c_api.h` declares only C types/macros.) | **Yes (at local build time).** `nrlmsis21_c_api.F90` requires upstream `.mod` files at compile time and links into `libnrlmsis21_jni.dll`/`.so`. | Because `nrlmsis21_c_api.F90` directly `USE`s NRLMSIS 2.1 Fortran modules and calls `msisinit`/`tselec`/`msiscalc` without altering upstream files, it is uncertain whether interfacing via `ISO_C_BINDING` constitutes a "modification" or "derivative work" under Section 4(b). | **Section 2**, **Section 4(a)**, **Section 4(b)** (derivative-work classification, change notices, public open-source release, U.S. Government license grant, mandatory delivery to Code 7630), **Section 4(c)**. |
| **Build Tooling & Configuration** (`CMakeLists.txt`, `setup.py`, `pyproject.toml`, `MANIFEST.in`, `build_dev.py`, `pom.xml`, `scripts/*`, `.github/workflows/ci.yml`) | Automates CMake compilation against user-supplied `-DNRLMSIS21_SOURCE_DIR`, checks all 8 required upstream `.F90` filenames and `module`/`subroutine` markers, builds the Java JAR, and creates wrapper-only wheels/sdists (`OREKIT_NRLMSIS21_WRAPPER_ONLY=1`) excluding upstream files. | **No.** Independently authored build and packaging scripts. | **By file/module expectation only.** `CMakeLists.txt` and `acquire.py` check for the 8 upstream `.F90` filenames and module names in a user-supplied directory; no upstream code is embedded. | **No.** Build orchestration scripts only. | Build recipes invoke the compiler with `-cpp -DDBLE` and link the user-supplied NRLMSIS 2.1 sources locally, raising no direct code-copying issue, though packaging metadata (`pyproject.toml`, `setup.py`) must accurately represent license boundaries. | **Section 2**, **Section 3** (`MSIS®` naming in metadata), **Section 4(c)** (notices in source distributions and wrapper wheels). |

---

## 2. Draft Formal Inquiry Email to NRL Code 7630 & NRL IP Counsel

> **Note:** Upstream author emails below are transcribed from `external/NRLMSIS2.1/readme.txt` as previously recorded in [`NRL_CODE_7630_DELIVERY_AND_LEGAL_INQUIRY.md`](NRL_CODE_7630_DELIVERY_AND_LEGAL_INQUIRY.md). Verify current NRL IP Counsel and Code 7630 points of contact before transmitting.

```text
To: NRL Code 7630 (John Emmert <john.emmert@nrl.navy.mil>, Douglas Drob <douglas.drob@nrl.navy.mil>, McArthur Jones Jr. <mcarthur.jones@nrl.navy.mil>); NRL IP Counsel
Subject: Request for Licensing Clarification and Section 4(b) Guidance — orekit-nrlmsis21 (v1.0.2 RC)

Dear NRL Code 7630 Authors and NRL IP Counsel,

We are writing to request written licensing clarification and guidance under the MSIS® (NRL-SOF-014-1) Open Source Academic Research License Agreement regarding `orekit-nrlmsis21`, an academic/research software integration connecting NRLMSIS 2.1 to the open-source Orekit astrodynamics library.

Immediate Intended Use and Distribution Posture:
- Our immediate intended use is strictly academic research and scientific software development in astrodynamics, orbit determination, and Space Situational Awareness (SSA).
- No commercial permission is currently claimed or assumed, and we have not published precompiled NRLMSIS 2.1 binaries or distributed upstream NRLMSIS 2.1 source files or `msis21.parm`.
- All upstream NRLMSIS 2.1 Fortran 2003 source files and `msis21.parm` (536,576 bytes) used during local development and verification remain completely unmodified from NRL's Version 2.1 release.

Software Architecture:
`orekit-nrlmsis21` bridges Orekit (Java / Python via JPype) to NRLMSIS 2.1 using the following multi-layer architecture:

  Python (`orekit_nrlmsis21`) -> JPype -> Java (`Nrlmsis21Atmosphere`, `Nrlmsis21Native`)
    -> C JNI Bridge (`native/nrlmsis21_jni.c`)
    -> Fortran 2003 ISO_C_BINDING API (`native/nrlmsis21_c_api.F90`, `native/nrlmsis21_c_api.h`)
    -> User-Supplied Upstream NRLMSIS 2.1 (`msis_constants`, `msis_init`, `msis_calc`, etc.)

Proposed Separate-Wrapper Distribution Model:
To avoid redistributing NRL-owned source code, parameter tables (`msis21.parm`), or compiled NRLMSIS binaries, our planned public repository and wrapper distributions would contain ONLY our independently authored integration layers (Python wrapper/acquisition helper, Java Orekit adapters, C JNI bridge, Fortran ISO_C_BINDING C API, CMake/build scripts, tests, and documentation). End users would independently obtain NRLMSIS 2.1 directly from NRL under their applicable license (`NRL-SOF-014-1` or a separate commercial license from NRL), compile the upstream Fortran source locally with `-DNRLMSIS21_SOURCE_DIR`, and link it to the integration on their own system.

Before making any public release, we respectfully request written clarification on the following nine questions:

1. Fortran ISO_C_BINDING API (`native/nrlmsis21_c_api.F90`):
   Does our independently authored Fortran 2003 ISO_C_BINDING interface module—which leaves all upstream NRLMSIS 2.1 files unmodified, but directly `USE`s `msis_constants`, `msis_init`, and `msis_calc` and invokes `msisinit`, `tselec`, and `msiscalc` with input/parameter validation and cache-flush guards—constitute a "modification" or "derivative work of the Software" under Section 4(b) of `NRL-SOF-014-1`?

2. C JNI Bridge (`native/nrlmsis21_jni.c`):
   Does the C JNI bridge—which contains no NRL code and includes only `<jni.h>`, OS mutex headers, and our C header `native/nrlmsis21_c_api.h`, but is compiled and linked with `native/nrlmsis21_c_api.F90` and upstream NRLMSIS 2.1 into a single local shared library at user build time—qualify as a derivative work under Section 4(b), or is it considered an independent interface layer?

3. Independent Distribution of Java and Python Layers:
   Are the pure Java Orekit adapters (`java/src/main/java/org/ssa/nrlmsis21/*.java`) and Python/JPype wrapper (`python/orekit_nrlmsis21/*.py`) independently distributable under a permissive open-source license (such as Apache-2.0, which is currently under consideration pending your guidance) when the upstream NRLMSIS 2.1 model is separately obtained and compiled by the end user?

4. Section 4(b) Delivery to NRL Code 7630:
   If any component of `orekit-nrlmsis21` is classified as a derivative work under Section 4(b), which exact source files (and supporting data/documentation) must be delivered to NRL Code 7630, and what is the preferred delivery method and recipient address?

5. Open-Source Availability and License Constraints under Section 4(b):
   Does the complete derivative integration need to be made publicly available under an open-source license, and are there constraints on the open-source license selected for independently authored components (for example, compatibility between a permissive license such as Apache-2.0 and Section 4(b)'s U.S. Government license grant and Section 2's non-commercial scope)?

6. Section 4(c) Applicability to Source-Only Separate-Wrapper Distributions:
   Does a source-only repository or wrapper-only Python wheel (`py3-none-any`) that excludes all upstream NRLMSIS 2.1 Fortran files, `msis21.parm`, and compiled NRLMSIS binaries—and requires users to download NRLMSIS 2.1 separately from NRL—still count as a "software package that incorporates the MSIS® Software or derivative work" under Section 4(c)?

7. Mandatory Notices and Attribution:
   What exact notices, disclaimers, `nrlmsis2.1_license.txt` copies, and MSIS® trademark attributions (Section 3 and Section 4(c)) must appear in (a) the public source repository, (b) source distributions (`sdist`), (c) wrapper-only wheels, and (d) project documentation? Additionally, does `Nrlmsis21Atmosphere.java`'s domain handling (clamping `< 0 km` to `0 km` and returning `0.0 kg/m^3` above configurable `maxAltitudeKm`, default `1000.0 km`) require any special notice under Section 4(b)'s "substantially change the model output" clause?

8. Research-Oriented Software Later Used by Commercial Organizations:
   How should a research-oriented open-source integration project be structured and licensed if a commercial or industrial organization later wishes to use the integration alongside its own separately licensed commercial copy of NRLMSIS 2.1?

9. Commercial Permissions, Services, and Data Products:
   What specific written permissions from NRL IP Counsel (and/or Office of Naval Research Counsel) would be required for any future commercial use, paid services, paid software distribution, or fee-based data products generated using the Software (Sections 2 and 4(a)), and what is the proper NRL IP Counsel contact workflow for commercial users?

We have attached/prepared the following technical supporting documents for your review:
- `NRL_COMPONENT_DEPENDENCY_MAP.md` (technical coupling across all layers)
- `NRL_SECTION_4B_OBLIGATION_MAP.md` (clause-by-clause mapping against `nrlmsis2.1_license.txt`)
- `NRL_DISTRIBUTION_SCENARIOS.md` (comparison of distribution models A–E)

Public release and binary redistribution remain on hold pending your written guidance. Thank you very much for your time and assistance.

Sincerely,
[VERIFIED AUTHOR / MAINTAINER NAME AND CONTACT DETAILS TO BE INSERTED PRIOR TO SENDING]
```
