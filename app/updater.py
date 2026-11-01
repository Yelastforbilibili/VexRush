# -*- coding: utf-8 -*-
"""更新检测与下载。

接口固定为 GitHub Releases 的 latest，优先直连官方地址；2 秒内没有响应则依次换用加速站。
下载安装包之前先对每个候选地址做一次小范围测速，取实际最快的那个，并在下载完成后校验
GitHub 接口给出的 SHA-256。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

API_URL = "https://api.github.com/repos/Yelastforbilibili/VexRush/releases/latest"
MIRROR_PREFIXES: Tuple[str, ...] = (
    "https://cdn.gh-proxy.org/",
    "https://v6.gh-proxy.org/",
    "https://gh-proxy.org/",
)
CHECK_TIMEOUT = 2.0
PROBE_BYTES = 262144
PROBE_TIMEOUT = 6.0
CHUNK = 128 * 1024
ASSET_NAME = "VexRush.exe"
USER_AGENT = "VexRush-updater"


class UpdateError(Exception):
    """更新过程中的可预期错误。"""


@dataclass
class ReleaseInfo:
    tag: str
    version: Tuple[int, ...]
    name: str
    notes: str
    html_url: str
    published_at: str
    asset_name: str
    asset_url: str
    asset_size: int
    sha256: str
    source: str

    @property
    def version_text(self) -> str:
        return ".".join(str(part) for part in self.version)


def parse_version(text: str) -> Tuple[int, ...]:
    """把 v3.2.2 / 3.2.2-beta 之类的字符串转成可比较的整数元组。"""
    cleaned = (text or "").strip()
    if cleaned[:1] in ("v", "V"):
        cleaned = cleaned[1:]
    numbers = re.findall(r"\d+", cleaned)
    if not numbers:
        return (0,)
    return tuple(int(item) for item in numbers[:4])


def is_newer(local: str, remote: str) -> bool:
    left = parse_version(local)
    right = parse_version(remote)
    length = max(len(left), len(right))
    left = left + (0,) * (length - len(left))
    right = right + (0,) * (length - len(right))
    return right > left


def candidate_urls(url: str, prefixes: Sequence[str] = MIRROR_PREFIXES) -> List[str]:
    """官方地址在前，加速站在后。加速站的用法是直接在原始地址前拼接。"""
    result = [url]
    for prefix in prefixes:
        candidate = prefix + url
        if candidate not in result:
            result.append(candidate)
    return result


def _label(url: str) -> str:
    if not MIRROR_PREFIXES:
        return url
    for prefix in MIRROR_PREFIXES:
        if url.startswith(prefix):
            return prefix.rstrip("/")
    return "github.com"


def _open(url: str, timeout: float, headers: Optional[dict] = None):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(request, timeout=timeout)


def parse_release(payload: dict, source: str = "") -> ReleaseInfo:
    if not isinstance(payload, dict):
        raise UpdateError("接口返回的数据格式不对")
    tag = str(payload.get("tag_name") or "")
    assets = payload.get("assets") or []
    target = None
    for asset in assets:
        if str(asset.get("name") or "").lower() == ASSET_NAME.lower():
            target = asset
            break
    if target is None:
        for asset in assets:
            if str(asset.get("name") or "").lower().endswith(".exe"):
                target = asset
                break
    if target is None:
        raise UpdateError("该版本没有可用的安装包")
    digest = str(target.get("digest") or "")
    sha256 = ""
    if digest.lower().startswith("sha256:"):
        sha256 = digest.split(":", 1)[1].strip().lower()
    elif re.fullmatch(r"[0-9a-f]{64}", digest.strip().lower()):
        sha256 = digest.strip().lower()
    return ReleaseInfo(
        tag=tag,
        version=parse_version(tag or payload.get("name") or ""),
        name=str(payload.get("name") or tag),
        notes=str(payload.get("body") or ""),
        html_url=str(payload.get("html_url") or ""),
        published_at=str(payload.get("published_at") or ""),
        asset_name=str(target.get("name") or ""),
        asset_url=str(target.get("browser_download_url") or ""),
        asset_size=int(target.get("size") or 0),
        sha256=sha256,
        source=source or _label(API_URL),
    )


def fetch_latest(timeout: float = CHECK_TIMEOUT) -> ReleaseInfo:
    """直连官方接口，超时或失败后依次尝试加速站。"""
    errors: List[str] = []
    for url in candidate_urls(API_URL):
        try:
            with _open(url, timeout, {"Accept": "application/vnd.github+json"}) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            return parse_release(payload, _label(url))
        except UpdateError:
            raise
        except Exception as exc:                      # 网络错误、超时、非 JSON
            errors.append("%s: %s" % (_label(url), exc))
    raise UpdateError("无法连接更新服务器（%s）" % "; ".join(errors[:2]))


def probe_speed(url: str, timeout: float = PROBE_TIMEOUT, probe_bytes: int = PROBE_BYTES) -> float:
    """下载一小段数据，返回字节/秒；失败抛异常。"""
    start = time.perf_counter()
    with _open(url, timeout, {"Range": "bytes=0-%d" % (probe_bytes - 1)}) as response:
        data = response.read(probe_bytes)
    elapsed = max(time.perf_counter() - start, 0.001)
    if not data:
        raise UpdateError("测速没有收到数据")
    return len(data) / elapsed


def rank_candidates(urls: Iterable[str], timeout: float = PROBE_TIMEOUT) -> List[Tuple[str, float]]:
    """按实测速度从快到慢排序；直连在速度接近时优先。"""
    scored: List[Tuple[str, float]] = []
    for index, url in enumerate(urls):
        try:
            speed = probe_speed(url, timeout)
        except Exception:
            continue
        bonus = 1.08 if index == 0 else 1.0          # 官方地址略微优先
        scored.append((url, speed * bonus))
    scored.sort(key=lambda item: item[1], reverse=True)
    return scored


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(
    candidates: Sequence[str],
    dest: str,
    expected_sha256: str,
    progress: Optional[Callable[[int, int], None]] = None,
    cancel: Optional[Callable[[], bool]] = None,
) -> str:
    """按给定顺序尝试候选地址，边下载边算 SHA-256，校验不通过就换下一个地址。"""
    errors: List[str] = []
    directory = os.path.dirname(os.path.abspath(dest))
    if directory:
        os.makedirs(directory, exist_ok=True)
    for url in candidates:
        part = dest + ".part"
        try:
            digest = hashlib.sha256()
            done = 0
            with _open(url, PROBE_TIMEOUT) as response:
                total = int(response.headers.get("Content-Length") or 0)
                with open(part, "wb") as handle:
                    while True:
                        if cancel is not None and cancel():
                            raise UpdateError("已取消")
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        done += len(chunk)
                        if progress is not None:
                            progress(done, total)
            actual = digest.hexdigest()
            if expected_sha256 and actual != expected_sha256.lower():
                errors.append("%s: SHA-256 不一致" % _label(url))
                os.remove(part)
                continue
            os.replace(part, dest)
            return actual
        except Exception as exc:
            errors.append("%s: %s" % (_label(url), exc))
            if os.path.exists(part):
                try:
                    os.remove(part)
                except OSError:
                    pass
            if isinstance(exc, UpdateError) and str(exc) == "已取消":
                raise
    raise UpdateError("下载失败（%s）" % "; ".join(errors[:2]))


def install_and_restart(new_exe: str, target_exe: str, process_id: int) -> str:
    """写一个 PowerShell 助手：等本进程退出 → 覆盖安装包 → 重新启动。返回脚本路径。"""
    script = """$ErrorActionPreference = 'SilentlyContinue'
$target = @'
{TARGET}
'@
$source = @'
{SOURCE}
'@
try {{ Wait-Process -Id {PID} -Timeout 40 }} catch {{ }}
Start-Sleep -Milliseconds 500
for ($i = 0; $i -lt 40; $i++) {{
    try {{
        Copy-Item -LiteralPath $source -Destination $target -Force -ErrorAction Stop
        break
    }} catch {{
        Start-Sleep -Milliseconds 400
    }}
}}
try {{ Remove-Item -LiteralPath $source -Force }} catch {{ }}
Start-Process -FilePath $target
try {{ Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force }} catch {{ }}
""".format(TARGET=target_exe, SOURCE=new_exe, PID=int(process_id))
    path = os.path.join(tempfile.gettempdir(), "vexrush_update_%d.ps1" % int(process_id))
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as handle:
        handle.write(script)
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
         "-File", path],
        close_fds=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    return path


def format_size(value: int) -> str:
    size = float(max(0, int(value)))
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return ("%.0f %s" % (size, unit)) if unit == "B" else ("%.1f %s" % (size, unit))
        size /= 1024.0
    return "%.1f GB" % size
