"""External read-only Windows process/socket/module observer. Never bundled in WrapLab.

Uses documented Win32 APIs, not WMI, injection, global input hooks or security changes.
Sampling is complemented by kernel ETW in forensic_windows.py; sampling alone can miss
very short events and is labelled accordingly.
"""

import ctypes as C
from ctypes import wintypes as W
from datetime import datetime, timezone
import hashlib
import socket
import threading
import time


class ProcessEntry(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("pid", W.DWORD),
                ("heap", C.c_size_t), ("module", W.DWORD), ("threads", W.DWORD),
                ("ppid", W.DWORD), ("priority", W.LONG), ("flags", W.DWORD),
                ("exe", W.WCHAR * 260)]


class ModuleEntry(C.Structure):
    _fields_ = [("dwSize", W.DWORD), ("module_id", W.DWORD), ("pid", W.DWORD),
                ("global_usage", W.DWORD), ("process_usage", W.DWORD),
                ("base", C.c_void_p), ("size", W.DWORD), ("handle", W.HMODULE),
                ("module", W.WCHAR * 256), ("path", W.WCHAR * 260)]


class WinAPI:
    def __init__(self):
        self.kernel = C.WinDLL("kernel32", use_last_error=True)
        self.user = C.WinDLL("user32", use_last_error=True)
        self.advapi = C.WinDLL("advapi32", use_last_error=True)
        self.ip = C.WinDLL("iphlpapi", use_last_error=True)
        self.kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
        self.kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        for prefix, entry in [("Process32", ProcessEntry), ("Module32", ModuleEntry)]:
            for action in ["FirstW", "NextW"]:
                f = getattr(self.kernel, prefix + action)
                f.argtypes = [W.HANDLE, C.POINTER(entry)]
                f.restype = W.BOOL
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.advapi.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, C.POINTER(W.HANDLE)]
        self.advapi.GetTokenInformation.argtypes = [W.HANDLE, C.c_int, W.LPVOID, W.DWORD, C.POINTER(W.DWORD)]
        self.advapi.GetSidSubAuthorityCount.argtypes = [W.LPVOID]
        self.advapi.GetSidSubAuthorityCount.restype = C.POINTER(C.c_ubyte)
        self.advapi.GetSidSubAuthority.argtypes = [W.LPVOID, W.DWORD]
        self.advapi.GetSidSubAuthority.restype = C.POINTER(W.DWORD)
        self.callback = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        self.user.EnumWindows.argtypes = [self.callback, W.LPARAM]
        self.user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        self.user.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.user.IsWindowVisible.argtypes = [W.HWND]
        self.user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
        for name in ["GetExtendedTcpTable", "GetExtendedUdpTable"]:
            f = getattr(self.ip, name)
            f.argtypes = [W.LPVOID, C.POINTER(W.DWORD), W.BOOL, W.ULONG, C.c_int, W.ULONG]
            f.restype = W.DWORD

    def processes(self):
        result = {}
        snapshot = self.kernel.CreateToolhelp32Snapshot(2, 0)
        if snapshot == C.c_void_p(-1).value:
            raise C.WinError(C.get_last_error())
        try:
            item = ProcessEntry(dwSize=C.sizeof(ProcessEntry))
            more = self.kernel.Process32FirstW(snapshot, C.byref(item))
            while more:
                result[int(item.pid)] = {"pid": int(item.pid), "parent_pid": int(item.ppid), "exe": item.exe, "threads": int(item.threads)}
                more = self.kernel.Process32NextW(snapshot, C.byref(item))
        finally:
            self.kernel.CloseHandle(snapshot)
        return result

    def image(self, pid):
        handle = self.kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return None
        try:
            buffer = C.create_unicode_buffer(32768)
            size = W.DWORD(len(buffer))
            if self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, C.byref(size)):
                return buffer.value
        finally:
            self.kernel.CloseHandle(handle)
        return None

    def modules(self, pid):
        result = []
        snapshot = self.kernel.CreateToolhelp32Snapshot(8 | 16, pid)
        if snapshot == C.c_void_p(-1).value:
            return result
        try:
            item = ModuleEntry(dwSize=C.sizeof(ModuleEntry))
            more = self.kernel.Module32FirstW(snapshot, C.byref(item))
            while more:
                result.append(item.path)
                more = self.kernel.Module32NextW(snapshot, C.byref(item))
        finally:
            self.kernel.CloseHandle(snapshot)
        return result

    def token(self, pid):
        process = self.kernel.OpenProcess(0x1000, False, pid)
        token = W.HANDLE()
        if not process:
            return {"error": C.get_last_error()}
        try:
            if not self.advapi.OpenProcessToken(process, 8, C.byref(token)):
                return {"error": C.get_last_error()}
            size, elevation = W.DWORD(), W.DWORD()
            assert self.advapi.GetTokenInformation(token, 20, C.byref(elevation), C.sizeof(elevation), C.byref(size))
            self.advapi.GetTokenInformation(token, 25, None, 0, C.byref(size))
            buffer = C.create_string_buffer(size.value)
            assert self.advapi.GetTokenInformation(token, 25, buffer, size, C.byref(size))
            sid = C.cast(buffer, C.POINTER(C.c_void_p))[0]
            count = self.advapi.GetSidSubAuthorityCount(sid)[0]
            rid = int(self.advapi.GetSidSubAuthority(sid, count - 1)[0])
            return {"elevated": bool(elevation.value), "integrity_rid": hex(rid), "integrity": {0x1000: "Low", 0x2000: "Medium", 0x3000: "High", 0x4000: "System"}.get(rid, "Other")}
        finally:
            if token:
                self.kernel.CloseHandle(token)
            self.kernel.CloseHandle(process)

    def windows(self, pids):
        result = []

        @self.callback
        def callback(hwnd, _):
            pid = W.DWORD()
            self.user.GetWindowThreadProcessId(hwnd, C.byref(pid))
            if pid.value in pids:
                text, kind = C.create_unicode_buffer(4096), C.create_unicode_buffer(256)
                self.user.GetWindowTextW(hwnd, text, len(text))
                self.user.GetClassNameW(hwnd, kind, len(kind))
                result.append({"handle": int(hwnd), "pid": int(pid.value), "title": text.value, "class": kind.value, "visible": bool(self.user.IsWindowVisible(hwnd))})
            return True

        self.user.EnumWindows(callback, 0)
        return result

    def network(self, pids):
        result = []
        for family, ip_size in [(2, 4), (23, 16)]:
            for protocol in ["TCP", "UDP"]:
                fields = [("local", W.DWORD)] if ip_size == 4 else [("local", C.c_ubyte * 16), ("local_scope", W.DWORD)]
                fields += [("local_port", W.DWORD)]
                if protocol == "TCP":
                    fields += [("remote", W.DWORD)] if ip_size == 4 else [("remote", C.c_ubyte * 16), ("remote_scope", W.DWORD)]
                    fields += [("remote_port", W.DWORD)]
                    if ip_size == 4:
                        fields = [("state", W.DWORD), *fields]
                    else:
                        fields += [("state", W.DWORD)]
                fields += [("pid", W.DWORD)]
                row_type = type("Row", (C.Structure,), {"_fields_": fields})
                f = self.ip.GetExtendedTcpTable if protocol == "TCP" else self.ip.GetExtendedUdpTable
                size = W.DWORD()
                f(None, C.byref(size), False, family, 5 if protocol == "TCP" else 1, 0)
                buffer = C.create_string_buffer(max(4, size.value))
                if f(buffer, C.byref(size), False, family, 5 if protocol == "TCP" else 1, 0):
                    continue
                count = C.cast(buffer, C.POINTER(W.DWORD))[0]
                for i in range(count):
                    row = row_type.from_buffer_copy(buffer.raw, 4 + i * C.sizeof(row_type))
                    if row.pid not in pids:
                        continue
                    local = row.local.to_bytes(4, "little") if ip_size == 4 else bytes(row.local)
                    record = {"pid": int(row.pid), "protocol": protocol, "family": "IPv4" if ip_size == 4 else "IPv6", "local": socket.inet_ntop(socket.AF_INET if ip_size == 4 else socket.AF_INET6, local), "local_port": socket.ntohs(row.local_port & 0xFFFF)}
                    if protocol == "TCP":
                        remote = row.remote.to_bytes(4, "little") if ip_size == 4 else bytes(row.remote)
                        record.update(remote=socket.inet_ntop(socket.AF_INET if ip_size == 4 else socket.AF_INET6, remote), remote_port=socket.ntohs(row.remote_port & 0xFFFF), state=int(row.state))
                    result.append(record)
        return result


