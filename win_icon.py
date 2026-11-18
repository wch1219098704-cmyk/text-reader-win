# -*- coding: utf-8 -*-
"""Win32 原生悬浮图标。

- Pillow 4 倍超采样渲染，缩小后边缘平滑
- UpdateLayeredWindow 逐像素透明，圆角自然、点击不抢焦点
- 左键朗读/停止；右键设置菜单；悬停高亮；自动隐藏
"""
import ctypes
from ctypes import wintypes as wt
import collections

from PIL import Image, ImageDraw

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)

WM_PAINT = 0x000F
WM_ERASEBKGND = 0x0014
WM_TIMER = 0x0113
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_MOUSELEAVE = 0x02A3
WM_APP_SHOW = 0x8001
WM_APP_TASK = 0x8002

WS_POPUP = 0x80000000
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_NOACTIVATE = 0x08000000

SW_SHOWNOACTIVATE = 4
SW_HIDE = 0
HWND_TOPMOST = -1
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

STATE_IDLE = "idle"
STATE_HOVER = "hover"
STATE_SPEAKING = "speaking"


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wt.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE),
        ("hIcon", wt.HICON),
        ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HANDLE),
        ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR),
    ]


class TRACKMOUSEEVENT(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("dwFlags", wt.DWORD),
                ("hwndTrack", wt.HWND), ("dwHoverTime", wt.DWORD)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wt.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wt.WORD),
                ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
                ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
                ("biClrImportant", wt.DWORD)]


user32.DefWindowProcW.restype = LRESULT
user32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.CreateWindowExW.restype = wt.HWND
user32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPVOID]
user32.RegisterClassW.restype = wt.ATOM
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wt.UINT]
user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
user32.SetTimer.restype = ctypes.c_size_t
user32.SetTimer.argtypes = [wt.HWND, ctypes.c_size_t, wt.UINT, wt.LPVOID]
user32.KillTimer.argtypes = [wt.HWND, ctypes.c_size_t]
user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, wt.UINT, wt.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
user32.DispatchMessageW.restype = LRESULT
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
user32.TrackMouseEvent.argtypes = [ctypes.POINTER(TRACKMOUSEEVENT)]
user32.GetCursorPos.argtypes = [ctypes.POINTER(wt.POINT)]
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetDC.restype = wt.HDC
user32.GetDC.argtypes = [wt.HWND]
user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
user32.UpdateLayeredWindow.restype = wt.BOOL
user32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC, ctypes.POINTER(wt.POINT),
                                       ctypes.POINTER(wt.SIZE), wt.HDC,
                                       ctypes.POINTER(wt.POINT), wt.DWORD,
                                       ctypes.POINTER(BLENDFUNCTION), wt.DWORD]

gdi32.CreateCompatibleDC.restype = wt.HDC
gdi32.CreateCompatibleDC.argtypes = [wt.HDC]
gdi32.CreateDIBSection.restype = wt.HANDLE
gdi32.CreateDIBSection.argtypes = [wt.HDC, ctypes.POINTER(BITMAPINFOHEADER), wt.UINT,
                                   ctypes.POINTER(ctypes.c_void_p), wt.HANDLE, wt.DWORD]
gdi32.SelectObject.restype = wt.HANDLE
gdi32.SelectObject.argtypes = [wt.HDC, wt.HANDLE]
gdi32.DeleteObject.argtypes = [wt.HANDLE]


# ─── 图标绘制（Pillow 4 倍超采样） ───────────────────────────────────────────
SIZE = 26          # 默认边长（26px ≈ 原 56px 的 1/5 面积）
DESIGN_SIZE = 56   # 设计稿坐标系，绘制按此比例缩放
SS = 4
BG = (26, 26, 42, 255)
BG_HOVER = (44, 44, 66, 255)
WHITE = (244, 244, 250, 255)
ACCENT = (85, 204, 255, 255)


