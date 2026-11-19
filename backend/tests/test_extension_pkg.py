"""Paczki rozszerzenia z serwera = to samo co extension/build.sh."""
from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import extension_pkg  # noqa: E402
import main  # noqa: E402

client = TestClient(main.app)


def _zip(data: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(data))


def test_info_lists_three_packages():
    r = client.get("/api/extension")
    assert r.status_code == 200
    info = r.json()
    assert info["available"] and info["version"] == extension_pkg.version()
    assert [p["browser"] for p in info["packages"]] == ["firefox", "chromium", "opera"]


@pytest.mark.parametrize("browser", ["firefox", "chromium", "opera"])
def test_download(browser):
    r = client.get(f"/api/extension/{browser}")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    z = _zip(r.content)
    m = json.loads(z.read("manifest.json"))
    names = z.namelist()
    assert "background.js" in names and "shared/render.js" in names and "_locales/pl/messages.json" in names
    assert not any(n.startswith(("tests/", "README")) or n.endswith(".sh") for n in names)
    if browser == "firefox":
        assert m == extension_pkg.manifest()
    else:
        assert m["background"] == {"service_worker": "background.js"}
        assert "contextMenus" in m["permissions"] and "menus" not in m["permissions"]
        assert "browser_specific_settings" not in m


def test_unknown_browser_rejected():
    assert client.get("/api/extension/safari").status_code == 422


def test_same_content_as_build_sh(tmp_path):
    """Zawartosc paczek jak z extension/build.sh (gdy jest zip w systemie)."""
    import shutil
    if not shutil.which("zip"):
        pytest.skip("no zip command")
    ext = extension_pkg.EXT_DIR
    work = tmp_path / "repo"
    shutil.copytree(ext, work / "extension")
    subprocess.run(["bash", str(work / "extension" / "build.sh")], check=True, capture_output=True)
    v = extension_pkg.version()
    for browser, fname in [("firefox", f"hermes-finder-{v}.xpi"),
                           ("chromium", f"hermes-finder-{v}-chromium.zip"),
                           ("opera", f"hermes-finder-{v}-opera.zip")]:
        ref = zipfile.ZipFile(work / "dist" / fname)
        ours = _zip(extension_pkg.build(browser))
        files = lambda z: sorted(n for n in z.namelist() if not n.endswith("/"))  # noqa: E731
        assert files(ours) == files(ref), browser
        assert json.loads(ours.read("manifest.json")) == json.loads(ref.read("manifest.json")), browser
