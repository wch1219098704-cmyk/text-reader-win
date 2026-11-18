# -*- coding: utf-8 -*-
"""TTS 核心：配置、选音、朗读。

音源优先级（auto）：
  1. 单词/短语（≤40 字符）→ 有道词典发音（自然、接近真人，就是单词点读那个声音）
  2. 整句/段落          → 百度翻译发音（能读长句、可调速）
  3. 全部失败/离线      → Windows SAPI（本地、机械音，兜底不哑）

播放用 winmm MCI，不依赖任何播放器；音频按内容哈希缓存在临时目录，重复点击零等待。
"""
import base64
import hashlib
import json
import os
import queue
import re
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
POWERSHELL = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
CACHE_DIR = os.path.join(tempfile.gettempdir(), "text-reader-cache")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
      "Referer": "https://fanyi.baidu.com/"}

try:
    import comtypes
    import comtypes.client
    HAVE_SAPI = True
except Exception:  # pragma: no cover
    HAVE_SAPI = False

DEFAULT_CONFIG = {
    "engine": "auto",       # auto | youdao | baidu | sapi
    "accent": 2,            # 1=英音 2=美音（仅影响有道）
    "voice_en": "Microsoft Zira Desktop",
    "voice_zh": "Microsoft Huihui Desktop",
    "rate": 0,              # -10 ~ 10（影响百度语速与 SAPI）
    "volume": 100,
    "auto_lang": True,
    "icon_size": 26,        # 悬浮图标边长(px)
    "youdao_max_chars": 40,
    "hotkey": "ctrl+alt+r",
    "icon_timeout_ms": 6000,
    "restore_clipboard": True,
    "max_chars": 2000,
}

_CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_LATIN = re.compile(r"[A-Za-z]")


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f) or {})
    except Exception:
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def is_mostly_chinese(text):
    return len(_CJK.findall(text)) > len(_LATIN.findall(text))


def pick_voice(text, cfg):
    if cfg.get("auto_lang", True) and is_mostly_chinese(text):
        return cfg.get("voice_zh") or "Microsoft Huihui Desktop"
    return cfg.get("voice_en") or "Microsoft Zira Desktop"


# ─── 在线音源 ────────────────────────────────────────────────────────────────
def _youdao_url(text, cfg):
    accent = 1 if int(cfg.get("accent", 2)) == 1 else 2
    return "https://dict.youdao.com/dictvoice?" + urllib.parse.urlencode(
        {"audio": text, "type": accent})


def _baidu_url(text, cfg):
    lang = "zh" if is_mostly_chinese(text) else "en"
    return "https://fanyi.baidu.com/gettts?" + urllib.parse.urlencode(
        {"lan": lang, "text": text, "spd": _rate_to_spd(cfg.get("rate", 0)),
         "source": "web"})


def _rate_to_spd(rate):
    """把 -10..10 的语速映射到百度 spd（实测 1/3 差不多，5、7 明显变快）。"""
    try:
        r = int(rate)
    except Exception:
        r = 0
    if r <= -4:
        return 1
    if r <= 1:
        return 3
    if r <= 4:
        return 5
    return 7


def _is_short_phrase(text, cfg):
    if is_mostly_chinese(text):
        return len(text) <= 12
    return len(text) <= int(cfg.get("youdao_max_chars", 40)) and len(text.split()) <= 6


def _choose_engine(text, cfg):
    eng = str(cfg.get("engine") or "auto").lower()
    if eng in ("sapi", "youdao", "baidu"):
        return eng
    return "youdao" if _is_short_phrase(text, cfg) else "baidu"


def _fetch_once(url, timeout):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        ctype = r.headers.get("Content-Type") or ""
        if "audio" not in ctype:
            return None
        data = r.read()
        return data if len(data) > 1500 else None


def _fetch(url, timeout=8, retries=1):
    for i in range(retries + 1):
        try:
            data = _fetch_once(url, timeout)
            if data:
                return data
        except Exception:
            pass
        if i < retries:
            time.sleep(0.25)
    return None


