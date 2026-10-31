# -*- coding: utf-8 -*-
"""打 v3.1.0 的 release 并上传 exe（令牌从 %TEMP%\\_gh_tok2.txt 读，绝不打印）。"""
import io
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = io.open(os.path.join(os.environ["TEMP"], "_gh_tok2.txt"), encoding="ascii").read().strip()
OWNER = "Yelastforbilibili"
REPO = "VexRush"
TAG = "v3.1.0"
EXE = os.path.join(ROOT, "dist", "VexRush.exe")

BODY = """## VexRush 3.1.0

### 中文
- **数据目录**：配置与语言包统一放在 `%APPDATA%\\VexRush`，设置里有「打开数据目录」按钮；旧的便携 `config.json` 首次启动自动迁移。
- **语言包**：界面文案改为 `lang\\*.json`（语义键），首次运行自动释放 `zh_cn.json` / `en_us.json` / `example.json`；自己丢一份翻译进去就能在语言列表里选，标为「非官方」。
- **窗口缓动**：拖动标题栏或边框时窗口平滑跟随，松手后高度自动贴合内容；可在设置里关闭。
- **展开卡片后手动改窗口大小**也会重新贴合，不再留白或被挤。
- **热键修复**：字母 / 数字热键以前会被桌面上残留的文本光标判据挡掉，现在只认真正的输入框（含控件类名判定），`x` 之类的热键恢复正常。
- **连点显示**：拖动跟手不再在按下瞬间跳过去；「预览一下」改为「试播动画」，随时重放入场动画。
- **设置界面**：说明文字改为整行自适应，长文本不再被右侧裁掉；标题栏右侧的「?」换成「GitHub 仓库」按钮。
- **外观切换**有转圈提示，应用时遮罩盖在当前设置窗上。

### English
- Data directory is now `%APPDATA%\\VexRush` (config + language packs), with an "open data folder" button; a portable `config.json` beside the exe is migrated once.
- Translations are JSON language packs (`lang\\*.json`, semantic keys). Drop your own file in and it appears in the language list marked *unofficial*.
- Optional smooth window easing while dragging the title bar / border, and the height re-fits after resize.
- Letter / digit hotkeys work again (the typing guard now requires a real text-input control).
- HUD drag no longer jumps on the first frame; the preview button replays the enter animation.
- Settings hints wrap instead of being clipped; the title-bar "?" became a GitHub button.

**Full changelog:** https://github.com/Yelastforbilibili/VexRush/compare/v3.0.0...v3.1.0
"""


def api(url, data=None, method=None, raw=None, extra_headers=None):
    headers = {
        "Authorization": "token " + TOKEN,
        "Accept": "application/vnd.github+json",
        "User-Agent": "VexRush-release-script",
    }
    if extra_headers:
        headers.update(extra_headers)
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    elif raw is not None:
        body = raw
        headers["Content-Type"] = "application/octet-stream"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(request, timeout=600) as response:
        payload = response.read()
        return response.status, (json.loads(payload.decode("utf-8")) if payload else None)


def main() -> int:
    try:
        status, existing = api(
            "https://api.github.com/repos/%s/%s/releases/tags/%s" % (OWNER, REPO, TAG))
    except Exception:
        existing = None
    if existing:
        print("release already exists", existing["html_url"])
        release = existing
        status = 200
    else:
        status, release = api(
            "https://api.github.com/repos/%s/%s/releases" % (OWNER, REPO),
        data={
                "tag_name": TAG,
                "target_commitish": "main",
                "name": "VexRush 3.1.0",
                "body": BODY,
                "draft": False,
                "prerelease": False,
            },
            method="POST",
        )
    print("release status", status)
    print("release url", release["html_url"])
    upload_url = release["upload_url"].split("{")[0]

    with io.open(EXE, "rb") as handle:
        blob = handle.read()
    print("exe bytes", len(blob))
    status, asset = api(upload_url + "?name=VexRush.exe", raw=blob, method="POST")
    print("asset status", status)
    print("asset url", asset["browser_download_url"])
    print("asset size", asset["size"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
