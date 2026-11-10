"""Windows 설치/제거: 함께 들어 있는 파이썬으로 실행됩니다.

설치  : python\\python.exe tools\\install.py
제거  : python\\python.exe tools\\install.py --uninstall

설치 위치는 %LOCALAPPDATA%\\Seobi (관리자 권한 불필요).
다시 설치(업데이트)해도 사용자가 만든 기관·서식·설정(data, config.yaml, .env)은 그대로 둡니다.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
def _default_dest() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        try:
            base = str(Path.home() / "AppData" / "Local")
        except RuntimeError:  # 사용자 폴더를 알 수 없는 특이한 환경
            base = str(SRC.parent)
    return Path(base) / "Seobi"


DEST = _default_dest()
USER_DATA = {"data", "config.yaml", ".env", "outputs", "data_backups"}  # 덮어쓰지 않고, 제거할 때도 남기는 것
NAME = "서비"


def _ps(script: str, **env: str) -> str:
    """PowerShell을 실행합니다. 경로는 환경변수로 넘겨 따옴표·한글 문제를 피합니다."""
    full_env = {**os.environ, **{f"SEOBI_{k}": v for k, v in env.items()}}
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", env=full_env)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "PowerShell 오류")
    return r.stdout.strip()


def _folders() -> tuple[Path, Path]:
    out = _ps("[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
              "[Environment]::GetFolderPath('Desktop'); [Environment]::GetFolderPath('Programs')")
    desktop, programs = out.splitlines()[:2]
    return Path(desktop), Path(programs)


def _shortcut(lnk: Path, target: Path, args: str, icon: Path, desc: str, minimized: bool) -> None:
    _ps("$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:SEOBI_LNK);"
        "$s.TargetPath=$env:SEOBI_TARGET; $s.Arguments=$env:SEOBI_ARGS;"
        "$s.WorkingDirectory=$env:SEOBI_DIR; $s.IconLocation=$env:SEOBI_ICON;"
        "$s.Description=$env:SEOBI_DESC; $s.WindowStyle=[int]$env:SEOBI_STYLE; $s.Save()",
        LNK=str(lnk), TARGET=str(target), ARGS=args, DIR=str(DEST), ICON=f"{icon},0",
        DESC=desc, STYLE="7" if minimized else "1")


def _copy_program() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    for item in SRC.iterdir():
        dst = DEST / item.name
        if item.name in USER_DATA and dst.exists():
            if item.name == "data":  # 새 예시 기관·공통 규정은 추가하되 기존 파일은 그대로
                _merge_new_only(item, dst)
            continue
        if item.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)


def _merge_new_only(src: Path, dst: Path) -> None:
    # 프로그램이 주는 것(공통 규정·업무 정의·기관 유형 틀·예시 기관)은 새 버전으로 통째로 바꿉니다.
    # 예시 기관을 그대로 두면 옛 규정 파일이 새 규정과 섞이기 때문입니다. 사용자가 만든 기관은 건드리지 않습니다.
    provided = [src / "common", src / "templates"] + [d for d in (src / "orgs").glob("*") if _is_example_org(d)]
    for d in provided:
        if d.is_dir():
            target = dst / d.relative_to(src)
            shutil.rmtree(target, ignore_errors=True)
            shutil.copytree(d, target)
    for p in src.rglob("*"):
        q = dst / p.relative_to(src)
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
        elif not q.exists():
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, q)


def _is_example_org(d: Path) -> bool:
    prof = d / "profile.yaml"
    if not prof.is_file():
        return False
    for line in prof.read_text(encoding="utf-8", errors="replace").splitlines()[:12]:
        if line.strip() == "example: true":
            return True
    return False


def _stop_running_seobi() -> None:
    """켜져 있는 서비가 있으면 끕니다(파이썬 파일을 바꾸려면 꺼져 있어야 해요)."""
    import json
    import socket
    import urllib.request
    stopped = False
    for port in range(8000, 8010):
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(("127.0.0.1", port)) != 0:
                continue
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/orgs", timeout=3) as r:
                if "templates" not in json.load(r):
                    continue
            urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST"),
                                   timeout=5).read()
            stopped = True
        except Exception:
            continue
    if stopped:
        print("  켜져 있던 서비를 껐습니다.")
        time.sleep(3)  # 프로그램 파일 잠금이 풀릴 시간


def install() -> None:
    print(f"\n  {NAME} 설치를 시작합니다...\n  설치 위치: {DEST}\n")
    if SRC == DEST:
        print("  이미 설치된 폴더에서 실행했습니다. 바로가기만 다시 만듭니다.")
    else:
        _stop_running_seobi()
        _copy_program()
    py = DEST / "python" / "python.exe"
    pyw = DEST / "python" / "pythonw.exe"  # 검은 창 없이 실행
    icon = DEST / "web" / "seobi.ico"
    desktop, programs = _folders()
    _shortcut(desktop / f"{NAME}.lnk", pyw, "run.py", icon, "서무 업무 비서 서비", minimized=False)
    menu = programs / NAME
    menu.mkdir(exist_ok=True)
    _shortcut(menu / f"{NAME}.lnk", pyw, "run.py", icon, "서무 업무 비서 서비", minimized=False)
    _shortcut(menu / f"{NAME} 끄기.lnk", pyw, "run.py --stop", icon, "켜져 있는 서비 끄기", minimized=False)
    _shortcut(menu / f"{NAME} 제거.lnk", py, "tools\\install.py --uninstall", icon, "서비 제거", minimized=False)
    print("  [완료] 바탕화면과 시작 메뉴에 '서비' 아이콘을 만들었습니다.")
    print("  아이콘을 누르면 서비가 켜지고 브라우저가 열립니다.")
    print("  켜져 있는 동안은 작업 표시줄 오른쪽 아래(시계 옆)에 서비 아이콘이 있어요.")
    print("  끌 때는 그 아이콘을 오른쪽 클릭 → '서비 끄기'를 누르세요.\n")
    subprocess.Popen([str(pyw), "run.py"], cwd=str(DEST))


def uninstall() -> None:
    print(f"\n  {NAME}를 제거합니다...")
    _stop_running_seobi()
    desktop, programs = _folders()
    (desktop / f"{NAME}.lnk").unlink(missing_ok=True)
    shutil.rmtree(programs / NAME, ignore_errors=True)
    if DEST.exists():
        for item in DEST.iterdir():
            if item.name in USER_DATA:
                continue
            if item.name == "python":  # 지금 실행 중인 파이썬은 마지막에 따로 지웁니다
                continue
            shutil.rmtree(item, ignore_errors=True) if item.is_dir() else item.unlink(missing_ok=True)
        # 실행 중인 python.exe는 스스로 못 지우므로, 잠시 뒤 지우도록 예약합니다
        subprocess.Popen(f'cmd /c timeout /t 2 >nul & rmdir /s /q "{DEST / "python"}"',
                         shell=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print("  [완료] 바로가기와 프로그램을 지웠습니다.")
    print(f"  만들어 둔 기관·서식·설정은 남겨 두었습니다: {DEST}")
    print("  완전히 지우려면 위 폴더를 직접 삭제하세요.\n")


def _wait_for_exit(pid: int, timeout_ms: int = 60000) -> None:
    import ctypes
    k = ctypes.windll.kernel32
    h = k.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if h:
        k.WaitForSingleObject(h, timeout_ms)
        k.CloseHandle(h)
    time.sleep(1.0)  # 파일 잠금이 풀릴 시간


def apply_update(target: str, pid: str, run_args: str = "[]") -> None:
    """자동 업데이트: 새 버전 폴더에서 실행되어, 기존 서비가 꺼지길 기다렸다가 프로그램만 바꾸고 다시 켭니다."""
    global DEST
    DEST = Path(target)
    log = DEST / ".cache" / "update" / "update.log"
    try:
        _wait_for_exit(int(pid))
        _copy_program()
        log.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 업데이트 완료\n", encoding="utf-8")
    except Exception as exc:  # 실패해도 기존 서비는 다시 켜서 쓸 수 있게 합니다
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"{time.strftime('%Y-%m-%d %H:%M:%S')} 업데이트 실패: {exc}\n", encoding="utf-8")
    import json
    args = [a for a in json.loads(run_args or "[]") if a != "--no-browser"] + ["--no-browser"]  # 열려 있던 화면이 스스로 새로고침
    subprocess.Popen([str(DEST / "python" / "pythonw.exe"), "run.py", *args], cwd=str(DEST))


if __name__ == "__main__":
    if "--apply-update" in sys.argv:
        i = sys.argv.index("--apply-update")
        apply_update(sys.argv[i + 1], sys.argv[i + 2], sys.argv[i + 3] if len(sys.argv) > i + 3 else "[]")
        sys.exit(0)
    try:
        uninstall() if "--uninstall" in sys.argv else install()
    except Exception as exc:
        print(f"\n  [오류] {exc}\n  이 화면을 캡처해서 알려 주세요.")
        sys.exit(1)
    finally:
        try:
            input("  창을 닫으려면 Enter 키를 누르세요...")
        except EOFError:
            pass
