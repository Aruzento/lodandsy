"""Hidden child-process entry point. Set resource limits before native decoders load."""
import json
import os
import sys
import threading


def limit_worker():
    from lodandsy.application.map_pyramid import WORKER_MEMORY_BYTES

    if os.name != "nt":
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (WORKER_MEMORY_BYTES, WORKER_MEMORY_BYTES))
        return None
    import ctypes
    from ctypes import wintypes

    class Basic(ctypes.Structure):
        _fields_ = [("per_process", ctypes.c_longlong), ("per_job", ctypes.c_longlong),
                    ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                    ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in
                    ["read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes",
                     "other_bytes"]]

    class Extended(ctypes.Structure):
        _fields_ = [("basic", Basic), ("io", IO), ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t), ("peak_process", ctypes.c_size_t),
                    ("peak_job", ctypes.c_size_t)]

    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    api.CreateJobObjectW.restype = wintypes.HANDLE
    api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                          ctypes.c_void_p, wintypes.DWORD]
    api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    api.GetCurrentProcess.restype = wintypes.HANDLE
    handle = api.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x100 | 0x2000  # PROCESS_MEMORY | KILL_ON_JOB_CLOSE
    limits.process_memory = WORKER_MEMORY_BYTES
    if (not handle or not api.SetInformationJobObject(handle, 9, ctypes.byref(limits),
                                                     ctypes.sizeof(limits))
            or not api.AssignProcessToJobObject(handle, api.GetCurrentProcess())):
        raise ctypes.WinError(ctypes.get_last_error())
    return handle  # Keep alive until process exit; never attached to the GUI process.


def watch_parent(parent_pid):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = api.OpenProcess(0x100000, False, parent_pid)  # SYNCHRONIZE
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        def wait():
            if api.WaitForSingleObject(handle, 0xFFFFFFFF) == 0:
                os._exit(130)
    else:
        import time
        def wait():
            while os.getppid() == parent_pid:
                time.sleep(.25)
            os._exit(130)
    threading.Thread(target=wait, name="map-parent-watch", daemon=True).start()


def _run(args):
    args = list(args if args is not None else sys.argv[1:])
    watch_parent(int(args.pop()))
    job = limit_worker()
    from lodandsy.application.map_pyramid import build_pyramid

    def progress(value):
        print(json.dumps({"progress": value}), flush=True)
    build_pyramid(*args, progress)
    progress(100)
    return 0 if job is not False else 1


def main(args=None):
    if os.name == "nt" and getattr(sys, "frozen", False):
        # A windowed PyInstaller entry sets sys.stdout/stderr=None even when the parent
        # supplies pipes. Restore only the hidden worker's inherited pipe handles.
        import ctypes
        import msvcrt
        from ctypes import wintypes
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.GetStdHandle.argtypes = [wintypes.DWORD]
        api.GetStdHandle.restype = wintypes.HANDLE
        for name, handle_id in [("stdout", -11), ("stderr", -12)]:
            if getattr(sys, name) is None:
                handle = api.GetStdHandle(handle_id & 0xFFFFFFFF)
                if handle and handle != ctypes.c_void_p(-1).value:
                    descriptor = msvcrt.open_osfhandle(handle, os.O_WRONLY | os.O_BINARY)
                    setattr(sys, name, open(descriptor, "w", encoding="utf-8", buffering=1))
    try:
        return _run(args)
    except Exception as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=True), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
