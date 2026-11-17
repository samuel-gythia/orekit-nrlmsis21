$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BuildDir    = Join-Path $ProjectRoot "build\milestone2_c"

Write-Host "=== Milestone 3: Building NRLMSIS 2.1 Java/JNI Bridge ===" -ForegroundColor Cyan

# Optional: point MSYS2_UCRT64_BIN at a 64-bit MSYS2 UCRT64 toolchain (e.g. C:\msys64\ucrt64\bin).
$Ucrt = $env:MSYS2_UCRT64_BIN
$CmakeArgs = @("-G", "Ninja", "-DCMAKE_BUILD_TYPE=Release")
if ($env:NRLMSIS21_SOURCE_DIR) {
    $CmakeArgs += @("-DNRLMSIS21_SOURCE_DIR=$($env:NRLMSIS21_SOURCE_DIR -replace '\\','/')")
}
if ($Ucrt) {
    $env:Path = "$Ucrt;$env:Path"
    $CmakeArgs += @("-DCMAKE_Fortran_COMPILER=$($Ucrt -replace '\\','/')/gfortran.exe",
                    "-DCMAKE_C_COMPILER=$($Ucrt -replace '\\','/')/gcc.exe")
}

# 1. Compile C/JNI Shared Library
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null
Push-Location $BuildDir
try {
    Write-Host "Configuring CMake for JNI ..." -ForegroundColor Yellow
    & cmake @CmakeArgs "$ProjectRoot"
    if ($LASTEXITCODE -ne 0) {
        Write-Error "CMake configuration failed."
    }

    Write-Host "Compiling libnrlmsis21_jni.dll ..." -ForegroundColor Yellow
    & cmake --build . --target nrlmsis21_jni --config Release
    if ($LASTEXITCODE -ne 0) {
        Write-Error "CMake build of nrlmsis21_jni failed."
    }
} finally {
    Pop-Location
}
Write-Host "[OK] Compiled libnrlmsis21_jni.dll" -ForegroundColor Green

# 2. Compile ALL Java classes and build the complete v1.0.2 JAR (never a partial JAR)
& (Join-Path $PSScriptRoot "build_java.ps1")
if ($LASTEXITCODE -ne 0) {
    Write-Error "build_java.ps1 failed."
}

# 3. Run Java JNI Verification Script
Write-Host "Running Java JNI reference and concurrency tests ..." -ForegroundColor Yellow
& python (Join-Path $ProjectRoot "tests\test_jni_bridge.py")
