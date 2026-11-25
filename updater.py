# -*- coding: utf-8 -*-
"""Auto-update support for Europa (GitHub Releases).

Pure standard library — no extra dependencies, nothing to install at runtime.

Flow:
    check_for_update(current_version)  -> dict | None   (GitHub API)
    checksum_for(info)                 -> sha256 | None (SHA256SUMS.txt asset)
    download_installer(info, sha256)   -> local path    (verified)
    launch_installer(path)             -> starts Inno Setup silently

Only installers published in this repository's releases are accepted, and the
downloaded file is verified against the published SHA-256 before it is run.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request

GITHUB_REPO = "0x-Shadow/AlumilOffers_platform"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
LATEST_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

USER_AGENT = "Europa-Updater"
_META_LIMIT = 2 * 1024 * 1024        # release JSON cap
_CHECKSUM_LIMIT = 64 * 1024          # SHA256SUMS.txt cap
_INSTALLER_LIMIT = 400 * 1024 * 1024  # 400 MB sanity cap
_MIN_INSTALLER = 1024 * 1024         # refuse suspiciously small "installers"

_INSTALLER_RE = re.compile(r"^Setup_Europa_[0-9]+(?:\.[0-9]+)*\.exe$", re.I)
_SHA_RE = re.compile(r"^[0-9a-f]{64}$")


class UpdateError(Exception):
    """Raised when an update cannot be checked, downloaded or verified."""


def parse_version(text):
    """'v1.4.0' -> (1, 4, 0). Missing/invalid versions yield ()."""
    m = re.search(r"(\d+(?:\.\d+){1,3})", text or "")
    if not m:
        return ()
    return tuple(int(part) for part in m.group(1).split("."))


def is_newer(latest, current):
    """True when `latest` is strictly newer than `current`."""
    new, old = parse_version(latest), parse_version(current)
    if not new or not old:
        return False
    width = max(len(new), len(old))
    return new + (0,) * (width - len(new)) > old + (0,) * (width - len(old))


def _http_get(url, timeout, limit):
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read(limit + 1)
    if len(data) > limit:
        raise UpdateError("Server response is unexpectedly large.")
    return data


def check_for_update(current_version, timeout=8):
    """Return release info when a newer stable release exists, else None.

    Never raises: network/JSON problems are reported as UpdateError so the
    caller can keep the banner silent and the app fully usable offline.
    """
    try:
        payload = json.loads(_http_get(LATEST_API, timeout, _META_LIMIT).decode("utf-8"))
    except UpdateError:
        raise
    except Exception as exc:
        raise UpdateError(f"Update check failed: {exc}") from exc

    tag = payload.get("tag_name") or payload.get("name") or ""
    if not is_newer(tag, current_version):
        return None

    assets = {}
    for asset in payload.get("assets") or []:
        name = asset.get("name") or ""
        url = asset.get("browser_download_url") or ""
        if name and url:
            assets[name] = url

    wanted = parse_version(tag)
    installer_name = next(
        (n for n in assets if _INSTALLER_RE.match(n) and parse_version(n) == wanted), None)
    if installer_name is None:  # tolerate unusual asset naming
        installer_name = next((n for n in assets if _INSTALLER_RE.match(n)), None)
    return {
        "version": ".".join(str(p) for p in wanted),
        "tag": tag,
        "notes": (payload.get("body") or "").strip(),
        "page_url": payload.get("html_url") or RELEASES_URL,
        "installer_name": installer_name,
        "installer_url": assets.get(installer_name) if installer_name else None,
        "checksums_url": assets.get("SHA256SUMS.txt"),
    }


def checksum_for(info, timeout=8):
    """Return the published SHA-256 for the installer, or None if unavailable."""
    url = (info or {}).get("checksums_url")
    name = (info or {}).get("installer_name")
    if not url or not name:
        return None
    try:
        text = _http_get(url, timeout, _CHECKSUM_LIMIT).decode("utf-8", "replace")
    except Exception:
        return None
    for line in text.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == name:
            digest = parts[0].lower()
            if _SHA_RE.match(digest):
                return digest
    return None


def download_installer(info, expected_sha256, progress=None, timeout=60):
    """Download the release installer to a temp folder and verify its SHA-256.

    `progress` is called as progress(done_bytes, total_bytes) during download.
    Raises UpdateError on any mismatch; the partial file is removed.
    """
    url = (info or {}).get("installer_url")
    name = (info or {}).get("installer_name") or "setup.exe"
    if not url:
        raise UpdateError("This release has no Windows installer.")
    if not expected_sha256 or not _SHA_RE.match(expected_sha256 or ""):
        raise UpdateError("No published checksum — refusing automatic install.")

    folder = tempfile.mkdtemp(prefix="alumina_update_")
    dest = os.path.join(folder, os.path.basename(name))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    digest = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp, open(dest, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            if total > _INSTALLER_LIMIT:
                raise UpdateError("Installer is larger than expected.")
            done = 0
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                done += len(chunk)
                if done > _INSTALLER_LIMIT:
                    raise UpdateError("Installer is larger than expected.")
                digest.update(chunk)
                fh.write(chunk)
                if progress:
                    try:
                        progress(done, total)
                    except Exception:
                        pass
        if os.path.getsize(dest) < _MIN_INSTALLER:
            raise UpdateError("Downloaded installer looks incomplete.")
        actual = digest.hexdigest()
        if not hmac.compare_digest(actual, expected_sha256.lower()):
            raise UpdateError("Checksum mismatch — the download was discarded.")
        return dest
    except UpdateError:
        _silent_remove(dest)
        raise
    except Exception as exc:
        _silent_remove(dest)
        raise UpdateError(f"Download failed: {exc}") from exc


def launch_installer(path):
    """Start the Inno Setup installer silently; it replaces files and relaunches."""
    if sys.platform != "win32":
        raise UpdateError("Automatic installation is supported on Windows only.")
    if not os.path.isfile(path):
        raise UpdateError("Installer file not found.")
    subprocess.Popen(
        [path, "/SILENT", "/CLOSEAPPLICATIONS", "/RESTARTAPPLICATIONS",
         "/NORESTART", "/SUPPRESSMSGBOXES"],
        close_fds=True,
    )


def _silent_remove(path):
    """Remove a failed download and its private temp folder."""
    try:
        if path:
            folder = os.path.dirname(path)
            if os.path.isdir(folder) and os.path.basename(folder).startswith("alumina_update_"):
                shutil.rmtree(folder, ignore_errors=True)
            elif os.path.isfile(path):
                os.remove(path)
    except OSError:
        pass
