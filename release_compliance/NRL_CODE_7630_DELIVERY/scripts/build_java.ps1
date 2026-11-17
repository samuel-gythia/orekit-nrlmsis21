$ErrorActionPreference = "Stop"
$Version     = "1.0.2"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$TargetDir   = Join-Path $ProjectRoot "target"
$ClassesDir  = Join-Path $TargetDir "classes"
$PkgLibDir   = Join-Path $ProjectRoot "python\orekit_nrlmsis21\lib"
$JarName     = "orekit-nrlmsis21-$Version.jar"
$JarPath     = Join-Path $TargetDir $JarName

# Discover the Orekit JARs bundled with orekit-jpype (no machine-specific classpath file needed).
$PyCode = "import orekit_jpype, os, pathlib; print(os.pathsep.join(str(j.resolve()) for j in pathlib.Path(orekit_jpype.__file__).parent.rglob('*.jar')))"
$OrekitClasspath = (& python -c $PyCode).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($OrekitClasspath)) {
    Write-Error "Could not discover Orekit JARs. Install orekit-jpype first: python -m pip install orekit-jpype"
}

if (Test-Path $ClassesDir) { Remove-Item -Recurse -Force $ClassesDir }
New-Item -ItemType Directory -Force -Path $ClassesDir | Out-Null
New-Item -ItemType Directory -Force -Path $PkgLibDir | Out-Null

$JavaSources = Get-ChildItem -Path (Join-Path $ProjectRoot "java\src\main\java") -Filter "*.java" -Recurse | ForEach-Object { $_.FullName }

Write-Host "Compiling Java sources with javac --release 17 against Orekit classpath ..." -ForegroundColor Yellow
& javac --release 17 -cp "$OrekitClasspath" -d "$ClassesDir" $JavaSources
if ($LASTEXITCODE -ne 0) {
    Write-Error "javac compilation failed."
}

Write-Host "Creating $JarPath ..." -ForegroundColor Yellow
if (Test-Path $JarPath) { Remove-Item -Force $JarPath }
& jar cf "$JarPath" -C "$ClassesDir" .
if ($LASTEXITCODE -ne 0) {
    Write-Error "jar packaging failed."
}

# Replace any previous JAR in the Python package with the freshly built one.
Get-ChildItem -Path $PkgLibDir -Filter "orekit-nrlmsis21-*.jar" -ErrorAction SilentlyContinue | Remove-Item -Force
Copy-Item $JarPath -Destination (Join-Path $PkgLibDir $JarName) -Force

Write-Host "[OK] Successfully packaged $JarPath and copied it to $PkgLibDir" -ForegroundColor Green
