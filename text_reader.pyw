# -*- coding: utf-8 -*-
"""文本朗读助手 v2（WorkBuddy 适配版）

流程：选中文字 → 松开鼠标 → 光标旁浮出小扬声器 → 单击朗读 / 再单击停止。
音源：单词走有道词典音，整句走百度发音，离线兜底 SAPI。
不依赖 tkinter；不残留剪贴板。
"""
import ctypes
import os
import threading
import time

import keyboard
import pyperclip

import tts_engine as tts
from win_icon import PopupIcon
import win_menu

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_PATH = os.path.join(BASE_DIR, "debug.log")

cfg = tts.load_config()
state = {"icon": None, "proc": None, "last_grab": 0.0, "text": ""}

VOICES = [
    ("Microsoft Zira Desktop", "Zira 美音·女"),
    ("Microsoft David Desktop", "David 美音·男"),
    ("Microsoft Huihui Desktop", "Huihui 中文·女"),
]
ENGINES = [
    ("auto", "自动（单词有道 / 整句百度）"),
    ("youdao", "有道词典音（自然）"),
    ("baidu", "百度发音（可读长句）"),
    ("sapi", "离线 SAPI（机械音）"),
]
ACCENTS = [(2, "美音"), (1, "英音")]
RATES = [(-4, "很慢 -4"), (-2, "慢 -2"), (0, "正常 0"), (2, "快 2"), (4, "很快 4")]


def log(msg):
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass


# ─── 朗读控制 ────────────────────────────────────────────────────────────────
def stop_speaking():
    tts.stop()


def start_speaking(text, on_done=None):
    if not text:
        return
    tts.stop()
    icon = state["icon"]
    if icon:
        icon.set_speaking(True)

    def _finish():
        if icon:
            icon.post(lambda: (icon.set_speaking(False), icon.restart_timer(1200)))
        if on_done:
            try:
                on_done()
            except Exception:
                pass

    tts.speak(text, cfg, _finish)


def toggle():
    icon = state["icon"]
    if icon and icon.speaking:
        stop_speaking()
        icon.set_speaking(False)
        icon.restart_timer(1200)
        return
    if state["text"]:
        start_speaking(state["text"])


# 这些窗口里 Ctrl+C 是"中断"而非"复制"，绝不能碰
_NO_CTRL_C_CLASSES = {
    "ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS", "mintty",
    "Cygwin", "PuTTY", "KiTTY", "Vim", "Emacs",
}


def _foreground_class():
    u = ctypes.windll.user32
    hwnd = u.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    u.GetClassNameW(hwnd, buf, 256)
    return buf.value


def grab_selection():
    """模拟 Ctrl+C 取选中文字，并把原剪贴板内容还原回去。"""
    cls = _foreground_class()
    if cls in _NO_CTRL_C_CLASSES:
        log(f"skip ctrl+c in {cls}")
        return None
    try:
        old = pyperclip.paste() or ""
    except Exception:
        old = ""
    try:
        keyboard.send("ctrl+c")
    except Exception as e:
        log(f"ctrl+c 失败: {e}")
        return None
    time.sleep(0.12)
    try:
        new = pyperclip.paste() or ""
    except Exception:
        return None
    if not new.strip() or new == old:
        return None
    if cfg.get("restore_clipboard", True) and old:

        def _restore():
            time.sleep(0.3)
            try:
                pyperclip.copy(old)
            except Exception:
                pass

        threading.Thread(target=_restore, daemon=True).start()
    return new.strip()


# ─── 设置 ────────────────────────────────────────────────────────────────────
def set_voice(name):
    if "Huihui" in name:
        cfg["voice_zh"] = name
    else:
        cfg["voice_en"] = name
    tts.save_config(cfg)
    log(f"voice -> {name}")


def set_engine(key):
    cfg["engine"] = key
    tts.save_config(cfg)
    log(f"engine -> {key}")


def set_accent(value):
    cfg["accent"] = int(value)
    tts.save_config(cfg)
    log(f"accent -> {value}")


def set_rate(value):
    cfg["rate"] = int(value)
    tts.save_config(cfg)
    log(f"rate -> {value}")


def build_menu_items():
    def sub(label, items):
        return {"type": "sub", "label": label, "items": items}

    engine_items = [{"id": f"engine:{k}", "label": lab, "type": "item",
                     "checked": str(cfg.get("engine", "auto")) == k}
                    for k, lab in ENGINES]
    accent_items = [{"id": f"accent:{v}", "label": lab, "type": "item",
                     "checked": int(cfg.get("accent", 2)) == v}
                    for v, lab in ACCENTS]
    rate_items = [{"id": f"rate:{v}", "label": lab, "type": "item",
                   "checked": int(cfg.get("rate", 0)) == v}
                  for v, lab in RATES]

    return [
        {"id": "reread", "label": "重读一次", "type": "item"},
        {"type": "sep"},
        sub("音源", engine_items),
        sub("口音（有道音）", accent_items),
        sub("语速", rate_items),
        {"type": "sep"},
        {"id": "close", "label": "关闭图标", "type": "item"},
    ]


