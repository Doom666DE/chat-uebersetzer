"""Check for releases and install a verified update after the app closes."""

from dataclasses import dataclass
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import uuid4

import pywintypes
import win32api
import win32con
import win32event
import win32file


VERSION = "0.5.6"
REPO = "Doom666DE/chat-uebersetzer"
ASSET = "Chat-Uebersetzer-win-x64.exe"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES = f"https://github.com/{REPO}/releases"
MAX_SIZE = 80 * 1024 * 1024
EVENT_PREFIX = "Local\\ChatUebersetzerUpdate-"
HELPER = "update-helper.exe"
DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


@dataclass(frozen=True)
class Release:
    tag: str
    url: str
    digest: str
    size: int
    notes: str = ""

    @property
    def page_url(self):
        return f"{RELEASES}/tag/{self.tag}"


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
            notes = data.get("body")
            return Release(tag, url, digest[7:], size, notes.strip() if isinstance(notes, str) else "")
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
    event = EVENT_PREFIX + uuid4().hex
    helper = staged.with_name(HELPER)
    shutil.copyfile(sys.executable, helper)
    command = [str(helper), "--apply-update", sys.executable, release.digest,
               str(os.getpid()), str(os.getppid()), event, language]
    start_independently(command)


def start_independently(command):
    env = os.environ | {"PYINSTALLER_RESET_ENVIRONMENT": "1"}
    try:
        return subprocess.Popen(command, env=env, creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB)
    except OSError as error:
        if error.winerror != 5:
            raise
        return subprocess.Popen(command, env=env)


def matching_process(pid, path):
    try:
        process = win32api.OpenProcess(win32con.SYNCHRONIZE | win32con.PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    except pywintypes.error as error:
        if error.winerror == 87:
            return None
        raise
    name = ctypes.create_unicode_buffer(32768)
    length = wintypes.DWORD(len(name))
    query = ctypes.windll.kernel32.QueryFullProcessImageNameW
    query.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))
    matches = False
    try:
        if query(int(process), 0, name, ctypes.byref(length)):
            matches = Path(name.value) == path
            if matches:
                return process
        elif win32event.WaitForSingleObject(process, 0) != win32event.WAIT_OBJECT_0:
            raise ctypes.WinError()
    finally:
        if not matches:
            process.Close()
    return None


def wait_for_exit(pid, path, timeout):
    process = matching_process(pid, path)
    if process is not None:
        try:
            if win32event.WaitForSingleObject(process, timeout) != win32event.WAIT_OBJECT_0:
                raise TimeoutError("Translator did not exit")
        finally:
            process.Close()


def replace_executable(source, target, backup):
    deadline = time.monotonic() + 15
    while True:
        try:
            win32file.ReplaceFile(str(source), str(target), str(backup), 0)
            return
        except pywintypes.error as error:
            if error.winerror not in (32, 33) or time.monotonic() >= deadline:
                raise
            time.sleep(0.25)


def staging_folder(folder, target):
    return folder.parent == target.parent and re.fullmatch(r"\.chat-update-[a-z0-9_]+", folder.name)


def valid_event(name):
    return re.fullmatch(re.escape(EVENT_PREFIX) + r"[a-f0-9]{32}", name)


def apply_update(arguments):
    if not arguments or arguments[0] != "--apply-update":
        return False
    if len(arguments) != 7 or not is_portable():
        return True
    _, raw_target, digest, old_pid, loader_pid, event, language = arguments
    helper = Path(sys.executable)
    folder = helper.parent
    target = Path(raw_target)
    source = folder / ASSET
    backup = folder / "previous.exe"
    failed = folder / "failed.exe"
    if not (helper.name == HELPER and target.is_absolute() and target.suffix.casefold() == ".exe"
            and staging_folder(folder, target) and re.fullmatch(r"[a-f0-9]{64}", digest)
            and old_pid.isdecimal() and loader_pid.isdecimal() and valid_event(event)):
        return True
    next_app = None
    ready = None
    replaced = False
    started = False
    try:
        with source.open("rb") as payload:
            if hashlib.file_digest(payload, "sha256").hexdigest() != digest:
                raise ValueError("Update checksum mismatch")
        ready = win32event.CreateEvent(None, True, False, event)
        if win32api.GetLastError() == 183:
            raise OSError("Update event already exists")
        wait_for_exit(int(old_pid), target, 15000)
        wait_for_exit(int(loader_pid), target, 15000)
        replace_executable(source, target, backup)
        replaced = True
        next_app = start_independently([str(target), "--update-ready", event, folder.name, str(os.getppid())])
        deadline = time.monotonic() + 45
        while win32event.WaitForSingleObject(ready, 300) != win32event.WAIT_OBJECT_0:
            if next_app.poll() is not None or time.monotonic() >= deadline:
                raise OSError("The updated translator did not start")
        started = True
    except (OSError, ValueError, pywintypes.error):
        restored = not replaced
        if replaced:
            try:
                if next_app is not None and next_app.poll() is None:
                    next_app.terminate()
                    next_app.wait(timeout=5)
                replace_executable(backup, target, failed)
                restored = True
            except (OSError, subprocess.TimeoutExpired, pywintypes.error):
                pass
        if restored:
            try:
                start_independently([str(target), "--cleanup-update", folder.name, str(os.getppid())])
            except OSError:
                pass
        if language == "de":
            message = ("Das Update ist fehlgeschlagen. Die vorherige Version ist weiterhin vorhanden."
                       if restored else f"Das Update ist fehlgeschlagen. Die Sicherung liegt unter\n{backup}")
        else:
            message = ("The update failed. The previous version is still available."
                       if restored else f"The update failed. The backup is at\n{backup}")
        win32api.MessageBox(0, message, "Chat-Update", win32con.MB_OK | win32con.MB_ICONERROR)
    finally:
        if ready is not None:
            ready.Close()
    if started:
        try:
            backup.unlink(missing_ok=True)
        except OSError:
            pass
    return True


def clean_up_after_helper(folder_name, pid):
    target = Path(sys.executable)
    folder = target.parent / folder_name
    if not staging_folder(folder, target) or not pid.isdecimal():
        return
    try:
        helper = folder / HELPER
        wait_for_exit(int(pid), helper, 60000)
        for file in (helper, folder / ASSET, folder / "failed.exe"):
            file.unlink(missing_ok=True)
        folder.rmdir()
    except (OSError, pywintypes.error):
        pass


def signal_ready(arguments):
    if len(arguments) == 3 and arguments[0] == "--cleanup-update":
        threading.Thread(target=clean_up_after_helper, args=arguments[1:], daemon=True).start()
        return
    if len(arguments) not in (2, 4) or arguments[0] != "--update-ready":
        return
    name = arguments[1]
    if not valid_event(name):
        return
    try:
        handle = win32event.OpenEvent(win32con.EVENT_MODIFY_STATE, False, name)
    except pywintypes.error:
        return
    try:
        win32event.SetEvent(handle)
    finally:
        handle.Close()
    if len(arguments) == 4:
        threading.Thread(target=clean_up_after_helper, args=arguments[2:], daemon=True).start()
