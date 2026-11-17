!===============================================================================
! File: native/nrlmsis21_c_api.F90
! Purpose:
!   Fortran 2003 ISO_C_BINDING C-ABI wrapper exposing thread-safe initialization,
!   storm/daily Ap mode selection, and density/temperature evaluation entry points
!   (msis21_init_c, msis21_init_ex_c, msis21_set_storm_ap_mode_c,
!    msis21_get_storm_ap_mode_c, msis21_is_initialized_c, msis21_calc_c).
!
! Integration & Modification Notice (NRL-SOF-014-1 Section 4(b)):
!   - Date of change: 2026-11-17
!   - Authored independently for orekit-nrlmsis21; no upstream NRLMSIS 2.1 source
!     files were copied into or modified inside this file.
!   - Directly USEs upstream NRLMSIS 2.1 modules (msis_constants, msis_init,
!     msis_calc) and calls msisinit, tselec, and msiscalc with -DDBLE double
!     precision, 536,576-byte msis21.parm validation, bounded 128-char path
!     handling, per-call output zero-initialization, and SAVE-cache flushing.
!   - Upstream NRLMSIS 2.1 scientific equations and parameter files remain
!     completely unmodified.
!   - Conservatively governed by NRL-SOF-014-1 (see LICENSES/NRL-SOF-014-1.txt).
!===============================================================================

module nrlmsis21_c_api
    use, intrinsic :: iso_c_binding, only: &
        c_char, c_int, c_double, c_ptr, c_null_char, c_associated, c_f_pointer
    use, intrinsic :: iso_fortran_env, only: int64
    use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
    use msis_constants,              only: rp
    use msis_init,                   only: msisinit, tselec
    use msis_calc,                   only: msiscalc
    implicit none
    private

    public :: msis21_init_c, msis21_init_ex_c, msis21_set_storm_ap_mode_c, &
              msis21_get_storm_ap_mode_c, msis21_is_initialized_c, msis21_calc_c

    integer(c_int), parameter, public :: MSIS21_SUCCESS             = 0
    integer(c_int), parameter, public :: MSIS21_ERR_NULL_POINTER    = -1
    integer(c_int), parameter, public :: MSIS21_ERR_INVALID_INPUT   = -2
    integer(c_int), parameter, public :: MSIS21_ERR_INIT_FAILED     = -3
    integer(c_int), parameter, public :: MSIS21_ERR_NOT_INITIALIZED = -4

    integer,        parameter :: MAX_MSIS_PATH_LEN = 128
    integer(int64), parameter :: PARM_FILE_BYTES   = 536576_int64
    integer,        parameter :: PARM_VALUE_COUNT  = 67072

    logical, save :: is_initialized     = .false.
    logical, save :: current_storm_mode = .true.

contains

    subroutine copy_c_string_bounded(c_str_ptr, max_len, f_str, ok_len)
        type(c_ptr), intent(in) :: c_str_ptr
        integer, intent(in) :: max_len
        character(len=:), allocatable, intent(out) :: f_str
        logical, intent(out) :: ok_len

        character(kind=c_char), pointer :: c_arr(:)
        integer :: slen, i

        call c_f_pointer(c_str_ptr, c_arr, [max_len + 1])
        slen = 0
        ok_len = .false.
        do i = 1, max_len + 1
            if (c_arr(i) == c_null_char) then
                ok_len = .true.
                exit
            end if
            slen = slen + 1
        end do

        if (.not. ok_len) then
            f_str = ""
            return
        end if

        allocate(character(len=slen) :: f_str)
        do i = 1, slen
            f_str(i:i) = c_arr(i)
        end do
    end subroutine copy_c_string_bounded

    subroutine build_switch_legacy(storm_ap_mode, sw_arr)
        integer(c_int), intent(in) :: storm_ap_mode
        real(4), intent(out) :: sw_arr(25)

        sw_arr = 1.0_4
        if (storm_ap_mode /= 0_c_int) then
            sw_arr(9) = -1.0_4
        else
            sw_arr(9) = 1.0_4
        end if
    end subroutine build_switch_legacy

    subroutine flush_msiscalc_cache()
        real(kind=rp) :: dummy_ap(7)
        real(kind=rp) :: dummy_tn, dummy_tex
        real(kind=rp) :: dummy_dn(10)

        dummy_ap  = 4.0_rp
        dummy_tn  = 0.0_rp
        dummy_tex = 0.0_rp
        dummy_dn  = 0.0_rp
        ! day=-999 forces msiscalc's SAVE cache comparison (day .ne. lastday) to miss on next valid call
        call msiscalc(-999.0_rp, 0.0_rp, 100.0_rp, 0.0_rp, 0.0_rp, &
                      150.0_rp, 150.0_rp, dummy_ap, dummy_tn, dummy_dn, dummy_tex)
    end subroutine flush_msiscalc_cache

    function validate_parm_file(fullpath) result(ok)
        character(len=*), intent(in) :: fullpath
        logical :: ok

        logical :: exists
        integer(int64) :: fsize
        integer :: u, ios
        real(c_double), allocatable :: parm_vals(:)

        ok = .false.
        inquire(file=fullpath, exist=exists, size=fsize, iostat=ios)
        if (ios /= 0 .or. .not. exists .or. fsize /= PARM_FILE_BYTES) then
            return
        end if

        allocate(parm_vals(PARM_VALUE_COUNT), stat=ios)
        if (ios /= 0) then
            return
        end if

        open(newunit=u, file=fullpath, status='old', action='read', &
             access='stream', form='unformatted', convert='little_endian', iostat=ios)
        if (ios /= 0) then
            deallocate(parm_vals)
            return
        end if

        read(u, iostat=ios) parm_vals
        close(u)

        if (ios /= 0) then
            deallocate(parm_vals)
            return
        end if

        ok = all(ieee_is_finite(parm_vals))
        deallocate(parm_vals)
    end function validate_parm_file

    function msis21_init_c(c_parmpath, c_parmfile) result(status) &
            bind(C, name="msis21_init_c")
