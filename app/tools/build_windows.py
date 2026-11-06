"""파이썬이 들어간 Windows 설치판을 만듭니다: python tools/build_windows.py

결과: (프로젝트 상위 폴더)/서비_Windows설치판_v버전.zip

자동 업데이트용으로 배포할 때:
  python tools/build_windows.py --release --base-url https://…/releases --update-url https://…/latest.json
  → zip과 함께 latest.json(버전·주소·sha256)을 만듭니다. 두 파일을 base-url 위치에 올리면,
    설치된 서비들이 켤 때 새 버전을 찾아 업데이트합니다.
받는 PC에는 파이썬도 인터넷도 필요 없습니다. 압축을 풀고 '설치하기.bat'을 누르면 됩니다.
실제 기관 자료(예시 기관 외), API 키(.env), 질문 기록은 넣지 않습니다.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from datetime import date
from pathlib import Path
from urllib.parse import quote

PY_VERSION = "3.14.10"
ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".cache" / "build"
APP = BUILD / "서비"
EXAMPLE_ORGS = {"demo-agency", "demo-city"}
SKIP_DIRS = {".git", ".claude", ".pytest_cache", "__pycache__", "outputs", ".cache",
             "tests", "data_backups", "node_modules", "desktop"}   # desktop 은 3.5단계에서 따로 넣습니다
SKIP_FILES = {".env", ".install_id", "server.log", "scratch_out.txt", "설치.bat", "설치.sh", "실행.bat", "render.yaml"}

INSTALL_BAT = r'''@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "python\python.exe" (
    echo.
    echo  [오류] 압축을 먼저 풀어 주세요. 압축 파일 안에서 바로 실행하면 설치되지 않습니다.
    echo  압축 파일을 마우스 오른쪽 버튼으로 눌러 "압축 풀기"를 한 뒤, 풀린 폴더에서 다시 실행하세요.
    echo.
    pause
    exit /b 1
)
"python\python.exe" tools\install.py
'''

RUN_BAT = r'''@echo off
chcp 65001 >nul
REM 서비를 화면에 띄웁니다. 서버는 서비가 알아서 켭니다.
cd /d "%~dp0"
if exist "desktop\node_modules\electron\dist\electron.exe" (
  start "" "desktop\node_modules\electron\dist\electron.exe" "desktop"
) else (
  echo   화면 위젯이 들어 있지 않아 서버만 켭니다.
  "python\python.exe" run.py --browser
  pause
)
'''


def _skip(rel: Path) -> bool:
    parts = rel.parts
    if any(p in SKIP_DIRS for p in parts) or rel.name in SKIP_FILES or rel.suffix == ".pyc":
        return True
    if parts[:2] == ("data", "orgs"):
        if len(parts) > 2 and parts[2] not in EXAMPLE_ORGS:
            return True
        if rel.name in ("history.jsonl", "done.json") or "profile_history" in parts:
            return True
    return parts[:1] == ("data",) and len(parts) > 1 and parts[1] == "orgs_deleted"


def _clean_config(text: str, update_url: str | None) -> str:
    """받는 PC용 설정: AI·메일 연결은 끄고(키가 없으니), 업데이트 주소는 넣습니다."""
    import yaml
    cfg = yaml.safe_load(text) or {}
    for role in (cfg.get("roles") or {}).values():
        role.update(provider="none", model=None)
    cfg.pop("show_example_orgs", None)
    (cfg.get("mail") or {})["provider"] = "none"
    if update_url is not None:
        cfg["update"] = {"url": update_url, "auto": True}
    head = "".join(l for l in text.splitlines(keepends=True)[:4] if l.startswith("#"))
    return head + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False)


def get_python() -> Path:
    dl = BUILD / "download"
    dl.mkdir(parents=True, exist_ok=True)
    z = dl / f"python-{PY_VERSION}-embed-amd64.zip"
    if not z.exists():
        url = f"https://www.python.org/ftp/python/{PY_VERSION}/{z.name}"
        print("  내려받는 중:", url)
        urllib.request.urlretrieve(url, z)
    return z


def build(update_url: str | None = None) -> Path:
    if APP.exists():
        shutil.rmtree(APP)
    APP.mkdir(parents=True)

    print("1/5 파이썬 넣기")
    pydir = APP / "python"
    with zipfile.ZipFile(get_python()) as z:
        z.extractall(pydir)
    tag = "".join(PY_VERSION.split(".")[:2])
    (pydir / f"python{tag}._pth").write_text(
        f"python{tag}.zip\n.\nLib\\site-packages\n..\n", encoding="utf-8")

    print("2/5 패키지 넣기 (Windows용 완성본만)")
    site = pydir / "Lib" / "site-packages"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                    "--target", str(site), "--platform", "win_amd64",
                    "--python-version", ".".join(PY_VERSION.split(".")[:2]), "--implementation", "cp",
                    "--only-binary=:all:", "-r", str(ROOT / "requirements.txt")], check=True)
    shutil.rmtree(site / "bin", ignore_errors=True)

    print("3/5 서비 프로그램 넣기")
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir() or _skip(rel):
            continue
        dst = APP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel.as_posix() == "config.yaml":
            dst.write_text(_clean_config(p.read_text(encoding="utf-8"), update_url), encoding="utf-8")
        else:
            shutil.copy2(p, dst)
    (APP / "outputs").mkdir(exist_ok=True)

    # 재단 규정·서식(data/)과 인트라넷 화면은 app/ 바깥에 있습니다.
    # 설치판에서는 app 안 bundled/ 로 함께 담습니다(intranet_ui 가 양쪽을 다 찾습니다).
    repo = ROOT.parent
    for src, dst in ((repo / "data", APP / "bundled" / "data"),
                     (repo / "intranet", APP / "bundled" / "intranet")):
        if not src.exists():
            print(f"    [건너뜀] {src.name} 를 찾지 못했습니다")
            continue
        for f in sorted(src.rglob("*")):
            if not f.is_file() or any(x in f.parts for x in
                                      ("__pycache__", ".git", "운영자료", ".venv")):
                continue
            t = dst / f.relative_to(src)
            t.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, t)
        print(f"    {src.name}: {sum(1 for _ in dst.rglob('*') if _.is_file())}개 담음")

    # 처음 켤 때 파이썬이 패키지를 하나하나 번역하느라 10초 넘게 걸리지 않도록 미리 번역해 둡니다
    subprocess.run([str(pydir / "python.exe"), "-m", "compileall", "-q", str(site), str(APP / "app"), str(APP / "run.py")],
                   check=False)

    print("3.5/5 화면 위젯(Electron) 넣기")
    desk_src = ROOT / "desktop"
    if desk_src.exists() and shutil.which("npm"):
        try:
            subprocess.run(["npm", "install", "--omit=dev", "--silent"],
                           cwd=str(desk_src), check=True, shell=(sys.platform == "win32"))
            for f in sorted(desk_src.rglob("*")):
                if not f.is_file() or ".git" in f.parts:
                    continue
                t = APP / "desktop" / f.relative_to(desk_src)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
            print("    위젯 넣음")
        except Exception as exc:
            print(f"    [건너뜀] 위젯을 넣지 못했습니다: {str(exc)[:80]}")
    else:
        print("    [건너뜀] npm 이 없어 위젯을 넣지 못했습니다")

    print("4/5 설치·실행 파일 만들기")
    for name, body in [("설치하기.bat", INSTALL_BAT), ("서비 실행.bat", RUN_BAT)]:
        (APP / name).write_text(body, encoding="utf-8", newline="\r\n")

    print("5/5 압축하기")
    out = ROOT.parent / f"서비_Windows설치판_v{_version()}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(APP.rglob("*")):
            if p.is_file():
                z.write(p, Path("서비") / p.relative_to(APP))
    print(f"\n  완성: {out}  ({out.stat().st_size / 1024 / 1024:.1f} MB)")
    return out


def _version() -> str:
    m = re.search(r'VERSION = "([^"]+)"', (ROOT / "app" / "version.py").read_text(encoding="utf-8"))
    return m.group(1)


def write_manifest(zip_path: Path, base_url: str, notes: str) -> Path:
    data = zip_path.read_bytes()
    manifest = {"version": _version(), "url": base_url.rstrip("/") + "/" + quote(zip_path.name),
                "sha256": hashlib.sha256(data).hexdigest(), "size": len(data), "notes": notes,
                "released": date.today().isoformat()}
    out = zip_path.parent / "latest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  업데이트 정보: {out}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="서비 Windows 설치판 만들기")
    ap.add_argument("--update-url", help="설치판에 넣을 업데이트 주소(latest.json)")
    ap.add_argument("--release", action="store_true", help="자동 업데이트용 latest.json도 만들기")
    ap.add_argument("--base-url", help="--release: zip을 올릴 위치(폴더 주소)")
    ap.add_argument("--notes", default="", help="--release: 바뀐 점 한 줄")
    a = ap.parse_args()
    if a.release and not a.base_url:
        ap.error("--release 에는 --base-url 이 필요합니다")
    z = build(a.update_url)
    if a.release:
        write_manifest(z, a.base_url, a.notes)
