# -*- coding: utf-8 -*-
"""Win32 原生弹出菜单（替代 tkinter.Menu）。"""
import ctypes
from ctypes import wintypes as wt

user32 = ctypes.WinDLL("user32", use_last_error=True)

MF_STRING = 0x0000
MF_POPUP = 0x0010
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008
MF_GRAYED = 0x0001
MF_RADIOCHECK = 0x0200
MF_UNCHECKED = 0x0000

TPM_LEFTALIGN = 0x0000
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002
TPM_NONOTIFY = 0x0080

user32.CreatePopupMenu.restype = wt.HMENU
user32.CreatePopupMenu.argtypes = []
user32.AppendMenuW.argtypes = [wt.HMENU, wt.UINT, ctypes.c_size_t, wt.LPCWSTR]
user32.AppendMenuW.restype = wt.BOOL
user32.DestroyMenu.argtypes = [wt.HMENU]
user32.TrackPopupMenuEx.restype = wt.UINT
user32.TrackPopupMenuEx.argtypes = [wt.HMENU, wt.UINT, ctypes.c_int,
                                    ctypes.c_int, wt.HWND, wt.LPVOID]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.SetForegroundWindow.argtypes = [wt.HWND]
user32.SetForegroundWindow.restype = wt.BOOL
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.AttachThreadInput.restype = wt.BOOL
user32.AttachThreadInput.argtypes = [wt.DWORD, wt.DWORD, wt.BOOL]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
kernel32 = ctypes.WinDLL("kernel32")
kernel32.GetCurrentThreadId.restype = wt.DWORD


def _build(items, hmenu, idmap):
    for it in items:
        if it.get("type") == "sep":
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            continue
        if it.get("type") == "sub":
            sub = user32.CreatePopupMenu()
            _build(it["items"], sub, idmap)
            user32.AppendMenuW(hmenu, MF_POPUP, int(sub), it["label"])
            continue
        flags = MF_STRING
        if it.get("checked"):
            flags |= MF_CHECKED | MF_RADIOCHECK
        if not it.get("enabled", True):
            flags |= MF_GRAYED
        idmap[int(sub_id(it))] = it["id"]
        user32.AppendMenuW(hmenu, flags, int(sub_id(it)), it["label"])


_counter = [1000]


def sub_id(item):
    if "_mid" not in item:
        _counter[0] += 1
        item["_mid"] = _counter[0]
    return item["_mid"]


def show_menu(hwnd, x, y, items):
    """弹出菜单，返回被点击项的 id（未选择返回 None）。"""
    hmenu = user32.CreatePopupMenu()
    idmap = {}
    fg = user32.GetForegroundWindow()
    my_tid = kernel32.GetCurrentThreadId()
    pid = wt.DWORD()
    fg_tid = user32.GetWindowThreadProcessId(fg, ctypes.byref(pid)) if fg else 0
    attached = False
    try:
        _build(items, hmenu, idmap)
        # 悬浮窗是 NOACTIVATE 的，必须临时借前台线程的输入队列才能正常弹菜单
        if fg_tid and fg_tid != my_tid:
            attached = bool(user32.AttachThreadInput(my_tid, fg_tid, True))
        user32.SetForegroundWindow(hwnd)
        pt = wt.POINT(x, y)
        cmd = user32.TrackPopupMenuEx(
            hmenu, TPM_LEFTALIGN | TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
            pt.x, pt.y, hwnd, None)
        user32.PostMessageW(hwnd, 0, 0, 0)  # 让菜单正常消失
    finally:
        if attached:
            user32.AttachThreadInput(my_tid, fg_tid, False)
        user32.DestroyMenu(hmenu)
    return idmap.get(int(cmd)) if cmd else None