def render_icon(state, size=None):
    size = int(size or SIZE)
    S = size * SS
    f = S / float(DESIGN_SIZE)     # 设计坐标 -> 实际像素
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    fill = BG_HOVER if state == STATE_HOVER else BG
    radius = int(S * 0.26)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=radius, fill=fill)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=radius,
                        outline=(255, 255, 255, 30), width=max(1, int(f)))

    color = ACCENT if state == STATE_SPEAKING else WHITE

    def p(x, y):
        return (x * f, y * f)

    if size <= 30:
        # 小尺寸简化字形：单道声波 + 加粗 + 减少留白，保证还能看出是喇叭
        d.polygon([p(8, 22), p(17, 22), p(28, 11), p(28, 45), p(17, 34), p(8, 34)],
                  fill=color)
        d.rounded_rectangle([4 * f, 20 * f, 9 * f, 36 * f],
                            radius=max(1, int(1.2 * f)), fill=color)
        d.arc([26 * f, 12 * f, 46 * f, 44 * f], start=-50, end=50,
              fill=color, width=max(2, int(3.2 * f)))
    else:
        d.polygon([p(10, 23), p(19, 23), p(29, 12), p(29, 44), p(19, 33), p(10, 33)],
                  fill=color)
        d.rounded_rectangle([5 * f, 21 * f, 11 * f, 35 * f],
                            radius=max(1, int(1 * f)), fill=color)
        lw = max(1, int(2.4 * f))
        d.arc([27 * f, 14 * f, 43 * f, 42 * f], start=-52, end=52, fill=color, width=lw)
        d.arc([32 * f, 8 * f, 52 * f, 48 * f], start=-46, end=46, fill=color, width=lw)

    return img.resize((size, size), Image.LANCZOS)