def _cache_key(text, engine, cfg):
    extra = f"{cfg.get('accent')}|{cfg.get('rate')}"
    return hashlib.md5(f"{engine}|{extra}|{text}".encode("utf-8")).hexdigest()[:20]


def _cache_path(key):
    return os.path.join(CACHE_DIR, key + ".mp3")


def _cache_get(key):
    p = _cache_path(key)
    return p if os.path.exists(p) and os.path.getsize(p) > 1500 else None


def _cache_put(key, data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        p = _cache_path(key)
        with open(p, "wb") as f:
            f.write(data)
        _cache_trim()
        return p
    except Exception:
        return None


def _cache_trim(limit=300):
    try:
        files = [os.path.join(CACHE_DIR, n) for n in os.listdir(CACHE_DIR)]
        if len(files) <= limit:
            return
        files.sort(key=os.path.getmtime)
        for p in files[:len(files) - limit]:
            try:
                os.remove(p)
            except Exception:
                pass
    except Exception:
        pass


def fetch_audio(text, cfg, on_step=None):
    """按引擎策略取音频字节，返回 (bytes, engine) 或 (None, None)。"""
    engine = _choose_engine(text, cfg)
    if engine == "sapi":
        return None, None
    key = _cache_key(text, engine, cfg)
    p = _cache_get(key)
    if p:
        try:
            with open(p, "rb") as f:
                return f.read(), engine
        except Exception:
            pass
    if on_step:
        on_step(engine)
    data = None
    if engine == "youdao":
        data = _fetch(_youdao_url(text, cfg))
        if not data:                      # 超长或异常时退到百度
            data = _fetch(_baidu_url(text, cfg))
            engine = "baidu"
    else:
        data = _fetch(_baidu_url(text, cfg))
        if not data:
            data = _fetch(_youdao_url(text, cfg))
            engine = "youdao"
    return data, engine


# ─── MCI 播放 ────────────────────────────────────────────────────────────────
ALIAS = "trplay"


def _mci(cmd):
    import ctypes
    buf = ctypes.create_unicode_buffer(64)
    err = ctypes.windll.winmm.mciSendStringW(cmd, buf, 64, None)
    return err, buf.value


class _Ctl:
    __slots__ = ("stop",)

    def __init__(self):
        self.stop = threading.Event()


class _OnlineSpeaker:
    def __init__(self):
        self.q = queue.Queue()
        self._cur = None
        self._lock = threading.Lock()
        threading.Thread(target=self._loop, daemon=True).start()

    def say(self, text, cfg, done):
        ctl = _Ctl()
        with self._lock:
            if self._cur:
                self._cur.stop.set()
            self._cur = ctl
        self.q.put((text, cfg, done, ctl))

    def stop(self):
        with self._lock:
            if self._cur:
                self._cur.stop.set()
        _mci(f"stop {ALIAS}")

    def _loop(self):
        while True:
            text, cfg, done, ctl = self.q.get()
            if ctl.stop.is_set():
                done()
                continue
            path = None
            try:
                data, _engine = fetch_audio(text, cfg)
                if data and not ctl.stop.is_set():
                    path = _cache_put(_cache_key(text, _engine, cfg), data)
            except Exception:
                path = None
            if ctl.stop.is_set():
                done()
                continue
            if not path:
                # 离线兜底：SAPI
                if HAVE_SAPI:
                    _get_speaker().say(text, cfg.get("rate", 0), cfg.get("volume", 100),
                                       pick_voice(text, cfg), done)
                    continue
                done()
                continue
            try:
                self._play(path, ctl)
            except Exception:
                pass
            done()

    def _play(self, path, ctl):
        _mci(f"close {ALIAS}")
        err, _ = _mci(f'open "{path}" type mpegvideo alias {ALIAS}')
        if err:
            return
        _mci(f"play {ALIAS}")
        t0 = time.time()
        # 等它真正开始播（避免一上来就 "not ready" 误判结束）
        while time.time() - t0 < 1.0:
            if ctl.stop.is_set():
                break
            _, mode = _mci(f"status {ALIAS} mode")
            if mode.strip() == "playing":
                break
            time.sleep(0.02)
        # 以 MCI 真实状态为准，不用估算时长（低码率 mp3 的 length 不准）
        while True:
            if ctl.stop.is_set():
                break
            _, mode = _mci(f"status {ALIAS} mode")
            if mode.strip() != "playing":
                break
            if time.time() - t0 > 180:
                break
            time.sleep(0.04)
        _mci(f"close {ALIAS}")


# ─── SAPI 本地朗读 ───────────────────────────────────────────────────────────
class _SapiSpeaker:
    def __init__(self):
        self.q = queue.Queue()
        self.voice = None
        self.ready = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()
        self.ready.wait(5)

    def _loop(self):
        try:
            comtypes.CoInitialize()
            self.voice = comtypes.client.CreateObject("SAPI.SpVoice")
        except Exception:
            self.voice = None
            self.ready.set()
            return
        self.ready.set()
        while True:
            kind, payload = self.q.get()
            if kind == "say":
                text, rate, volume, name, done = payload
                try:
                    self._apply(rate, volume, name)
                    self.voice.Speak(text, 1)
                    time.sleep(0.08)
                    while self.voice.Status.RunningState == 2:
                        time.sleep(0.05)
                except Exception:
                    pass
                if done:
                    try:
                        done()
                    except Exception:
                        pass
            elif kind == "stop":
                try:
                    self.voice.Speak("", 2)
                except Exception:
                    pass

    def _apply(self, rate, volume, name):
        try:
            self.voice.Rate = max(-10, min(10, int(rate)))
            self.voice.Volume = max(0, min(100, int(volume)))
        except Exception:
            pass
        if name:
            try:
                voices = self.voice.GetVoices()
                for i in range(voices.Count):
                    item = voices.Item(i)
                    desc = item.GetDescription()
                    if desc == name or desc.startswith(name):
                        self.voice.Voice = item
                        break
            except Exception:
                pass

    def say(self, text, rate, volume, name, done):
        self.q.put(("say", (text, rate, volume, name, done)))

    def stop(self):
        self.q.put(("stop", None))


_speaker = None
_online = None
_lock = threading.Lock()


def _get_speaker():
    global _speaker
    with _lock:
        if _speaker is None:
            _speaker = _SapiSpeaker()
        return _speaker


def _get_online():
    global _online
    with _lock:
        if _online is None:
            _online = _OnlineSpeaker()
        return _online


# ─── 对外接口 ────────────────────────────────────────────────────────────────
def speak(text, cfg=None, on_done=None):
    """朗读一段文本（异步）。"""
    cfg = cfg or load_config()
    if not text or not text.strip():
        return False
    text = text.strip()[:int(cfg.get("max_chars", 2000))]
    if str(cfg.get("engine", "auto")).lower() == "sapi":
        if HAVE_SAPI:
            _get_speaker().say(text, cfg.get("rate", 0), cfg.get("volume", 100),
                               pick_voice(text, cfg), on_done)
            return True
    _get_online().say(text, cfg, on_done or (lambda: None))
    return True


def stop():
    if _online is not None:
        _online.stop()
    if _speaker is not None:
        _speaker.stop()


def warmup():
    """提前建好对象，避免首次点击等初始化。"""
    if HAVE_SAPI:
        try:
            _get_speaker()
        except Exception:
            pass
    _get_online()
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
    except Exception:
        pass


# ─── 自检用 ──────────────────────────────────────────────────────────────────
def _b64(text):
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def synthesize_to_wav(text, out_path, voice=None, rate=0, volume=100):
    voice = voice or DEFAULT_CONFIG["voice_en"]
    b64 = _b64(text)
    vs = voice.replace("'", "''")
    op = out_path.replace("'", "''")
    cmd = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"try{{$s.SelectVoice('{vs}')}}catch{{}};"
        f"$s.Rate={int(rate)};$s.Volume={int(volume)};"
        f"$s.SetOutputToWaveFile('{op}');"
        f"$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}'));"
        "$s.Speak($t);$s.Dispose();"
    )
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd],
        capture_output=True, text=True, timeout=60,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