def on_menu(hwnd):
    icon = state["icon"]
    import ctypes.wintypes as wt
    p = wt.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
    choice = win_menu.show_menu(hwnd, p.x, p.y, build_menu_items())
    if not choice:
        return
    if choice == "reread":
        start_speaking(state["text"])
    elif choice == "close":
        icon.hide()
    elif choice.startswith("engine:"):
        set_engine(choice.split(":", 1)[1])
        start_speaking(state["text"])
    elif choice.startswith("accent:"):
        set_accent(choice.split(":", 1)[1])
        start_speaking(state["text"])
    elif choice.startswith("rate:"):
        set_rate(choice.split(":", 1)[1])
        start_speaking(state["text"])
    elif choice.startswith("voice:"):
        set_voice(choice.split(":", 1)[1])
        start_speaking(state["text"])


# ─── 托盘 ────────────────────────────────────────────────────────────────────
def start_tray():
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        log("托盘不可用（缺少 pystray/Pillow）")
        return

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(10, 26), (22, 26), (34, 14), (34, 50), (22, 38), (10, 38)],
              fill=(240, 240, 245, 255))
    d.rectangle([6, 24, 11, 40], fill=(240, 240, 245, 255))
    d.arc([32, 16, 50, 48], start=-55, end=55, fill=(85, 204, 255, 255), width=4)
    d.arc([38, 10, 62, 54], start=-50, end=50, fill=(85, 204, 255, 255), width=4)

    def engine_item(key, label):
        return pystray.MenuItem(
            label, lambda: set_engine(key),
            checked=lambda item, k=key: str(cfg.get("engine", "auto")) == k, radio=True)

    def accent_item(value, label):
        return pystray.MenuItem(
            label, lambda: set_accent(value),
            checked=lambda item, v=value: int(cfg.get("accent", 2)) == v, radio=True)

    def rate_item(value, label):
        return pystray.MenuItem(
            label, lambda: set_rate(value),
            checked=lambda item, v=value: int(cfg.get("rate", 0)) == v, radio=True)

    menu = pystray.Menu(
        pystray.MenuItem("文本朗读助手 · 运行中", None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("朗读剪贴板内容", lambda: read_clipboard_and_speak()),
        pystray.MenuItem("音源", pystray.Menu(*[engine_item(k, l) for k, l in ENGINES])),
        pystray.MenuItem("口音（有道音）", pystray.Menu(*[accent_item(v, l) for v, l in ACCENTS])),
        pystray.MenuItem("语速", pystray.Menu(*[rate_item(v, l) for v, l in RATES])),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"快捷键 {cfg.get('hotkey')}：先选中文字", None, enabled=False),
        pystray.MenuItem("退出", on_exit),
    )
    pystray.Icon("text_reader", img, "文本朗读助手", menu).run()


def read_clipboard_and_speak():
    try:
        text = (pyperclip.paste() or "").strip()
    except Exception:
        return
    if text:
        start_speaking(text)


def on_exit(icon=None, item=None):
    try:
        if icon:
            icon.stop()
    except Exception:
        pass
    stop_speaking()
    os._exit(0)


# ─── 鼠标监听 ────────────────────────────────────────────────────────────────
def on_mouse_up(x, y):
    now = time.time()
    if now - state["last_grab"] < 0.25:
        return
    state["last_grab"] = now

    icon = state["icon"]
    if icon and icon.visible:
        b = icon.bounds()
        if b and b[0] <= x <= b[0] + b[2] and b[1] <= y <= b[1] + b[3]:
            return
        if icon.speaking:
            return

    text = grab_selection()
    if not text:
        return
    state["text"] = text
    if icon:
        icon.show(x, y)


def mouse_watcher():
    LEFT = 0x01
    was_down = False
    while True:
        down = bool(ctypes.windll.user32.GetAsyncKeyState(LEFT) & 0x8000)
        if was_down and not down:
            p = ctypes.wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(p))
            threading.Thread(target=on_mouse_up, args=(p.x, p.y), daemon=True).start()
        was_down = down
        time.sleep(0.04)


def main():
    # 单实例：已经有一个在跑就安静退出
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\TextReaderAssistantV2")
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        return

    tts.save_config(cfg)
    icon = PopupIcon(on_left=toggle, on_right=on_menu,
                     size=int(cfg.get("icon_size", 26)))
    icon.timeout_ms = int(cfg.get("icon_timeout_ms", 6000))
    state["icon"] = icon
    icon.create()

    threading.Thread(target=start_tray, daemon=True).start()
    threading.Thread(target=mouse_watcher, daemon=True).start()

    hotkey = cfg.get("hotkey")
    if hotkey:
        try:
            keyboard.add_hotkey(hotkey, lambda: threading.Thread(
                target=lambda: (lambda t: (state.__setitem__("text", t),
                                           start_speaking(t)) if t else None)(
                    grab_selection()), daemon=True).start())
            log(f"hotkey {hotkey} ok")
        except Exception as e:
            log(f"hotkey fail: {e}")

    log(f"started pid={os.getpid()}")
    tts.warmup()
    icon.message_loop()


if __name__ == "__main__":
    main()
