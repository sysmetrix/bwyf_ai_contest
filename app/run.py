"""서무비서 실행: python run.py  →  브라우저에서 http://localhost:8000

바탕화면 아이콘(pythonw.exe)으로 켜면 검은 창 없이 작업 표시줄 오른쪽 아래에 서비 아이콘으로 떠 있습니다.
  - 아이콘을 누르면 서비 화면이 열리고, 오른쪽 클릭 → '서비 끄기'로 끕니다.
  - 오류는 알림 상자로 보여 주고, 기록은 .cache/seobi.log 에 남깁니다.
python run.py --stop  : 켜져 있는 서비를 끕니다.
"""
import argparse
import json
import socket
import sys
import threading
import traceback
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HIDDEN = sys.stdout is None or Path(sys.executable).name.lower() == "pythonw.exe"  # 창 없이 켜졌는지

if HIDDEN:  # 창이 없으면 출력할 곳이 없으므로 기록 파일로 보냅니다
    (ROOT / ".cache").mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(ROOT / ".cache" / "seobi.log", "a", encoding="utf-8", buffering=1)


def _message_box(msg: str, error: bool = True) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "서비", 0x10 if error else 0x40)


def _fail(msg: str) -> None:
    print(f"\n  [실행 실패] {msg}")
    if HIDDEN:
        _message_box(f"서비를 켜지 못했어요.\n\n{msg}")
    else:  # 더블클릭으로 켰을 때 오류 창이 바로 닫히지 않도록 멈춥니다
        try:
            input("\n  창을 닫으려면 Enter 키를 누르세요...")
        except EOFError:
            pass
    sys.exit(1)


def _port_in_use(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)  # Windows는 안 쓰는 포트에 연결을 시도하면 2초씩 기다려서, 짧게 끊습니다
        return s.connect_ex(("127.0.0.1", port)) == 0


def _is_seobi(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/orgs", timeout=3) as r:
            return "templates" in json.load(r)
    except Exception:
        return False


def _stop_running(start_port: int) -> None:
    stopped = False
    for port in range(start_port, start_port + 10):
        if _port_in_use(port) and _is_seobi(port):
            try:
                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/api/shutdown", method="POST"),
                                       timeout=5).read()
                stopped = True
            except Exception:
                pass
    msg = "서비를 껐어요." if stopped else "켜져 있는 서비가 없어요."
    print(f"  {msg}")
    if HIDDEN:
        _message_box(msg, error=False)


def _run_with_tray(server, url: str) -> None:
    """서버는 뒤에서 돌리고, 작업 표시줄에 서비 아이콘을 띄웁니다."""
    try:
        import pystray
        from PIL import Image
    except ImportError:  # 아이콘 기능이 없으면 그냥 서버만 돌립니다
        server.run()
        return
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    icon = pystray.Icon("seobi", Image.open(ROOT / "web" / "seobi.ico"), "서비 — 켜져 있어요",
                        menu=pystray.Menu(
                            pystray.MenuItem("서비 열기", lambda: webbrowser.open(url), default=True),
                            pystray.MenuItem("서비 끄기", lambda ic: ic.stop())))

    def watch():  # 화면의 '서비 끄기'나 업데이트로 서버가 먼저 끝나면 아이콘도 내립니다
        t.join()
        icon.stop()

    def ready(ic):
        ic.visible = True
        threading.Thread(target=watch, daemon=True).start()
        try:
            ic.notify("작업 표시줄 오른쪽 아래 서비 아이콘을 누르면 다시 열 수 있어요.", "서비가 켜졌어요")
        except Exception:
            pass

    icon.run(setup=ready)
    server.should_exit = True
    t.join(timeout=10)


def main() -> None:
    parser = argparse.ArgumentParser(description="서무비서 실행")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않기")
    parser.add_argument("--stop", action="store_true", help="켜져 있는 서비 끄기")
    args = parser.parse_args()

    if args.stop:
        _stop_running(args.port)
        return

    if sys.version_info < (3, 10):
        _fail(f"Python 3.10 이상이 필요합니다. 지금 버전: {sys.version.split()[0]}\n"
              "  https://python.org 에서 새 버전을 설치해 주세요.")

    missing = []
    for mod, pkg in [("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("httpx", "httpx"), ("yaml", "PyYAML"),
                     ("docx", "python-docx"), ("pypdf", "pypdf"), ("multipart", "python-multipart")]:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)
    if missing:
        _fail("필요한 프로그램이 설치되지 않았습니다: " + ", ".join(missing) + "\n"
              "  먼저 '설치.bat'을 더블클릭해서 설치해 주세요.\n"
              "  (또는 이 폴더에서: python -m pip install -r requirements.txt)")

    for port in range(args.port, args.port + 10):
        if not _port_in_use(port):
            break
        if _is_seobi(port):  # 이미 켜져 있으면(아이콘을 또 누른 경우) 브라우저만 엽니다
            print(f"\n  서비가 이미 켜져 있습니다 → http://localhost:{port}")
            if not args.no_browser:
                webbrowser.open(f"http://localhost:{port}")
            return
    else:
        _fail(f"{args.port}~{args.port + 9}번 포트를 모두 다른 프로그램이 쓰고 있습니다.\n"
              f"  다른 번호로 실행하세요: python run.py --port 9000")
    if port != args.port:
        print(f"\n  {args.port}번 포트를 다른 프로그램이 쓰고 있어서 {port}번으로 엽니다.")

    import uvicorn

    url = f"http://localhost:{port}"
    if sys.platform == "win32" and not HIDDEN:
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("서비 - 이 창을 닫으면 서비가 꺼져요")
    print(f"\n  서무비서가 시작됐습니다 → {url}\n  (이 창을 닫으면 서비도 꺼집니다. 끝내려면 Ctrl+C)\n")
    if not args.no_browser:
        def open_when_ready():  # 서버가 실제로 준비되면 브라우저를 엽니다(처음 켤 때 느려도 '연결할 수 없음'이 안 뜨게)
            for _ in range(240):
                if _port_in_use(port):
                    webbrowser.open(url)
                    return
                threading.Event().wait(0.25)
        threading.Thread(target=open_when_ready, daemon=True).start()

    config = uvicorn.Config("app.main:app", host=args.host, port=port, reload=False, use_colors=not HIDDEN)
    server = uvicorn.Server(config)
    from app import main as app_main
    app_main.app.state.request_shutdown = lambda: setattr(server, "should_exit", True)
    if HIDDEN:
        _run_with_tray(server, url)
    else:
        server.run()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        _fail("예상하지 못한 오류가 났습니다. " + ("기록: .cache/seobi.log" if HIDDEN else "위의 오류 내용을 캡처해서 알려 주세요."))
