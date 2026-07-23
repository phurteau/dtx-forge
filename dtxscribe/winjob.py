"""Bind this process and every child it spawns into a Windows Job Object that is destroyed
the instant the process dies, so NOTHING DTXScribe launches can outlive it: not the uvicorn
server, not a mid-encode ffmpeg, not a yt-dlp/deno download, not the WebView2 window.

This makes exit bulletproof across every path equally, because all of them end in the process
dying, which closes the last handle to the job and triggers KILL_ON_JOB_CLOSE:
  * the in-app Exit button (app.py /api/quit -> os._exit(0)),
  * the native window's X (pywebview returns -> main() returns -> interpreter exit),
  * an unexpected crash.

Flags:
  * KILL_ON_JOB_CLOSE  -- terminate every process still in the job when the job handle closes.
  * BREAKAWAY_OK       -- let a child that explicitly requests CREATE_BREAKAWAY_FROM_JOB leave
                          the job, so a WebView2 build that spawns detached helpers can still
                          start. Plain children (ffmpeg, deno, yt-dlp via subprocess.run) do
                          NOT request breakaway, so they stay governed and get reaped.

No-op (returns False) on non-Windows, if the job APIs fail, or if the process is already in a
non-nestable job (rare on Windows 8+, which supports nested jobs) -- in every such case the
app simply keeps its previous exit behavior.
"""
import sys

# The job handle is deliberately kept for the entire process lifetime. If it were closed or
# garbage-collected early, the job would close and KILL_ON_JOB_CLOSE would terminate us.
_JOB_HANDLE = None


def enable_kill_on_close():
    """Create the kill-on-close job and assign the current process to it. Returns True on
    success. Safe to call more than once (only the first call does anything)."""
    global _JOB_HANDLE
    if sys.platform != "win32" or _JOB_HANDLE is not None:
        return False
    try:
        import ctypes
        from ctypes import wintypes

        k32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
        JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
        JobObjectExtendedLimitInformation = 9

        k32.CreateJobObjectW.restype = wintypes.HANDLE
        k32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        hjob = k32.CreateJobObjectW(None, None)
        if not hjob:
            return False

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_BREAKAWAY_OK)
        k32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        if not k32.SetInformationJobObject(
                hjob, JobObjectExtendedLimitInformation,
                ctypes.byref(info), ctypes.sizeof(info)):
            k32.CloseHandle(hjob)
            return False

        k32.GetCurrentProcess.restype = wintypes.HANDLE
        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        if not k32.AssignProcessToJobObject(hjob, k32.GetCurrentProcess()):
            # Already in a job that can't be nested (very rare on Win8+). Keep prior behavior.
            k32.CloseHandle(hjob)
            return False

        _JOB_HANDLE = hjob
        return True
    except Exception:
        return False
