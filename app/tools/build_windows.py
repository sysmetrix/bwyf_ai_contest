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
import os
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
# 이 PC 안에서 도는 AI. 설치 프로그램이 아니라 풀어 쓰는 압축본을 담습니다.
OLLAMA_VERSION = "v0.40.15"
OLLAMA_ZIP = "ollama-windows-amd64.zip"
OLLAMA_URL = f"https://github.com/ollama/ollama/releases/download/{OLLAMA_VERSION}/{OLLAMA_ZIP}"
# 그래픽카드용 덩어리. 사무용 PC 에는 없는 장치라 빼면 1GB 넘게 줄어듭니다.
OLLAMA_DROP = ("cuda", "rocm", "hip", "mlx")
OLLAMA_MODEL = "gemma3:4b"
ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / ".cache" / "build"
APP = BUILD / "서비"
# 레포에 들어 있는 기관은 모두 넣습니다. 받는 PC 에서 바로 시연할 수 있어야 하므로,
# 예시 기관만 넣으면 실제 기관(재단) 프로필이 빠져 버립니다.
SKIP_ORGS: set[str] = set()
SKIP_DIRS = {".git", ".claude", ".pytest_cache", "__pycache__", "outputs", ".cache",
             "tests", "data_backups", "node_modules", "desktop",   # desktop 은 3.5단계에서 따로
             "ollama",                                             # ollama 는 4단계에서 따로
             ".venv", "venv", ".idea", ".vscode"}                  # 만든 PC 의 환경은 넣지 않습니다
# 만든 PC 의 개인 자료는 절대 넣지 않습니다.
SKIP_FILES = {".env", ".install_id", "server.log", "scratch_out.txt",
              "설치.bat", "설치.sh", "실행.bat", "render.yaml",
              "서비.db", "서비.db-wal", "서비.db-shm",      # 개인 데이터베이스
              "개인학습.json", "개인학습.json.migrated",     # 개인 학습
              "결재시스템지도.json", "intranet_sync.json",
              "approval_mock.json", "history.jsonl", "done.json"}

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
        if len(parts) > 2 and parts[2] in SKIP_ORGS:
            return True
        if rel.name in ("history.jsonl", "done.json", "개인학습.json",
                        "결재시스템지도.json", "intranet_sync.json") \
                or "profile_history" in parts or "packages" in parts:
            return True
    return parts[:1] == ("data",) and len(parts) > 1 and parts[1] == "orgs_deleted"


def _clean_config(text: str, update_url: str | None, *,
                  ai_model: str | None = None) -> str:
    """받는 PC용 설정: 메일 연결은 끄고, 업데이트 주소는 넣습니다.

    AI 를 함께 담았으면 그 모델을 가리켜 둡니다. 담지 않았으면 껐다가,
    처음 설정에서 'AI 켜기' 를 누르면 그때 켜집니다.
    """
    import yaml
    cfg = yaml.safe_load(text) or {}
    for role in (cfg.get("roles") or {}).values():
        if ai_model:
            role.update(provider="ollama", model=ai_model)
        else:
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


def get_ollama() -> Path:
    """윈도우용 올라마 공식 압축본. 설치 프로그램이 아니라 풀어 쓰는 쪽입니다.

    설치 프로그램(OllamaSetup.exe, 1.7GB)은 관리자 권한을 묻습니다. 기관 PC 는
    설치 권한이 막혀 있는 경우가 많아, 풀어서 바로 실행하는 압축본을 씁니다.
    """
    dl = BUILD / "download"
    dl.mkdir(parents=True, exist_ok=True)
    z = dl / OLLAMA_ZIP
    if not z.exists():
        print("  내려받는 중:", OLLAMA_URL, "(1.6GB, 한 번만)")
        urllib.request.urlretrieve(OLLAMA_URL, z)
    return z


def _manifest(models: Path, model: str) -> Path | None:
    """`manifests/.../이름/태그` 파일 찾기. 없으면 None."""
    name, _, tag = model.partition(":")
    tag = tag or "latest"
    root = models / "manifests"
    if not root.exists():
        return None
    return next((f for f in root.rglob("*")
                 if f.is_file() and f.parent.name == name and f.name == tag), None)


