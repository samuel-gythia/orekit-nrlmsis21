package org.ssa.nrlmsis21;

import java.io.File;
import java.util.Locale;

/**
 * Low-level JNI bridge to the native NRLMSIS 2.1 Fortran/C library.
 */
public final class Nrlmsis21Native {
    private static volatile boolean loaded = false;

    private Nrlmsis21Native() {}

    /**
     * Loads the native JNI library from an explicit filesystem path or a bare library name.
     */
    public static synchronized void load(String libraryPath) {
        if (loaded) {
            return;
        }
        if (libraryPath == null || libraryPath.isEmpty()) {
            throw new UnsatisfiedLinkError("Native library path must not be null or empty.");
        }

        File f = new File(libraryPath).getAbsoluteFile();
        String lower = libraryPath.toLowerCase(Locale.ROOT);
        boolean isFilesystemPath = libraryPath.contains("/")
                || libraryPath.contains("\\")
                || lower.endsWith(".dll")
                || lower.endsWith(".so")
                || lower.endsWith(".dylib")
                || f.exists();

        if (isFilesystemPath) {
            if (!f.exists() || !f.isFile()) {
                throw new UnsatisfiedLinkError("Native library file not found: " + f.getAbsolutePath());
            }
            System.load(f.getAbsolutePath());
        } else {
            System.loadLibrary(libraryPath);
        }
        loaded = true;
    }

    public static boolean isLoaded() {
        return loaded;
    }

    public static boolean isReady() {
        return loaded && isInitialized();
    }

    public static native int init(String parmPath, String parmFile);
    public static native int init(String parmPath, String parmFile, boolean stormApMode);
    public static native int setStormApMode(boolean stormApMode);
    public static native boolean isStormApMode();
    public static native boolean isInitialized();
    public static native int calc(
        double day, double utsec, double zKm, double latDeg, double lonDeg,
        double sfluxavg, double sflux, double[] ap7,
        double[] outScalars, double[] outDn
    );
}