def now():
    return datetime.now(timezone.utc).isoformat()


def file_snapshot(roots):
    result = {}
    for name, root in roots.items():
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    with path.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    result[name + "/" + str(path.relative_to(root))] = {"bytes": path.stat().st_size, "sha256": digest}
                except (OSError, PermissionError):
                    result[name + "/" + str(path.relative_to(root))] = {"unreadable": True}
    return result


class Observer:
    def __init__(self, api, root_pid):
        self.api, self.root_pid = api, root_pid
        self.processes, self.modules, self.connections, self.windows = {}, set(), [], {}
        self.errors, self.samples = [], 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                current = self.api.processes()
                selected = {self.root_pid, *self.processes}
                changed = True
                while changed:
                    changed = False
                    for pid, row in current.items():
                        if row["parent_pid"] in selected and pid not in selected:
                            selected.add(pid)
                            changed = True
                for pid in selected & current.keys():
                    row = current[pid]
                    if pid not in self.processes:
                        self.processes[pid] = {**row, "image": self.api.image(pid), "token": self.api.token(pid), "first_seen": now()}
                    self.processes[pid]["last_seen"] = now()
                    self.processes[pid]["max_threads"] = max(row["threads"], self.processes[pid].get("max_threads", 0))
                if self.samples % 10 == 0:
                    for pid in selected & current.keys():
                        self.modules.update(self.api.modules(pid))
                    for row in self.api.windows(selected):
                        self.windows[row["handle"]] = row
                for row in self.api.network(selected):
                    if row not in self.connections:
                        self.connections.append(row)
                self.samples += 1
            except Exception as exc:
                self.errors.append(repr(exc))
                return
            self.stop.wait(0.02)

    def finish(self):
        self.stop.set()
        self.thread.join()
        return {
            "primary_pid": self.root_pid, "sampling_interval_seconds": 0.02,
            "samples": self.samples, "sampling_limit": "May miss transient events; use the accompanying ETW record",
            "process_tree": list(self.processes.values()),
            "child_processes": [r for p, r in self.processes.items() if p != self.root_pid],
            "loaded_modules": sorted(self.modules), "network_endpoints": self.connections,
            "windows": list(self.windows.values()),
            "visible_console_observed": any(r["visible"] and r["class"] == "ConsoleWindowClass" for r in self.windows.values()),
            "observer_errors": self.errors,
        }


def wait_for_window(api, process, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"GUI exited early with code {process.returncode}")
        windows = api.windows({process.pid})
        visible = [w for w in windows if w["visible"] and w["title"].startswith("WrapLab")]
        if visible:
            return visible[0]
        time.sleep(0.05)
    raise TimeoutError("Normal WrapLab GUI did not become visible")