def _pull_into(exe: Path, models: Path, model: str) -> None:
    """방금 담은 올라마로 모델을 받아 그 자리에 바로 넣습니다."""
    import time
    import urllib.error

    models.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "OLLAMA_MODELS": str(models), "OLLAMA_HOST": "127.0.0.1:11434"}
    print(f"    {model} 받는 중 (몇 분 걸립니다)")
    srv = subprocess.Popen([str(exe), "serve"], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):                       # 떠오를 때까지
            try:
                urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2).read()
                break
            except (urllib.error.URLError, OSError):
                time.sleep(1)
        else:
            raise SystemExit("  올라마가 뜨지 않아 모델을 받지 못했습니다")
        r = subprocess.run([str(exe), "pull", model], env=env)
        if r.returncode:
            raise SystemExit(f"  {model} 을 받지 못했습니다")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=10)
        except Exception:
            srv.kill()


def put_ollama(model: str | None) -> None:
    """`서비/ollama/` 에 올라마와 모델을 담습니다. 받는 PC 는 받을 것이 없습니다."""
    dest = APP / "ollama"
    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(get_ollama()) as z:
        z.extractall(dest)
    if not (dest / "ollama.exe").exists():
        raise SystemExit("  올라마 압축본에 ollama.exe 가 없습니다")

    # 그래픽카드용 덩어리는 뺍니다. 사무용 PC 는 CPU 로 돕니다.
    dropped = 0
    for p in sorted(dest.rglob("*"), reverse=True):
        rel = str(p.relative_to(dest)).lower()
        if any(k in rel for k in OLLAMA_DROP):
            if p.is_file():
                dropped += p.stat().st_size
                p.unlink()
            elif p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    size = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file())
    print(f"    올라마 {size/1e6:.0f} MB (그래픽카드용 {dropped/1e6:.0f} MB 뺌)")

    if not model or model == "none":
        print("    모델은 넣지 않습니다 (받는 PC 에서 처음 설정 때 받습니다)")
        return

    src = Path(os.environ.get("OLLAMA_MODELS") or (Path.home() / ".ollama" / "models"))
    man = _manifest(src, model)
    if not man:
        # 이 PC 에 없으면, 방금 담은 ollama.exe 로 바로 받아 담습니다.
        # (윈도우에서 빌드할 때. 맥에서는 받아 둔 것을 씁니다)
        if sys.platform == "win32":
            src = dest / "models"
            _pull_into(dest / "ollama.exe", src, model)
            man = _manifest(src, model)
    if not man:
        raise SystemExit(f"  {model} 을 찾지 못했습니다. 먼저 `ollama pull {model}` 하세요\n"
                         f"  (찾아본 자리: {src})")

    mdest = dest / "models"
    here = src.resolve() == mdest.resolve()       # 방금 그 자리에 바로 받은 경우
    t = mdest / "manifests" / man.relative_to(src / "manifests")
    if not here:
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(man, t)

    layers = json.loads(man.read_text(encoding="utf-8"))
    total = 0
    for layer in [layers["config"]] + layers["layers"]:
        name = layer["digest"].replace(":", "-")
        b = src / "blobs" / name
        if not b.exists():
            raise SystemExit(f"  모델 조각이 없습니다: {name}")
        tb = mdest / "blobs" / name
        if not here:
            tb.parent.mkdir(parents=True, exist_ok=True)
            if not tb.exists():
                shutil.copy2(b, tb)
        total += tb.stat().st_size
    print(f"    모델 {model} {total/1e9:.2f} GB")


