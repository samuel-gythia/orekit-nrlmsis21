/*==============================================================================
 * File: native/nrlmsis21_c_api.h
 * Purpose:
 *   C11 header declaring the stable extern "C" ABI and status codes for
 *   native/nrlmsis21_c_api.F90.
 *
 * Integration & Modification Notice (NRL-SOF-014-1 Section 4(b)):
 *   - Date of change: 2026-11-17
 *   - Authored independently for orekit-nrlmsis21; contains no copied upstream
 *     NRLMSIS 2.1 source code. Upstream NRLMSIS 2.1 remains unmodified.
 *   - Defines the C interface bound to nrlmsis21_c_api.F90 and is conservatively
 *     governed by NRL-SOF-014-1 (see LICENSES/NRL-SOF-014-1.txt).
 *============================================================================*/

#ifndef NRLMSIS21_C_API_H
#define NRLMSIS21_C_API_H

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32) || defined(__CYGWIN__)
  #if defined(NRLMSIS21_EXPORTS)
    #define NRLMSIS21_API __declspec(dllexport)
  #else
    #define NRLMSIS21_API
  #endif
#else
  #define NRLMSIS21_API __attribute__((visibility("default")))
#endif

#define MSIS21_SUCCESS              0
#define MSIS21_ERR_NULL_POINTER    -1
#define MSIS21_ERR_INVALID_INPUT   -2
#define MSIS21_ERR_INIT_FAILED     -3
#define MSIS21_ERR_NOT_INITIALIZED -4

NRLMSIS21_API int msis21_init_c(const char* parmpath, const char* parmfile);
NRLMSIS21_API int msis21_init_ex_c(const char* parmpath, const char* parmfile, int storm_ap_mode);
NRLMSIS21_API int msis21_set_storm_ap_mode_c(int storm_ap_mode);
NRLMSIS21_API int msis21_get_storm_ap_mode_c(void);
NRLMSIS21_API int msis21_is_initialized_c(void);
NRLMSIS21_API int msis21_calc_c(
    double day, double utsec, double z_km, double lat_deg, double lon_deg,
    double sfluxavg, double sflux, const double ap7[7],
    double* out_rho_kg_m3, double* out_tn_k, double* out_tex_k, double out_dn[10]
);

#ifdef __cplusplus
}
#endif

#endif /* NRLMSIS21_C_API_H */