#if defined(_WIN32) || defined(__CYGWIN__)
!GCC$ ATTRIBUTES DLLEXPORT :: msis21_init_c
#endif
        type(c_ptr), value, intent(in) :: c_parmpath
        type(c_ptr), value, intent(in) :: c_parmfile
        integer(c_int) :: status

        status = msis21_init_ex_c(c_parmpath, c_parmfile, 1_c_int)
    end function msis21_init_c

    function msis21_init_ex_c(c_parmpath, c_parmfile, storm_ap_mode) result(status) &
            bind(C, name="msis21_init_ex_c")
#if defined(_WIN32) || defined(__CYGWIN__)
!GCC$ ATTRIBUTES DLLEXPORT :: msis21_init_ex_c
#endif
        type(c_ptr),    value, intent(in) :: c_parmpath
        type(c_ptr),    value, intent(in) :: c_parmfile
        integer(c_int), value, intent(in) :: storm_ap_mode
        integer(c_int) :: status

        character(len=:), allocatable :: f_parmpath, f_parmfile, fullpath
        logical :: ok_path, ok_file
        integer :: plen
        real(4) :: sw_arr(25)

        if (.not. c_associated(c_parmpath) .or. .not. c_associated(c_parmfile)) then
            status = MSIS21_ERR_NULL_POINTER
            return
        end if

        call copy_c_string_bounded(c_parmpath, MAX_MSIS_PATH_LEN, f_parmpath, ok_path)
        call copy_c_string_bounded(c_parmfile, MAX_MSIS_PATH_LEN, f_parmfile, ok_file)
        if (.not. ok_path .or. .not. ok_file) then
            status = MSIS21_ERR_INIT_FAILED
            return
        end if

        plen = len(f_parmpath)
        if (plen > 0) then
            if (f_parmpath(plen:plen) /= '/' .and. f_parmpath(plen:plen) /= '\') then
                f_parmpath = f_parmpath // '/'
            end if
        end if

        if (len(f_parmpath) > MAX_MSIS_PATH_LEN .or. &
            len(f_parmfile) == 0 .or. len(f_parmfile) > MAX_MSIS_PATH_LEN) then
            status = MSIS21_ERR_INIT_FAILED
            return
        end if

        fullpath = f_parmpath // f_parmfile
        if (.not. validate_parm_file(fullpath)) then
            status = MSIS21_ERR_INIT_FAILED
            return
        end if

        call build_switch_legacy(storm_ap_mode, sw_arr)
        call msisinit(parmpath=f_parmpath, parmfile=f_parmfile, &
                      switch_legacy=sw_arr, lzalt_type=.true.)
        call flush_msiscalc_cache()

        is_initialized = .true.
        current_storm_mode = (storm_ap_mode /= 0_c_int)
        status = MSIS21_SUCCESS
    end function msis21_init_ex_c

    function msis21_set_storm_ap_mode_c(storm_ap_mode) result(status) &
            bind(C, name="msis21_set_storm_ap_mode_c")
#if defined(_WIN32) || defined(__CYGWIN__)
!GCC$ ATTRIBUTES DLLEXPORT :: msis21_set_storm_ap_mode_c
#endif
        integer(c_int), value, intent(in) :: storm_ap_mode
        integer(c_int) :: status
        real(4) :: sw_arr(25)

        if (.not. is_initialized) then
            status = MSIS21_ERR_NOT_INITIALIZED
            return
        end if

        call build_switch_legacy(storm_ap_mode, sw_arr)
        call tselec(sw_arr)
        call flush_msiscalc_cache()

        current_storm_mode = (storm_ap_mode /= 0_c_int)
        status = MSIS21_SUCCESS
    end function msis21_set_storm_ap_mode_c

    function msis21_get_storm_ap_mode_c() result(res) &
            bind(C, name="msis21_get_storm_ap_mode_c")
#if defined(_WIN32) || defined(__CYGWIN__)
!GCC$ ATTRIBUTES DLLEXPORT :: msis21_get_storm_ap_mode_c
#endif
        integer(c_int) :: res

        if (.not. is_initialized) then
            res = MSIS21_ERR_NOT_INITIALIZED
        else if (current_storm_mode) then
            res = 1_c_int
        else
            res = 0_c_int
        end if
    end function msis21_get_storm_ap_mode_c

    function msis21_is_initialized_c() result(res) &
            bind(C, name="msis21_is_initialized_c")
#if defined(_WIN32) || defined(__CYGWIN__)
!GCC$ ATTRIBUTES DLLEXPORT :: msis21_is_initialized_c
#endif
        integer(c_int) :: res

        if (is_initialized) then
            res = 1_c_int
        else
            res = 0_c_int
        end if
    end function msis21_is_initialized_c

    function msis21_calc_c(day, utsec, z_km, lat_deg, lon_deg, &
                           sfluxavg, sflux, c_ap7, &
                           c_rho, c_tn, c_tex, c_dn) result(status) &
            bind(C, name="msis21_calc_c")
#if defined(_WIN32) || defined(__CYGWIN__)
!GCC$ ATTRIBUTES DLLEXPORT :: msis21_calc_c
#endif
        real(c_double), value, intent(in) :: day
        real(c_double), value, intent(in) :: utsec
        real(c_double), value, intent(in) :: z_km
        real(c_double), value, intent(in) :: lat_deg
        real(c_double), value, intent(in) :: lon_deg
        real(c_double), value, intent(in) :: sfluxavg
        real(c_double), value, intent(in) :: sflux
        type(c_ptr),    value, intent(in) :: c_ap7
        type(c_ptr),    value, intent(in) :: c_rho
        type(c_ptr),    value, intent(in) :: c_tn
        type(c_ptr),    value, intent(in) :: c_tex
        type(c_ptr),    value, intent(in) :: c_dn
        integer(c_int) :: status

        real(c_double), pointer :: p_ap7(:), p_rho, p_tn, p_tex, p_dn(:)
        real(kind=rp) :: f_day, f_utsec, f_z, f_lat, f_lon, f_sfluxavg, f_sflux
        real(kind=rp) :: f_ap(7)
        real(kind=rp) :: f_tn, f_tex
        real(kind=rp) :: f_dn(10)
        integer :: i

        if (.not. c_associated(c_ap7) .or. &
            .not. c_associated(c_rho) .or. &
            .not. c_associated(c_tn)  .or. &
            .not. c_associated(c_tex) .or. &
            .not. c_associated(c_dn)) then
            status = MSIS21_ERR_NULL_POINTER
            return
        end if

        if (.not. is_initialized) then
            status = MSIS21_ERR_NOT_INITIALIZED
            return
        end if

        call c_f_pointer(c_ap7, p_ap7, [7])
        call c_f_pointer(c_rho, p_rho)
        call c_f_pointer(c_tn,  p_tn)
        call c_f_pointer(c_tex, p_tex)
        call c_f_pointer(c_dn,  p_dn,  [10])

        ! Explicit per-call zero-initialization prevents stale stack NaN * 0.0 in dn(1)
        f_dn  = 0.0_rp
        f_tn  = 0.0_rp
        f_tex = 0.0_rp

        f_day      = real(day,      kind=rp)
        f_utsec    = real(utsec,    kind=rp)
        f_z        = real(z_km,     kind=rp)
        f_lat      = real(lat_deg,  kind=rp)
        f_lon      = real(lon_deg,  kind=rp)
        f_sfluxavg = real(sfluxavg, kind=rp)
        f_sflux    = real(sflux,    kind=rp)
        do i = 1, 7
            f_ap(i) = real(p_ap7(i), kind=rp)
        end do

        if (.not. (ieee_is_finite(f_day)      .and. &
                   ieee_is_finite(f_utsec)    .and. &
                   ieee_is_finite(f_z)        .and. &
                   ieee_is_finite(f_lat)      .and. &
                   ieee_is_finite(f_lon)      .and. &
                   ieee_is_finite(f_sfluxavg) .and. &
                   ieee_is_finite(f_sflux)    .and. &
                   all(ieee_is_finite(f_ap)))) then
            status = MSIS21_ERR_INVALID_INPUT
            return
        end if

        if (f_sfluxavg < 0.0_rp .or. f_sflux < 0.0_rp .or. any(f_ap < 0.0_rp)) then
            status = MSIS21_ERR_INVALID_INPUT
            return
        end if

        call msiscalc(f_day, f_utsec, f_z, f_lat, f_lon, f_sfluxavg, f_sflux, f_ap, f_tn, f_dn, f_tex)

        if (.not. (ieee_is_finite(f_dn(1)) .and. ieee_is_finite(f_tn) .and. &
                   ieee_is_finite(f_tex) .and. all(ieee_is_finite(f_dn)))) then
            status = MSIS21_ERR_INVALID_INPUT
            return
        end if

        p_rho = real(f_dn(1), kind=c_double)
        p_tn  = real(f_tn,    kind=c_double)
        p_tex = real(f_tex,   kind=c_double)
        do i = 1, 10
            p_dn(i) = real(f_dn(i), kind=c_double)
        end do

        status = MSIS21_SUCCESS
    end function msis21_calc_c

end module nrlmsis21_c_api
