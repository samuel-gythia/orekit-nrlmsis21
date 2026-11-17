import sys
import platform
import subprocess
from importlib.metadata import version, PackageNotFoundError

print("=== 1. Python & OS Environment ===")
print(f"OS:             {platform.platform()}")
print(f"Architecture:   {platform.machine()}")
print(f"Python Version: {sys.version}")
print(f"Executable:     {sys.executable}")

for pkg in ["orekit-jpype", "jpype1", "numpy", "scipy"]:
    try:
        print(f"Package {pkg:15s}: {version(pkg)}")
    except PackageNotFoundError:
        print(f"Package {pkg:15s}: NOT INSTALLED")

print("\n=== 2. Compilers on PATH ===")
for tool in ["gfortran", "gcc", "cmake", "java", "javac"]:
    try:
        out = subprocess.check_output([tool, "--version"], stderr=subprocess.STDOUT, text=True).splitlines()[0]
        print(f"{tool:10s}: {out}")
    except Exception as exc:
        print(f"{tool:10s}: MISSING or error ({exc})")

print("\n=== 3. Orekit JVM & Atmosphere Interface Inspection ===")
try:
    import orekit_jpype as orekit
    import jpype
    orekit.initVM()
    from java.lang import System
    print(f"JVM Version:    {System.getProperty('java.version')}")
    print(f"JVM Vendor:     {System.getProperty('java.vendor')}")
    print(f"JAVA_HOME(JVM): {System.getProperty('java.home')}")

    from org.orekit.models.earth.atmosphere import Atmosphere
    atm_class = Atmosphere.class_
    print(f"Interface:      {atm_class.getName()}")
    print("Declared Methods on Atmosphere:")
    for m in atm_class.getDeclaredMethods():
        params = ", ".join([p.getSimpleName() for p in m.getParameterTypes()])
        print(f"  - {m.getReturnType().getSimpleName()} {m.getName()}({params})")
except Exception as exc:
    print(f"Orekit/JVM inspection failed: {exc}")
