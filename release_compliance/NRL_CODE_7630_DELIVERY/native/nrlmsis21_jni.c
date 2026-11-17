/*==============================================================================
 * File: native/nrlmsis21_jni.c
 * Purpose:
 *   Java Native Interface (JNI) C bridge connecting org.ssa.nrlmsis21.Nrlmsis21Native
 *   to the C-ABI functions declared in native/nrlmsis21_c_api.h under OS mutex
 *   serialization (Windows INIT_ONCE CRITICAL_SECTION / POSIX pthread_mutex_t).
 *
 * Integration & Modification Notice (NRL-SOF-014-1 Section 4(b)):
 *   - Date of change: 2026-11-17
 *   - Authored independently for orekit-nrlmsis21; contains no copied upstream
 *     NRLMSIS 2.1 source code and makes no direct Fortran calls.
 *   - Compiles and links locally with native/nrlmsis21_c_api.F90 and user-supplied
 *     upstream NRLMSIS 2.1 into libnrlmsis21_jni; upstream NRLMSIS 2.1 remains
 *     completely unmodified.
 *   - Conservatively governed by NRL-SOF-014-1 (see LICENSES/NRL-SOF-014-1.txt).
 *============================================================================*/

#include <jni.h>
#include <stdlib.h>
#include <string.h>
#include "nrlmsis21_c_api.h"

#if defined(_WIN32) || defined(__CYGWIN__)
  #include <windows.h>
  static CRITICAL_SECTION g_msis_lock;
  static INIT_ONCE g_lock_once = INIT_ONCE_STATIC_INIT;

  static BOOL CALLBACK init_lock_cb(PINIT_ONCE initOnce, PVOID param, PVOID *context) {
      (void)initOnce;
      (void)param;
      (void)context;
      InitializeCriticalSection(&g_msis_lock);
      return TRUE;
  }

  static void acquire_lock(void) {
      InitOnceExecuteOnce(&g_lock_once, init_lock_cb, NULL, NULL);
      EnterCriticalSection(&g_msis_lock);
  }

  static void release_lock(void) {
      LeaveCriticalSection(&g_msis_lock);
  }
#else
  #include <pthread.h>
  static pthread_mutex_t g_msis_lock = PTHREAD_MUTEX_INITIALIZER;

  static void acquire_lock(void) { pthread_mutex_lock(&g_msis_lock); }
  static void release_lock(void) { pthread_mutex_unlock(&g_msis_lock); }
#endif

static jint jni_init_impl(
    JNIEnv *env, jstring jParmPath, jstring jParmFile, int use_ex, jboolean jStormApMode)
{
    if (jParmPath == NULL || jParmFile == NULL) return MSIS21_ERR_NULL_POINTER;

    const char *path = (*env)->GetStringUTFChars(env, jParmPath, NULL);
    const char *file = (*env)->GetStringUTFChars(env, jParmFile, NULL);
    if (path == NULL || file == NULL) {
        if (path) (*env)->ReleaseStringUTFChars(env, jParmPath, path);
        if (file) (*env)->ReleaseStringUTFChars(env, jParmFile, file);
        return MSIS21_ERR_NULL_POINTER;
    }

    acquire_lock();
    int status = use_ex
        ? msis21_init_ex_c(path, file, (jStormApMode != JNI_FALSE) ? 1 : 0)
        : msis21_init_c(path, file);
    release_lock();

    (*env)->ReleaseStringUTFChars(env, jParmPath, path);
    (*env)->ReleaseStringUTFChars(env, jParmFile, file);
    return (jint)status;
}

JNIEXPORT jint JNICALL
Java_org_ssa_nrlmsis21_Nrlmsis21Native_init__Ljava_lang_String_2Ljava_lang_String_2(
    JNIEnv *env, jclass cls, jstring jParmPath, jstring jParmFile)
{
    (void)cls;
    return jni_init_impl(env, jParmPath, jParmFile, 0, JNI_TRUE);
}

JNIEXPORT jint JNICALL
Java_org_ssa_nrlmsis21_Nrlmsis21Native_init__Ljava_lang_String_2Ljava_lang_String_2Z(
    JNIEnv *env, jclass cls, jstring jParmPath, jstring jParmFile, jboolean jStormApMode)
{
    (void)cls;
    return jni_init_impl(env, jParmPath, jParmFile, 1, jStormApMode);
}

JNIEXPORT jint JNICALL Java_org_ssa_nrlmsis21_Nrlmsis21Native_setStormApMode(
    JNIEnv *env, jclass cls, jboolean jStormApMode)
{
    (void)env;
    (void)cls;
    acquire_lock();
    int status = msis21_set_storm_ap_mode_c((jStormApMode != JNI_FALSE) ? 1 : 0);
    release_lock();
    return (jint)status;
}

JNIEXPORT jboolean JNICALL Java_org_ssa_nrlmsis21_Nrlmsis21Native_isStormApMode(
    JNIEnv *env, jclass cls)
{
    (void)env;
    (void)cls;
    acquire_lock();
    int res = msis21_get_storm_ap_mode_c();
    release_lock();
    return (res == 1) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jboolean JNICALL Java_org_ssa_nrlmsis21_Nrlmsis21Native_isInitialized(
    JNIEnv *env, jclass cls)
{
    (void)env;
    (void)cls;
    acquire_lock();
    int res = msis21_is_initialized_c();
    release_lock();
    return (res == 1) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jint JNICALL Java_org_ssa_nrlmsis21_Nrlmsis21Native_calc(
    JNIEnv *env, jclass cls,
    jdouble day, jdouble utsec, jdouble zKm, jdouble latDeg, jdouble lonDeg,
    jdouble sfluxavg, jdouble sflux,
    jdoubleArray jAp7, jdoubleArray jOutScalars, jdoubleArray jOutDn)
{
    (void)cls;
    if (jAp7 == NULL || jOutScalars == NULL || jOutDn == NULL) return MSIS21_ERR_NULL_POINTER;
    if ((*env)->GetArrayLength(env, jAp7) < 7 ||
        (*env)->GetArrayLength(env, jOutScalars) < 3 ||
        (*env)->GetArrayLength(env, jOutDn) < 10) return MSIS21_ERR_NULL_POINTER;

    jdouble *ap_ptr = (*env)->GetDoubleArrayElements(env, jAp7, NULL);
    if (ap_ptr == NULL) return MSIS21_ERR_NULL_POINTER;

    double rho = 0.0, tn = 0.0, tex = 0.0, dn[10];

    acquire_lock();
    int status = msis21_calc_c(
        (double)day, (double)utsec, (double)zKm, (double)latDeg, (double)lonDeg,
        (double)sfluxavg, (double)sflux, ap_ptr,
        &rho, &tn, &tex, dn
    );
    release_lock();

    (*env)->ReleaseDoubleArrayElements(env, jAp7, ap_ptr, JNI_ABORT);

    if (status == MSIS21_SUCCESS) {
        jdouble scalars[3] = { (jdouble)rho, (jdouble)tn, (jdouble)tex };
        (*env)->SetDoubleArrayRegion(env, jOutScalars, 0, 3, scalars);
        jdouble dn_j[10];
        for (int i = 0; i < 10; ++i) dn_j[i] = (jdouble)dn[i];
        (*env)->SetDoubleArrayRegion(env, jOutDn, 0, 10, dn_j);
    }

    return (jint)status;
}
