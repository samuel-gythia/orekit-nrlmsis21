import sys
import os
import glob
from pathlib import Path
import orekit_jpype
import jpype

# Locate all JAR files bundled inside the orekit_jpype package
pkg_dir = Path(orekit_jpype.__file__).parent
jars = list(pkg_dir.rglob("*.jar"))
print("=== Bundled Orekit JARs ===")
for j in jars:
    print(f"  {j.name} ({j.stat().st_size // 1024} KB)")

# Build classpath string for javac
cp_str = os.pathsep.join(str(j.resolve()) for j in jars)
Path("orekit_classpath.txt").write_text(cp_str, encoding="utf-8")
print(f"\nSaved classpath with {len(jars)} JARs to orekit_classpath.txt")

# Check default method implementations on Atmosphere
orekit_jpype.initVM()
from org.orekit.models.earth.atmosphere import Atmosphere
cls = Atmosphere.class_
print("\n=== Atmosphere Methods & Modifiers ===")
for m in cls.getDeclaredMethods():
    is_def = m.isDefault()
    ret = m.getReturnType().getSimpleName()
    params = ", ".join([p.getSimpleName() for p in m.getParameterTypes()])
    print(f"  {'[DEFAULT]' if is_def else '[ABSTRACT]'} {ret} {m.getName()}({params})")
