"""
Automated Build Pipeline for orekit-nrlmsis21 (v1.0.2).
Compiles native Fortran/C libraries via CMake and Java classes via javac (--release 17),
packages the distribution JAR, copies it (and the native library) into the Python package
``lib/`` directory and links the Python package in development mode.

Windows note: run from an MSYS2 UCRT64 shell (or put ``C:\\msys64\\ucrt64\\bin`` first on PATH) so
CMake picks the 64-bit gcc/gfortran; pass ``--no-pip`` to skip the editable install.
"""
import argparse
import os
import sys
import shutil
import subprocess
from pathlib import Path

VERSION = "1.0.2"
JAR_NAME = f"orekit-nrlmsis21-{VERSION}.jar"


def run_cmd(cmd, cwd=None, env=None):
    cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
    print(f"[RUN] {cmd_str}")
    res = subprocess.run(cmd, cwd=cwd, env=env, shell=isinstance(cmd, str))
    if res.returncode != 0:
        print(f"[FAIL] Command failed with exit code {res.returncode}: {cmd_str}")
        sys.exit(res.returncode)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Build native JNI library, Java Orekit adapter JAR, and editable Python install."
    )
    parser.add_argument(
        "--nrlmsis-source-dir",
        default=os.environ.get("NRLMSIS21_SOURCE_DIR"),
        help="Path to upstream NRLMSIS 2.1 Fortran source directory (default: $NRLMSIS21_SOURCE_DIR or external/NRLMSIS2.1).",
    )
    parser.add_argument(
        "--build-dir",
        default=None,
        help="Separate local CMake build directory (default: build/milestone2_c).",
    )
    parser.add_argument(
        "--no-stage-package-lib",
        action="store_true",
        help="Do not copy the compiled native DLL/SO into python/orekit_nrlmsis21/lib/; keep it in --build-dir.",
    )
    parser.add_argument(
        "--skip-native",
        action="store_true",
        help="Skip CMake native Fortran/C compilation and build only the Java JAR (and optional pip install).",
    )
    parser.add_argument(
        "--no-pip",
        action="store_true",
        help="Skip `pip install -e .` after building.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parent
    if str(project_root / "python") not in sys.path:
        sys.path.insert(0, str(project_root / "python"))

    from orekit_nrlmsis21.acquire import validate_nrlmsis21_directory

    build_dir = (
        Path(args.build_dir).expanduser().resolve()
        if args.build_dir
        else (project_root / "build" / "milestone2_c")
    )
    target_dir = project_root / "target"
    classes_dir = target_dir / "classes"
    pkg_lib = project_root / "python" / "orekit_nrlmsis21" / "lib"
    skip_pip = args.no_pip
    nrlmsis_src = (
        Path(args.nrlmsis_source_dir).expanduser().resolve()
        if args.nrlmsis_source_dir
        else (project_root / "external" / "NRLMSIS2.1").resolve()
    )

    print("==========================================================================")
    print(f"  BUILDING OREKIT-NRLMSIS21 {VERSION} NATIVE & JAVA RUNTIME")
    print("==========================================================================")

    # 1. Ensure build directories exist (start from a clean classes dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    if classes_dir.exists():
        shutil.rmtree(classes_dir)
    classes_dir.mkdir(parents=True, exist_ok=True)
    pkg_lib.mkdir(parents=True, exist_ok=True)

    built_lib_path = None
    # 2. Build native C/Fortran JNI shared library via CMake (unless --skip-native)
    if args.skip_native:
        print("\n--- Step 1: Skipped Native JNI Build (--skip-native) ---")
    else:
        print("\n--- Step 1: Building Native JNI Shared Library (CMake) ---")
        print(f"Using NRLMSIS 2.1 Fortran source directory: {nrlmsis_src}")
        validate_nrlmsis21_directory(nrlmsis_src, require_parm=False, require_license=False)
        cmake_configure_cmd = [
            "cmake",
            "-S", ".",
            "-B", str(build_dir),
            "-G", "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DNRLMSIS21_SOURCE_DIR={nrlmsis_src}",
        ]
        run_cmd(cmake_configure_cmd, cwd=project_root)
        run_cmd(["cmake", "--build", str(build_dir), "--target", "nrlmsis21_jni", "--config", "Release"], cwd=project_root)

        lib_name = "libnrlmsis21_jni.dll" if sys.platform == "win32" else "libnrlmsis21_jni.so"
        built = next(iter(build_dir.rglob(lib_name)), None)
        if built is None:
            print(f"[FAIL] {lib_name} not found under {build_dir}")
            sys.exit(1)
        built_lib_path = built.resolve()
        if args.no_stage_package_lib:
            print(f"[OK] Kept compiled native library in {built_lib_path} (--no-stage-package-lib)")
        else:
            shutil.copy2(built, pkg_lib / lib_name)
            print(f"Copied {built} -> {pkg_lib / lib_name}")

    # 3. Read Orekit classpath from orekit-jpype (in memory; no machine-specific file is written)
    print("\n--- Step 2: Discovering Orekit Classpath ---")
    import orekit_jpype
    pkg_dir = Path(orekit_jpype.__file__).parent
    jars = list(pkg_dir.rglob("*.jar"))
    classpath = os.pathsep.join(str(j.resolve()) for j in jars)
    print(f"Discovered {len(jars)} Orekit JARs.")

    # 4. Compile Java sources (Java 17 bytecode, independent of the build JDK version)
    print("\n--- Step 3: Compiling Java Sources (javac --release 17) ---")
    java_files = [str(p) for p in (project_root / "java" / "src" / "main" / "java").rglob("*.java")]
    run_cmd(["javac", "--release", "17", "-cp", classpath, "-d", str(classes_dir)] + java_files)

    # 5. Package JAR and install into the Python package
    print("\n--- Step 4: Packaging JAR (jar) ---")
    jar_path = target_dir / JAR_NAME
    run_cmd(["jar", "cf", str(jar_path), "-C", str(classes_dir), "."])
    for stale in pkg_lib.glob("orekit-nrlmsis21-*.jar"):
        stale.unlink()
    shutil.copy2(jar_path, pkg_lib / JAR_NAME)
    print(f"Copied {jar_path} -> {pkg_lib / JAR_NAME}")

    # 6. Install Python package in editable mode
    if skip_pip:
        print("\n--- Step 5: Skipped editable install (--no-pip) ---")
    else:
        print("\n--- Step 5: Installing Python Wrapper in Editable Mode ---")
        run_cmd([sys.executable, "-m", "pip", "install", "-e", "."])

    print("\n[OK] Build complete! Package is ready to use via `import orekit_nrlmsis21`.")
    if built_lib_path is not None:
        parm_hint = nrlmsis_src / "msis21.parm"
        print("Runtime configuration (for wrapper-only / custom library runs):")
        print(f"  NRLMSIS21_LIB_PATH={built_lib_path}")
        print(f"  NRLMSIS21_PARM_PATH={parm_hint}")


if __name__ == "__main__":
    main()