class PopupIcon:
    def __init__(self, on_left, on_right, size=None):
        self.size = int(size or SIZE)
        self.on_left = on_left
        self.on_right = on_right
        self.hwnd = None
        self.visible = False
        self.speaking = False
        self.hover = False
        self.timeout_ms = 6000
        self._pos = (0, 0)
        self._wndproc = WNDPROC(self._proc)
        self._bitmaps = {}
        self._hdc_mem = None
        self._dib = None
        self._bits = None
        self._tasks = collections.deque()

    def post(self, fn):
        """从任意线程安全地安排一个函数到窗口线程执行。"""
        self._tasks.append(fn)
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP_TASK, 0, 0)

    def _proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_MOUSEMOVE:
            if not self.hover:
                self.hover = True
                self._refresh()
                tme = TRACKMOUSEEVENT(ctypes.sizeof(TRACKMOUSEEVENT), 0x00000002, hwnd, 0)
                user32.TrackMouseEvent(ctypes.byref(tme))
            return 0
        if msg == WM_MOUSELEAVE:
            self.hover = False
            self._refresh()
            return 0
        if msg == WM_LBUTTONDOWN:
            self.on_left()
            return 0
        if msg == WM_RBUTTONDOWN:
            self.on_right(hwnd)
            return 0
        if msg == WM_TIMER:
            if not self.speaking and not self.hover:
                self.hide()
            return 0
        if msg == WM_APP_SHOW:
            self._do_show()
            return 0
        if msg == WM_APP_TASK:
            while self._tasks:
                try:
                    self._tasks.popleft()()
                except Exception:
                    pass
            return 0
        if msg == WM_ERASEBKGND or msg == WM_PAINT:
            return 1
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    # ── 位图 ──
    def _state(self):
        if self.speaking:
            return STATE_SPEAKING
        return STATE_HOVER if self.hover else STATE_IDLE

    def _push_bitmap(self):
        if not self.hwnd:
            return
        state = self._state()
        img = self._bitmaps.get(state)
        if img is None:
            img = render_icon(state, self.size)
            self._bitmaps[state] = img

        prem = bytearray(self.size * self.size * 4)
        px = img.tobytes()
        for i in range(0, len(px), 4):
            a = px[i + 3]
            if a == 255:
                prem[i:i + 4] = px[i:i + 4]
            elif a:
                prem[i] = px[i] * a // 255
                prem[i + 1] = px[i + 1] * a // 255
                prem[i + 2] = px[i + 2] * a // 255
                prem[i + 3] = a

        hdc_screen = user32.GetDC(None)
        try:
            if self._dib is None:
                bmi = BITMAPINFOHEADER()
                bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
                bmi.biWidth = self.size
                bmi.biHeight = -self.size
                bmi.biPlanes = 1
                bmi.biBitCount = 32
                bits = ctypes.c_void_p()
                self._hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
                self._dib = gdi32.CreateDIBSection(
                    self._hdc_mem, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
                self._bits = bits
                gdi32.SelectObject(self._hdc_mem, self._dib)
            ctypes.memmove(self._bits, bytes(prem), len(prem))

            blend = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
            pt_dst = wt.POINT(self._pos[0], self._pos[1])
            size = wt.SIZE(self.size, self.size)
            pt_src = wt.POINT(0, 0)
            user32.UpdateLayeredWindow(self.hwnd, hdc_screen, ctypes.byref(pt_dst),
                                       ctypes.byref(size), self._hdc_mem,
                                       ctypes.byref(pt_src), 0, ctypes.byref(blend),
                                       ULW_ALPHA)
        finally:
            user32.ReleaseDC(None, hdc_screen)

    def _refresh(self):
        self._push_bitmap()

    def create(self):
        hinst = kernel32.GetModuleHandleW(None)
        cls = WNDCLASSW()
        cls.style = 0x0008
        cls.lpfnWndProc = self._wndproc
        cls.hInstance = hinst
        cls.hCursor = user32.LoadCursorW(None, wt.LPCWSTR(32649))  # IDC_HAND
        cls.hbrBackground = None
        cls.lpszClassName = "TextReaderFloatIcon"
        atom = user32.RegisterClassW(ctypes.byref(cls))
        if not atom and ctypes.get_last_error() != 1410:
            raise OSError(f"RegisterClass 失败: {ctypes.get_last_error()}")
        self.hwnd = user32.CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_TOOLWINDOW | WS_EX_LAYERED | WS_EX_NOACTIVATE,
            "TextReaderFloatIcon", "TextReaderIcon", WS_POPUP,
            -2000, -2000, self.size, self.size, None, None, hinst, None)
        if not self.hwnd:
            raise OSError(f"CreateWindow 失败: {ctypes.get_last_error()}")

    def show(self, x, y):
        self._pos = (int(x), int(y))
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_APP_SHOW, 0, 0)

    def _do_show(self):
        x, y = self._pos
        sw = user32.GetSystemMetrics(0)
        px = min(x + 18, sw - self.size - 6)
        py = max(y - self.size - 20, 6)
        self._pos = (px, py)
        self.hover = False
        self._push_bitmap()
        user32.ShowWindow(self.hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(self.hwnd, HWND_TOPMOST, px, py, 0, 0,
                            SWP_NOSIZE | SWP_NOACTIVATE)
        self.visible = True
        self._start_timer()

    def _start_timer(self):
        if self.hwnd:
            user32.SetTimer(self.hwnd, 1, int(self.timeout_ms), None)

    def restart_timer(self, ms):
        if self.hwnd:
            old, self.timeout_ms = self.timeout_ms, int(ms)
            self._start_timer()
            self.timeout_ms = old

    def hide(self):
        if self.hwnd:
            user32.KillTimer(self.hwnd, 1)
            user32.ShowWindow(self.hwnd, SW_HIDE)
        self.visible = False
        self.speaking = False

    def set_speaking(self, speaking):
        self.speaking = speaking
        if speaking and self.hwnd:
            user32.KillTimer(self.hwnd, 1)
        self._refresh()

    def bounds(self):
        if not self.hwnd:
            return None
        r = wt.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(r))
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def message_loop(self):
        msg = wt.MSG()
        while True:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
