"""Check for releases and install a verified update after the app closes."""

import base64
import ctypes
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

import pywintypes
import win32con
import win32event


VERSION = "0.5.0"
REPO = "Doom666DE/chat-uebersetzer"
ASSET = "Chat-Uebersetzer-win-x64.exe"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases"
MAX_SIZE = 80 * 1024 * 1024
EVENT_PREFIX = "Local\\ChatUebersetzerUpdate-"
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


@dataclass(frozen=True)
class Release:
    tag: str
    url: str
    digest: str
    size: int


def version_parts(value):
    if isinstance(value, str) and re.fullmatch(r"v?[0-9]{1,6}\.[0-9]{1,6}\.[0-9]{1,6}", value):
        return tuple(map(int, value.removeprefix("v").split(".")))
    return None


def newer_release(data, installed=VERSION):
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name")
    version = version_parts(tag)
    if version is None or version <= version_parts(installed):
        return None
    url = f"{RELEASES}/download/{tag}/{ASSET}"
    for asset in data.get("assets", []):
        if asset.get("name") != ASSET or asset.get("state") != "uploaded":
            continue
        digest = asset.get("digest")
        size = asset.get("size")
        if (
            asset.get("browser_download_url") == url
            and isinstance(digest, str) and re.fullmatch(r"sha256:[a-f0-9]{64}", digest)
            and type(size) is int and 0 < size <= MAX_SIZE
        ):
            return Release(tag, url, digest[7:], size)
    raise ValueError("No verifiable Windows asset in release")


class ApprovedRedirects(HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urlsplit(newurl)
        if (target.scheme != "https" or target.netloc not in self.hosts):
            raise ValueError("Unexpected GitHub redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def github_request(url, hosts, accept):
    request = Request(url, headers={"User-Agent": f"Chat-Uebersetzer/{VERSION}", "Accept": accept})
    return build_opener(ApprovedRedirects(hosts)).open(request, timeout=15)


def check_release():
    with github_request(API, {"api.github.com"}, "application/vnd.github+json") as response:
        body = response.read(2 * 1024 * 1024 + 1)
    if len(body) > 2 * 1024 * 1024:
        raise ValueError("Release metadata is too large")
    return newer_release(json.loads(body))


def is_portable():
    return getattr(sys, "frozen", False) and Path(sys.executable).suffix.casefold() == ".exe"


def download_update(release, installed, cancelled):
    """Create a staging directory beside the installed executable for an atomic replacement."""
    folder = Path(tempfile.mkdtemp(prefix=".chat-update-", dir=installed.parent))
    staged = folder / ASSET
    try:
        sha = hashlib.sha256()
        received = 0
        if cancelled.is_set():
            raise InterruptedError
        with github_request(release.url, DOWNLOAD_HOSTS, "application/octet-stream") as response, staged.open("xb") as output:
            while chunk := response.read1(128 * 1024):
                if cancelled.is_set():
                    raise InterruptedError
                received += len(chunk)
                if received > release.size:
                    raise ValueError("Update exceeds the advertised size")
                sha.update(chunk)
                output.write(chunk)
        if received != release.size or sha.hexdigest() != release.digest:
            raise ValueError("Update size or checksum does not match")
        return staged
    except Exception:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def launch_installer(staged, release, language):
    script = Path(__file__).with_name("apply_update.ps1").read_text(encoding="utf-8")
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    windows = Path(os.environ["SystemRoot"]) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    event = EVENT_PREFIX + uuid4().hex
    env = os.environ | {
        "CHAT_UPDATE_TARGET": sys.executable,
        "CHAT_UPDATE_SOURCE": str(staged),
        "CHAT_UPDATE_HASH": release.digest,
        "CHAT_UPDATE_PID": str(os.getpid()),
        "CHAT_UPDATE_BOOTLOADER": str(os.getppid()),
        "CHAT_UPDATE_EVENT": event,
        "CHAT_UPDATE_LANGUAGE": language,
        "PYINSTALLER_RESET_ENVIRONMENT": "1",
    }
    dll_directory = ctypes.windll.kernel32.SetDllDirectoryW
    dll_directory.argtypes = [ctypes.c_wchar_p]
    dll_directory(None)
    try:
        subprocess.Popen([str(windows), "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                         env=env, creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        dll_directory(str(sys._MEIPASS))


def signal_ready(arguments):
    if len(arguments) != 2 or arguments[0] != "--update-ready":
        return
    name = arguments[1]
    if not re.fullmatch(re.escape(EVENT_PREFIX) + r"[a-f0-9]{32}", name):
        return
    try:
        handle = win32event.OpenEvent(win32con.EVENT_MODIFY_STATE, False, name)
    except pywintypes.error:
        return
    try:
        win32event.SetEvent(handle)
    finally:
        handle.Close()