def build(update_url: str | None = None, *, ollama: bool = False,
          model: str | None = None) -> Path:
    if APP.exists():
        shutil.rmtree(APP)
    APP.mkdir(parents=True)

    print("1/6 파이썬 넣기")
    pydir = APP / "python"
    with zipfile.ZipFile(get_python()) as z:
        z.extractall(pydir)
    tag = "".join(PY_VERSION.split(".")[:2])
    (pydir / f"python{tag}._pth").write_text(
        f"python{tag}.zip\n.\nLib\\site-packages\n..\n", encoding="utf-8")

    print("2/6 패키지 넣기 (Windows용 완성본만)")
    site = pydir / "Lib" / "site-packages"
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "--disable-pip-version-check",
                    "--target", str(site), "--platform", "win_amd64",
                    "--python-version", ".".join(PY_VERSION.split(".")[:2]), "--implementation", "cp",
                    "--only-binary=:all:", "-r", str(ROOT / "requirements.txt")], check=True)
    shutil.rmtree(site / "bin", ignore_errors=True)

    print("3/6 서비 프로그램 넣기")
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if p.is_dir() or _skip(rel):
            continue
        dst = APP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if rel.as_posix() == "config.yaml":
            dst.write_text(_clean_config(p.read_text(encoding="utf-8"), update_url,
                                         ai_model=(model if ollama else None)), encoding="utf-8")
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

    # 처음 켤 때 파이썬이 패키지를 하나하나 번역하느라 10초 넘게 걸리지 않도록 미리 번역해 둡니다.
    # 윈도우용 python.exe 는 윈도우에서만 돌릴 수 있어, 다른 OS 에서 만들 때는 건너뜁니다
    # (건너뛰어도 동작은 같고, 받는 PC 에서 처음 켤 때만 조금 느립니다).
    if sys.platform == "win32":
        subprocess.run([str(pydir / "python.exe"), "-m", "compileall", "-q",
                        str(site), str(APP / "app"), str(APP / "run.py")], check=False)
    else:
        print("    (윈도우가 아니라 미리 번역은 건너뜁니다)")

    print("3.5/6 화면 위젯(Electron) 넣기")
    desk_src = ROOT / "desktop"
    if desk_src.exists() and shutil.which("npm"):
        try:
            # 만든 PC 에 깔린 Electron 은 그 PC 용입니다. 윈도우용을 깨끗한 자리에
            # 따로 받아서 넣습니다.
            stage = BUILD / "desktop_win"
            shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True, exist_ok=True)
            for f in ("package.json", "main.js", "preload.js"):
                if (desk_src / f).exists():
                    shutil.copy2(desk_src / f, stage / f)
            env = {**os.environ, "npm_config_platform": "win32",
                   "npm_config_arch": "x64", "npm_config_fund": "false",
                   "npm_config_audit": "false"}
            subprocess.run(["npm", "install", "--omit=dev", "--silent", "--no-package-lock"],
                           cwd=str(stage), check=True, env=env,
                           shell=(sys.platform == "win32"))
            exe = stage / "node_modules" / "electron" / "dist" / "electron.exe"
            if not exe.exists():
                raise RuntimeError("윈도우용 electron.exe 를 받지 못했습니다")
            for f in sorted(stage.rglob("*")):
                if not f.is_file():
                    continue
                t = APP / "desktop" / f.relative_to(stage)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, t)
            print("    위젯 넣음 (윈도우용 electron.exe 확인)")
        except Exception as exc:
            print(f"    [건너뜀] 위젯을 넣지 못했습니다: {str(exc)[:100]}")
    else:
        print("    [건너뜀] npm 이 없어 위젯을 넣지 못했습니다")

    print("4/6 AI(올라마) 넣기")
    if ollama:
        put_ollama(model)
    else:
        print("    [건너뜀] --ollama 를 주면 담습니다. 받는 PC 에서 처음 설정 때 받습니다")

    print("5/6 설치·실행 파일 만들기")
    for name, body in [("설치하기.bat", INSTALL_BAT), ("서비 실행.bat", RUN_BAT)]:
        (APP / name).write_text(body, encoding="utf-8", newline="\r\n")

    print("6/6 압축하기")
    tagname = "_AI포함" if ollama else ""
    out = ROOT.parent / f"서비_Windows설치판{tagname}_v{_version()}.zip"
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
    ap.add_argument("--ollama", action="store_true",
                    help="이 PC 안에서 도는 AI(올라마)와 모델을 함께 담습니다. 압축본이 커집니다")
    ap.add_argument("--model", default=OLLAMA_MODEL,
                    help=f"--ollama 와 함께 담을 모델 (기본 {OLLAMA_MODEL}, none 이면 모델 없이)")
    a = ap.parse_args()
    if a.release and not a.base_url:
        ap.error("--release 에는 --base-url 이 필요합니다")
    z = build(a.update_url, ollama=a.ollama, model=a.model)
    if a.release:
        write_manifest(z, a.base_url, a.notes)
