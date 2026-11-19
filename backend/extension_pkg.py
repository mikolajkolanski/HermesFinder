"""Paczki rozszerzenia Hermes Finder do pobrania ze strony (sekcja "Instalacja").

Paczki powstaja w locie z katalogu extension/ - zawsze w wersji zgodnej z kodem
serwera - tak samo jak w extension/build.sh:
  * firefox  -> .xpi (manifest bez zmian),
  * chromium -> .zip (Chrome/Edge/Brave: "Zaladuj rozpakowane"),
  * opera    -> .zip (Opera: "Load unpacked").
Manifest Chromium/Opery: tlo jako service worker, uprawnienie contextMenus zamiast
menus, bez browser_specific_settings.

Podpisany przez Mozille .xpi (extension/sign-firefox.sh -> dist/signed/*.xpi albo
CV_FIREFOX_XPI) instaluje sie na stale jednym kliknieciem; jesli jest dostepny dla
biezacej wersji, serwer wydaje go zamiast niepodpisanego.
"""
from __future__ import annotations

import io
import json
import os
import threading
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXT_DIR = Path(os.environ.get("CV_EXTENSION_DIR") or ROOT / "extension")
SIGNED_DIR = ROOT / "dist" / "signed"
FILES = ["background.js", "content", "popup", "options", "panel", "shared", "icons", "_locales"]
BROWSERS = ("firefox", "chromium", "opera")
SKIP = (".DS_Store",)

_cache: dict[tuple[str, float], bytes] = {}
_lock = threading.Lock()


def available() -> bool:
    return (EXT_DIR / "manifest.json").exists()


def manifest() -> dict[str, Any]:
    return json.loads((EXT_DIR / "manifest.json").read_text(encoding="utf-8"))


def version() -> str:
    return str(manifest().get("version", "0"))


def chromium_manifest(m: dict[str, Any], browser: str) -> dict[str, Any]:
    m = json.loads(json.dumps(m))
    m["background"] = {"service_worker": "background.js"}  # skrypty laduje importScripts
    m["permissions"] = ["contextMenus" if p == "menus" else p for p in m.get("permissions", [])]
    m.pop("browser_specific_settings", None)
    # Opera 109+ (Chromium 123) i Chromium 121+: MV3, storage.session, scripting
    m["minimum_chrome_version"] = "123" if browser == "opera" else "121"
    return m


def _files() -> list[Path]:
    out: list[Path] = []
    for name in FILES:
        p = EXT_DIR / name
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            out += sorted(x for x in p.rglob("*") if x.is_file()
                          and not x.name.endswith(SKIP) and not x.name.endswith("~"))
    return out


def _stamp() -> float:
    paths = [EXT_DIR / "manifest.json"] + _files()
    return max(p.stat().st_mtime for p in paths) + len(paths)


def signed_xpi() -> Path | None:
    """Podpisany .xpi dla biezacej wersji (CV_FIREFOX_XPI albo dist/signed/)."""
    env = os.environ.get("CV_FIREFOX_XPI")
    if env and Path(env).is_file():
        return Path(env)
    if SIGNED_DIR.is_dir():
        v = version()
        cands = [p for p in SIGNED_DIR.glob("*.xpi") if v in p.name]
        if cands:
            return max(cands, key=lambda p: p.stat().st_mtime)
    return None


def filename(browser: str) -> str:
    v = version()
    return f"hermes-finder-{v}.xpi" if browser == "firefox" else f"hermes-finder-{v}-{browser}.zip"


def build(browser: str) -> bytes:
    """Paczka dla przegladarki (z pamieci, przebudowa po zmianie plikow)."""
    if browser not in BROWSERS:
        raise ValueError(f"unknown browser: {browser}")
    if browser == "firefox":
        signed = signed_xpi()
        if signed:
            return signed.read_bytes()
    key = (browser, _stamp())
    with _lock:
        if key in _cache:
            return _cache[key]
    m = manifest()
    if browser != "firefox":
        m = chromium_manifest(m, browser)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(m, ensure_ascii=False, indent=2))
        for p in _files():
            z.write(p, p.relative_to(EXT_DIR).as_posix())
    data = buf.getvalue()
    with _lock:
        _cache.clear() if len(_cache) > 6 else None
        _cache[key] = data
    return data


def info() -> dict[str, Any]:
    if not available():
        return {"available": False, "packages": []}
    m = manifest()
    signed = signed_xpi() is not None
    return {
        "available": True,
        "version": m.get("version"),
        "name": m.get("name"),
        "firefox_min": ((m.get("browser_specific_settings") or {}).get("gecko") or {}).get("strict_min_version"),
        "packages": [
            {"browser": b, "url": f"/api/extension/{b}", "filename": filename(b),
             "signed": signed if b == "firefox" else False}
            for b in BROWSERS
        ],
    }
