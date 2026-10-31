# VexRush

**双通道连点器 · Windows** ｜ [English](README.en.md)

一次装、两路连点：左键右键各一路，可以同时按住、分别设置，不用开两个程序。
点的是"窗口消息"，不动你的鼠标、不抢前台——鼠标可以一边打游戏一边连点。

![主界面](docs/screenshot-main.png)

---

## 快速开始

1. 双击 `VexRush.exe`（绿色版，单个文件，不用安装）。
2. 顶部「目标程序」会自动选中当前在前台的 `java.exe` / `javaw.exe`（也就是 Minecraft）；
   如果是别的程序，从下拉框里选，或者直接手打进程名（如 `msedge.exe`）。
3. 设好间隔 → 打开这一路的开关 → **按住**触发键（默认鼠标左键 / 右键）就开始连点，
   松手立刻停。

所有设置（含窗口位置、两路开关状态）改动后自动保存，关掉再打开还在。

---

## 界面

主界面只有两张卡片，**连点1 / 连点2**，两路完全独立：

| 位置 | 作用 |
| --- | --- |
| 右上角开关 | 这一路的总开关（也可以按快捷键切） |
| 间隔 | 每次点击的间隔，1–2000 ms。15 ms ≈ 66 次/秒，10 ms ≈ 100 次/秒 |
| 触发 | 什么动作触发连点：鼠标左/右/中键，或任意键盘键（选「自定义键盘键」后按一下要用的键） |
| 高级（折叠） | **名称**（可改名，改名会同步到 HUD）、模拟点击的按键、开关热键 |
| 速率（折叠） | 这一路的实时速率曲线、累计次数、当前每秒次数 |

顶栏还有「连点显示」（HUD 开关）和「设置」。

---

## 设置

| 分区 | 内容 |
| --- | --- |
| 外观 | 4 套主题（浅色/深色/暖砂/墨蓝）、6 种强调色 + 自定义取色、4 档界面字号、界面字体、界面语言 |
| 目标程序 | 自动识别（优先选前台里的 java/javaw），后台消息 / 同步消息两种发送方式 |
| 防卡手 | **只允许开一路**：开一路自动关掉另一路，避免两路同时猛点；**关闭后恢复**：关掉当前这路时，把刚被挤掉的那路重新打开（只记最近一次，来回切换也不会恢复错） |
| 输入法 | **暂时下线**（置灰 + 敬请期待）：各家程序对「输入框 / 输入法拼字」的判定差异太大，做不到稳定可靠，所以默认关闭并停用 |
| 悬浮显示 | 打开「连点显示设置」窗口 |
| 配置文件 | 显示真实路径，可打开数据目录、导入 / 导出 / 恢复默认 |

