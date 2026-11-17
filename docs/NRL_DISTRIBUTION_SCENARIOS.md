# Comparison of Distribution Scenarios (`orekit-nrlmsis21`)

This attachment compares five distribution and usage scenarios (A–E) for `orekit-nrlmsis21` under `NRL-SOF-014-1` and identifies which obligations appear relevant versus which require written NRL clarification.

---

## Summary Comparison Matrix

| Scenario | Upstream NRL Code/Binaries Included? | Appears Clearly Relevant (`NRL-SOF-014-1`) | Requires Written NRL Clarification | Current Risk Posture |
|---|---|---|---|---|
| **A. Academic researcher downloads source & builds locally** | Obtained separately by researcher from NRL | Researcher bound by Sections 2, 3, 4(a), 4(b), 4(c) upon downloading/using NRLMSIS 2.1 | Whether `nrlmsis21_c_api.F90` / `nrlmsis21_jni.c` require Code 7630 delivery before sharing the wrapper source | Low operational risk once Section 4(b) delivery/status of bridge files is clarified |
| **B. Public GitHub source repo (upstream NRLMSIS obtained separately)** | **No** (excluded) | Mandatory Section 4(c) notices if any file is a derivative work; no commercial-use claims | Derivative status of `nrlmsis21_c_api.F90`, `nrlmsis21_jni.c`, Java/Python; Section 4(b) delivery; permissive license compatibility | **Blocked** pending NRL Code 7630 written reply (and replacement of draft placeholders) |
| **C. Wrapper-only Python wheel (`py3-none-any`, no NRL binaries)** | **No** (excluded) | Must not misrepresent commercial clearance in PyPI/wheel metadata | Whether wrapper-only wheel triggers Section 4(c) ("incorporates the MSIS® Software or derivative work") & Section 4(b) | **Blocked** pending NRL Code 7630 reply + finalized `LICENSE`/`NOTICE` |
| **D. Precompiled distribution containing NRLMSIS native model (`.dll`/`.so` + `msis21.parm`)** | **Yes** (compiled NRL object code & `msis21.parm`) | Full `NRL-SOF-014-1` applies (Sec. 2 non-commercial only, Sec. 4a no fees, Sec. 4b open-source/delivery, Sec. 4c verbatim notice & `nrlmsis2.1_license.txt`), plus GPLv3/GCC-exception-3.1 if `libgfortran` is bundled | Whether NRL permits public redistribution of precompiled binary wheels on GitHub Releases / PyPI at all | **Prohibited / Do Not Publish** without explicit written NRL approval |
| **E. Commercial use or commercial redistribution** | Either separate or combined | **Prohibited** under `NRL-SOF-014-1` Sections 2 & 4(a) without written NRL IP Counsel consent | Whether commercial users with a separate NRL commercial license may use Apache-2.0 wrapper layers; NRL IP Counsel licensing workflow | **Prohibited** without prior written NRL IP Counsel consent |

---

## Detailed Scenario Analysis

### Scenario A: Academic Researcher Downloads Source and Builds Locally
- **Mechanics**: An academic researcher obtains `orekit-nrlmsis21` source for non-commercial research, independently downloads `nrlmsis2.1.tar.gz` from NRL (`https://map.nrl.navy.mil/map/pub/nrl/NRLMSIS/NRLMSIS2.1/`), compiles `libnrlmsis21_jni` locally with CMake (`-DNRLMSIS21_SOURCE_DIR`), and runs Orekit simulations.
- **Relevant Obligations**:
  - The researcher directly accepts `NRL-SOF-014-1` when obtaining NRLMSIS 2.1 (research/academic/non-profit use only; no fee-based data products under Section 4(a)).
  - On the publisher side, making `native/nrlmsis21_c_api.F90` available publicly still requires clarifying Section 4(b) derivative-work status and completing any required Code 7630 delivery first.

### Scenario B: Public GitHub Source Repository (Upstream NRLMSIS Obtained Separately)
- **Mechanics**: Similar to `pymsis`'s separation of wrapper code from NRL-licensed Fortran sources, the public GitHub repository distributes only project-authored Python, Java, C JNI, Fortran `ISO_C_BINDING`, build scripts, docs, and tests—with zero upstream `.F90` files, zero `msis21.parm`, and zero compiled binaries.
- **Relevant Obligations**:
  - No upstream NRL copyrighted files are redistributed.
  - Because `native/nrlmsis21_c_api.F90` directly `USE`s NRLMSIS 2.1 modules (`msis_constants`, `msis_init`, `msis_calc`), NRL clarification is needed on: (1) whether `nrlmsis21_c_api.F90` and/or `nrlmsis21_jni.c` are Section 4(b) derivative works, (2) which files must be delivered to NRL Code 7630, (3) whether pure Java/Python layers can carry a permissive license (`Apache-2.0` candidate), and (4) whether Section 4(c) applies to a source-only wrapper repo.

### Scenario C: Python Wheel Containing Independently Authored Wrappers Only (`py3-none-any`)
- **Mechanics**: Built via `OREKIT_NRLMSIS21_WRAPPER_ONLY=1 python setup.py bdist_wheel`, containing Python modules, `orekit-nrlmsis21-1.0.2.jar` (Java bytecode), and `nrlmsis2.1_license.txt`, with **no** `.dll`, `.so`, or `msis21.parm`.
- **Relevant Obligations & Uncertainties**:
  - Even though no compiled NRLMSIS binary is inside the wheel, the wheel requires local compilation of NRLMSIS 2.1 (or `NRLMSIS21_LIB_PATH`/`NRLMSIS21_PARM_PATH`) to compute densities.
  - Requires NRL clarification on Section 4(c) notice obligations, `MSIS®` trademark usage (Section 3) in PyPI package naming (`orekit-nrlmsis21`), and whether `Apache-2.0` metadata can be applied to the wrapper wheel without misleading downstream commercial users.

### Scenario D: Precompiled Distribution Containing the NRLMSIS Native Model
- **Mechanics**: Distributing `libnrlmsis21_jni.dll` / `libnrlmsis21_jni.so` and `msis21.parm` inside platform wheels (`win_amd64` / `linux_x86_64`) or GitHub Release archives.
- **Relevant Obligations**:
  - Directly redistributes compiled NRLMSIS 2.1 object code and `msis21.parm`, squarely triggering all `NRL-SOF-014-1` terms (Sections 2, 3, 4(a), 4(b), 4(c)), plus GNU GPLv3 + GCC Runtime Library Exception 3.1 obligations if `libgfortran.so.5` / `libgcc_s` are dynamically bundled.
  - **Safest Posture**: **Do not distribute** precompiled NRLMSIS binaries publicly unless explicit written authorization is received from NRL Code 7630 and NRL IP Counsel.

### Scenario E: Commercial Use or Commercial Redistribution
- **Mechanics**: Any commercial organization using `orekit-nrlmsis21` with NRLMSIS 2.1, offering hosted/paid orbit-determination services, selling software, or transferring generated density/ephemeris data products for a fee.
- **Relevant Obligations**:
  - **Explicitly prohibited** under `NRL-SOF-014-1` Section 2 (*"Any commercial use is prohibited"*) and Section 4(a) (*"shall not sell, or license, or transfer for a fee the Software or portion thereof, or any derivative work of the Software, or any data products generated by the Software, without first obtaining the written consent of IP Counsel for the Naval Research Laboratory"*).
  - **Clarification Needed**: Whether a commercial organization that separately purchases/obtains a commercial NRLMSIS 2.1 license from NRL may use the independently authored Java/Python/JNI wrapper layers if those layers are cleared for permissive licensing.
