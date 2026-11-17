# Formal NRL Code 7630 Section 4(b) Delivery Email Draft

> **DO NOT SEND AUTOMATICALLY.** Review maintainer signature and attach `NRL_CODE_7630_DELIVERY.zip` (SHA-256: `8cb6d926d162e1ccd733e9b6520b3bcf4becf1d5cffde99e097710ca65c7b5ce`) before transmitting.

```text
To: John Emmert <john.emmert@nrl.navy.mil>; Douglas Drob <douglas.drob@nrl.navy.mil>; McArthur Jones Jr. <mcarthur.jones@nrl.navy.mil>; NRL Code 7630
Subject: NRL-SOF-014-1 Section 4(b) Derivative/Integration Delivery — orekit-nrlmsis21 (v1.0.2)

Dear NRLMSIS Authors and NRL Code 7630,

Pursuant to Section 4(b) of the MSIS(R) (NRL-SOF-014-1) Open Source Academic Research License Agreement, we are delivering the source code, build instructions, and validation documentation for `orekit-nrlmsis21` (v1.0.2), an academic/research integration connecting NRLMSIS 2.1 to the open-source Orekit astrodynamics library.

1. Academic Research Purpose:
   This project was developed strictly for academic research and scientific software development in astrodynamics, orbit determination, and Space Situational Awareness. No commercial use is claimed or conducted.

2. Upstream Integrity:
   All upstream NRLMSIS 2.1 Fortran 2003 source files and `msis21.parm` remain completely unmodified and are NOT redistributed in our public repository; end users obtain NRLMSIS 2.1 independently from https://map.nrl.navy.mil/map/pub/nrl/NRLMSIS/NRLMSIS2.1/.

3. Supplied Native Integration / Potential Derivative Components (Attached in NRL_CODE_7630_DELIVERY.zip):
   - native/nrlmsis21_c_api.F90 (Fortran 2003 ISO_C_BINDING C-ABI wrapper calling msisinit, tselec, msiscalc)
   - native/nrlmsis21_c_api.h (C ABI header)
   - native/nrlmsis21_jni.c (thread-safe JNI C bridge)
   - java/src/main/java/org/ssa/nrlmsis21/*.java (Orekit Atmosphere and CSSI weather adapters)
   - CMakeLists.txt, pom.xml, build_dev.py, scripts/build_java.ps1
   - Architecture, Section 4(b) mapping, validation, and reproducibility documentation
   - SHA256SUMS.txt (package SHA-256: 8cb6d926d162e1ccd733e9b6520b3bcf4becf1d5cffde99e097710ca65c7b5ce)

4. Proposed GitHub Repository URL:
   https://github.com/samuel-gythia/orekit-nrlmsis21
   (Staged privately pending completion of this Code 7630 delivery and any written feedback.)

5. Government Rights & Open-Source Availability:
   In accordance with Section 4(b), these integration components carry prominent change notices and dates (2026-11-17), are made available as open-source software, and grant the Government of the United States of America a non-exclusive, irrevocable, fully paid-up license to any modifications and derivative works.

Sincerely,
samuel-gythia (orekit-nrlmsis21 Maintainer)
```
