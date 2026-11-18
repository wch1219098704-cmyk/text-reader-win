# 选中即读 (text-reader-win)

<img src="assets/icon.svg" width="72" align="right">

在**任意 Windows 应用**里选中一段英文，光标旁会浮出一个小喇叭，点一下就朗读出来。
不用复制、不用粘贴、不用切窗口。适合背单词、练听力、读英文文档。

> 本项目重构自 [zskr-at-ladge/text-reader](https://github.com/zskr-at-ladge/text-reader)（MIT）。
> 原版依赖 tkinter 且音源是系统 SAPI（机械音），本版重写了悬浮窗口和发音管线。

## 特性

- **单词用有道词典音**（自然，接近真人），**整句用百度发音**（能读长段落、可调速）
- 断网自动回落 Windows SAPI，不会哑掉
- 图标 26px，不挡内容，点它不会抢走你的文字选区
- 读完自动还原剪贴板，不会污染你复制的东西
- 全局快捷键 `Ctrl + Alt + R`，选中后按下即读
- 右键图标切换：音源 / 英式美式 / 语速
- 纯本地运行，**不需要任何 API Key**

## 快速开始

要求：Windows 10/11，Python 3.8+（官方版或精简版都行，本项目不用 tkinter）

```bash
pip install -r requirements.txt
pythonw text_reader.pyw
```

也可以双击 `start-reader.vbs`（静默启动，不弹黑框，需要 `pythonw` 在 PATH 里）。

启动后托盘会出现喇叭图标；此时选中任意文字，光标右上角就会浮出小喇叭。

开机自启：把 `start-reader.vbs` 的快捷方式放进
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`。

## 用法

| 操作 | 效果 |
|---|---|
| 选中文字 → 点悬浮喇叭 | 朗读；读的时候再点一次即停止 |
| 选中文字 → `Ctrl + Alt + R` | 直接朗读 |
| 右键悬浮喇叭 | 音源 / 口音 / 语速 / 重读 |
| 右键托盘图标 | 同上，另有「朗读剪贴板内容」「退出」 |

## 发音策略

程序按长度自动分流（`tts_engine.py` 的 `_choose_engine`）：

| 选中内容 | 音源 | 原因 |
|---|---|---|
| ≤40 字符、≤6 个词 | 有道词典发音 | 语感最自然；但该接口**只接受 44 字符以内**，超了返回 500 |
| 更长的句子、段落 | 百度翻译发音 | 支持任意长度与中文，可用 `spd` 调速 |
| 断网 / 两者都失败 | 本地 SAPI | 保底能出声，音色机械 |

## 配置

改 `config.json` 后重启程序生效。

```json
{
  "engine": "auto",        // auto | youdao | baidu | sapi
  "accent": 2,             // 1=英音 2=美音（仅影响有道）
  "icon_size": 26,         // 悬浮图标边长(px)，18 以下会糊
  "rate": 0,               // 语速 -10 ~ 10
  "youdao_max_chars": 40,  // 超过此长度不走有道
  "hotkey": "ctrl+alt+r",
  "icon_timeout_ms": 6000, // 图标停留时间
  "restore_clipboard": true,
  "max_chars": 2000        // 单次朗读上限
}
```

音频缓存在 `%TEMP%\text-reader-cache`，同一个词第二次点击直接播放，不走网络。

## 为什么不是「右键菜单里加一项」

做不到，这是硬限制：Electron 应用（VS Code、Discord、本工具的常见宿主）的右键菜单是页面自己绘制的，
不是 Windows 原生菜单，任何桌面工具和 Shell 扩展都塞不进去。只有浏览器扩展（只对网页）能加。
所以做成“选区旁的悬浮按钮”——同样是点一下就出声。

## 已知限制

- 仅 Windows（用到 SAPI / MCI / 分层窗口）
- 单词走有道成品音频，**不能变速**；要慢速练单词请把音源切成百度或 SAPI
- 在终端类窗口（cmd / Windows Terminal / mintty）里不会触发：那里 `Ctrl+C` 是中断信号，
  全局发送会杀掉正在运行的程序，已做白名单跳过
- 在线音源依赖有道/百度的公开接口，若对方调整接口需要更新

## 文件结构

```
text_reader.pyw   主程序：托盘、悬浮图标、鼠标监听、热键、菜单
tts_engine.py     发音：有道/百度抓取、MCI 播放、缓存、SAPI 兜底
win_icon.py       悬浮图标：Pillow 超采样 + UpdateLayeredWindow
win_menu.py       原生右键菜单：TrackPopupMenuEx
config.json       配置
start-reader.vbs  静默启动器
```

## 致谢与许可

- 原始想法与初版：[zskr-at-ladge/text-reader](https://github.com/zskr-at-ladge/text-reader)
- 发音数据来自有道词典、百度翻译的公开接口，仅供个人学习使用

MIT License，见 [LICENSE](LICENSE)。