数据目录固定在 **`%APPDATA%\VexRush`**（`config.json` 和 `lang\` 都在这里）。
如果 exe 旁边有旧的 `config.json`，第一次启动会搬过去。

---

## 连点显示（HUD）

给录制 / 直播看的小面板：无边框、置顶、可点击穿透，显示每路的状态、速率、次数、间隔。

![HUD 设置](docs/screenshot-hud-settings.png)

- **排布**：竖排 / 横排；**标题文字**可关、内容可自定义。
- **显示内容**：状态 / 速率 / 次数 / 间隔，逐项开关。
- **入场 / 出场动画**：淡入、缩放、滑入、弹簧、柔焦、无；帧率跟随显示器刷新率（本机 120 Hz → 8 ms 一帧，最高按 144 Hz 处理）。
- **拖动**：按下才跟手，指针插值缓动（可关、可调跟手强度）；松手会**先对齐到指针位置**，只有真正快速"甩"出去才会滑一小段，且**最多 16 px**，绝不会溜出屏幕。
- **外观**：字号、背景不透明度（只管底板）、整体不透明度（连文字一起淡）、未开启时的淡化、圆角、内边距、行间距、底色、文字色、强调色（跟随主题 / 按通道自动配色 / 自定义）、彩虹流光及其速度。
- 右键菜单可以快速锁定位置、点击穿透、逐项开关内容、试播动画、打开设置、关闭显示。
- 「**试播动画**」按钮会把入场动画再演一遍，方便调参。

---

## 语言包

界面语言是**数据**不是代码，`%APPDATA%\VexRush\lang\` 里放 json 就能加：

```json
{
  "_name": "Deutsch",
  "interval": "Intervall",
  "click": "Klick %d"
}
```

- 键是固定的语义 ID —— 复制 `example.json`，键别动，只翻值。
- `_name` 是语言列表里显示的名字。
- `%d` / `%s` / `%0.1f` 这类占位符要保留；`%%` 是百分号本身。
- 缺键会回退到内置简体中文，再回退到键名本身。
- 自己加的包在列表里会标「非官方」，内置的两套不会。

---

## 没反应怎么办

1. **目标对不对**：顶部右侧会显示「进程名 · 窗口标题」，确认是你要点的那个窗口。
2. **权限**：目标程序以管理员身份运行时，VexRush 也要用管理员身份运行，否则消息会被系统拦掉（UIPI）。
3. **这类程序本来就不吃窗口消息**：少数用 DirectInput / Raw Input 读输入的游戏或工具，不会理会进程外投递的鼠标消息。这时换「同步消息 SendMessage」偶尔能救，但多数情况是无效的。
4. **热键没反应**：热键默认 `x` 和 `r`。热键是双通道注册（低级键盘钩子 + 系统 `RegisterHotKey`），一般情况在其他程序聚焦时也能触发；如果某个游戏全屏并且独占了键盘，可能仍然收不到。
5. **本窗口在最前面时不会往外点**：这是故意的，防止你在界面上点按钮时误点进游戏。

---

## 已知限制

- 窗口消息点击天然不兼容所有程序（DirectInput / Raw Input 见上）。
- 目标以管理员运行时必须同样提权。
- 「打字时不响应」暂时下线（原因见上）。
- 只支持 Windows 10 / 11（x64）。

---

# 开发者部分（Developer notes）

## 环境与运行

```bat
pip install PyQt5 pywin32 pynput psutil pyinstaller
python main.py                 :: 直接跑源码
python main.py --multi         :: 跳过单实例限制（测试用）
```

高 DPI：`AA_EnableHighDpiScaling` + `AA_UseHighDpiPixmaps` + `PassThrough` 缩放策略，175% 下验证过。

## 打包

```bat
python -m PyInstaller --noconfirm --clean dual_clicker.spec
:: -> dist\VexRush.exe  (onefile, 无控制台, 带图标/版本信息, 内嵌 assets\fonts 与 assets\lang)
```

打包前记得关掉残留的 `dist\VexRush.exe` 进程，否则会 `PermissionError: [WinError 5]`。

## 测试

三套都在 Windows 上跑真实窗口与真实输入，都会把 `APPDATA` 指到临时目录，不碰你的真实配置：

```bat
python tests\selftest.py     :: 配置/主题/i18n/HUD 几何与拖动/消息投递
python tests\e2e_test.py     :: 真按住 F19 打靶子窗口、字母热键切换、真实鼠标、前台保护
python tests\exe_check.py    :: 打包 exe：高 DPI、配置落盘、重启还原（可传 exe 路径）
```

测试小贴士：

- 拖动/动画类测试要用**干净的临时 APPDATA**，否则会读到旧窗口 geometry 导致假失败。
- e2e 里防卡手必须关掉（`cfg.exclusive = False`），它测的是两路互不影响。
- `exe_check` 会顺手删 `dist\config.json`：残留的便携配置会被启动时搬进数据目录，把窗口尺寸带跑。

## 目录结构

```
main.py                  入口：高 DPI、单实例、QApplication、字体与语言
app/
  config.py              dataclass 配置、原子保存、v1→v2 迁移、数据目录/语言目录
  engine.py              pynput 输入中心、目标窗口注册表、连点线程、通道
  winapi.py              屏幕/刷新率/输入法查询、窗口消息点击、热键注册
  theme.py               设计令牌、QSS 与调色板生成、自定义强调色
  widgets.py             自绘控件（开关、数字框、分段选择、迷你折线…）
  mainwindow.py          主窗口：目标栏、卡片、页脚与各处接线
  channel_card.py        单路卡片（间隔/触发/高级/速率）
  window_drag.py         Win32 侧：标题栏拖动接管、热键注册、自动高度
  switcher.py            换主题时的模糊幕布（盖住重建卡顿）
  overlay.py             HUD：绘制、布局、拖动、位置
  overlay_anim.py        HUD 入场/出场动画与缓动曲线
  overlay_menu.py        HUD 右键菜单（自绘圆角深色菜单）
  overlay_settings.py    HUD 设置窗口
  settings.py            主设置窗口
  dialogbase.py          设置窗口骨架（页头 / 滚动区 / 页脚、网格行）
  fonts.py               内置字体加载 + 系统字体列表
  i18n.py                JSON 语言包：内置 assets/lang + 用户 lang\
  icon.py                程序图标（代码生成）
  screen.py              显示器几何（把点/窗口夹回可见区域）
  textfmt.py             数字与文本格式化
  debug.py               按需日志（环境变量 VEXRUSH_DEBUG=<路径>）
assets/fonts/            ChillRoundM.otf + OFL 许可全文
assets/lang/             zh_cn.json, en_us.json, example.json
tests/, tools/           测试与开发工具（preview.py 离屏渲染、make_icon.py 生成 .ico）
docs/                    README 用截图
```

## 几个必须知道的坑

1. **排程用 `time.perf_counter()`，不能用 `time.monotonic()`**。后者在 Windows 上来自 `GetTickCount64`，粒度 15.6 ms，所有 ≤15 ms 的间隔会被压成 16 ms —— 设 10 ms 只有 65 次/秒。
2. **`WM_MOVING` / `WM_SIZING` 的 lParam RECT 是物理像素**，Qt 的 geometry 是逻辑像素。175% 缩放下混用就是"抽搐"。现在拖动完全不进系统模态循环：自己 `SetCapture` + 每帧 `SetWindowPos` 缓动。
3. **PyQt5 在槽函数里抛未捕获异常会直接 abort 进程**。定时器/输入回调要做薄壳 + `try/except`，否则一个 `NameError` 就是"卡爆并崩溃"。
4. **`QFontDatabase` / `QFontMetrics` 必须晚于 `QApplication`**，否则打包版会在启动时 access violation（0xC0000005），而且没有 stderr。定位靠 `faulthandler.enable(file=...)` 的探针入口。
5. **拆分模块时最容易漏搬模块级常量**（`NameError` 只在真正走那条路径时才炸）。提交前可以跑一遍 AST 的「用了但没定义」扫描。
6. **测试里的窗口位置要留在虚拟屏内**（离屏平台是 768×576），否则 `clamp_point` 会把窗口拉回边界，测出来的位移是假的。
7. 全局 git 有 `gh-proxy.com` 的 URL 改写，push 前要么临时移除该配置段，要么用能直连的地址。

## 提交与发布约定

- commit message 第一行说清版本与主旨，正文分「修复 / 新增 / 移除」三段。
- 发布前：三套测试全绿 → 升 `APP_VERSION` 与 `version_info.txt` 里的四个版本字段（元组和字符串都要改）→ 重新打包 → `exe_check`。
- 产物只放在 `dist\`，不要往桌面或仓库里塞 exe。

## 许可

程序本体 MIT，见 `LICENSE`。

内置字体 **ChillRoundM（寒蝉半圆体）** 来自 [Warren2060/ChillRound](https://github.com/Warren2060/ChillRound)，
采用 SIL Open Font License 1.1，许可全文随字体放在 `assets/fonts/LICENSE-ChillRound.txt`。
按其要求保留字体名 `ChillRoundF` / `ChillRoundM` 不变；**该字体不在上面的 MIT 许可范围内**。
