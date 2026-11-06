"""자동 업데이트: 인터넷에 연결돼 있으면 새 버전을 확인하고, 내려받아 설치한 뒤 다시 켭니다.

- 업데이트 주소(config.yaml의 update.url)에는 latest.json이 있어야 합니다:
    {"version": "1.2.0", "url": "https://…/서비_Windows설치판_….zip", "sha256": "…", "notes": "바뀐 점"}
  (tools/build_windows.py --release 가 이 파일을 만들어 줍니다)
- 내려받은 파일은 sha256이 맞을 때만 설치합니다(중간에 바뀐 파일 차단).
- 설치된 서비(함께 들어 있는 파이썬으로 실행 중)에서만 동작합니다. 개발 폴더는 건드리지 않습니다.
- 사용자가 만든 기관·규정·서식·설정(data, config.yaml, .env 등)은 그대로 둡니다.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path

import httpx

from . import store
from .version import VERSION

WORK = store.ROOT / ".cache" / "update"
_state: dict = {"state": "idle", "progress": 0, "error": None, "checked": None}
_lock = threading.Lock()


def _ver(v: str) -> tuple:
    return tuple(int(p) if p.isdigit() else 0 for p in str(v).strip().lstrip("v").split("."))


def installed() -> bool:
    py = store.ROOT / "python" / "python.exe"
    return py.exists() and Path(sys.executable).resolve().parent == py.parent.resolve()


def settings() -> dict:
    u = store.load_config().get("update") or {}
    return {"url": (u.get("url") or "").strip(), "auto": u.get("auto", True)}


def save_settings(url: str | None = None, auto: bool | None = None) -> dict:
    cfg = store.load_config()
    u = cfg.setdefault("update", {})
    if url is not None:
        url = url.strip()
        if url and not url.startswith("https://") and not url.startswith("http://localhost") \
                and not url.startswith("http://127.0.0.1"):
            raise ValueError("업데이트 주소는 https:// 로 시작해야 해요")
        u["url"] = url
    if auto is not None:
        u["auto"] = bool(auto)
    store._write_config_keep_comments(cfg)
    return settings()


def check() -> dict:
    s = settings()
    result = {"current": VERSION, "installed": installed(), "auto": s["auto"], "url_set": bool(s["url"]),
              "latest": None, "available": False, "notes": "", "error": None}
    if not s["url"]:
        result["error"] = "업데이트 주소가 아직 정해지지 않았어요"
    else:
        try:
            r = httpx.get(s["url"], timeout=8, follow_redirects=True)
            r.raise_for_status()
            m = r.json()
            result.update(latest=m.get("version"), notes=m.get("notes", ""),
                          available=bool(m.get("version")) and _ver(m["version"]) > _ver(VERSION))
            result["_manifest"] = m
        except Exception as exc:
            result["error"] = f"업데이트 정보를 가져오지 못했어요(인터넷 연결 확인): {str(exc)[:120]}"
    _state["checked"] = {k: v for k, v in result.items() if not k.startswith("_")}
    return result


def status() -> dict:
    return {**_state, "current": VERSION, "installed": installed()}


def start(manifest: dict | None = None) -> dict:
    """내려받기·검사를 뒤에서 시작합니다. 끝나면 설치 도우미를 띄우고 서비를 끕니다."""
    if not installed():
        raise ValueError("설치판에서만 자동 업데이트를 해요. (개발 폴더는 git으로 업데이트하세요)")
    with _lock:
        if _state["state"] in ("downloading", "restarting"):
            return status()
        if manifest is None:
            c = check()
            if c["error"]:
                raise ValueError(c["error"])
            if not c["available"]:
                raise ValueError("이미 최신 버전이에요")
            manifest = c["_manifest"]
        _state.update(state="downloading", progress=0, error=None)
    threading.Thread(target=_run, args=(manifest,), daemon=True).start()
    return status()


def _run(m: dict) -> None:
    try:
        WORK.mkdir(parents=True, exist_ok=True)
        zpath = WORK / f"seobi-{m['version']}.zip"
        h = hashlib.sha256()
        with httpx.stream("GET", m["url"], timeout=60, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length") or m.get("size") or 0)
            done = 0
            with open(zpath, "wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if total:
                        _state["progress"] = int(done * 100 / total)
        if not m.get("sha256") or h.hexdigest() != m["sha256"].lower():
            zpath.unlink(missing_ok=True)
            raise ValueError("내려받은 파일이 원본과 달라서 설치하지 않았어요(sha256 불일치)")
        out = WORK / m["version"]
        if out.exists():
            import shutil
            shutil.rmtree(out)
        with zipfile.ZipFile(zpath) as z:
            for name in z.namelist():
                if name.startswith("/") or ".." in Path(name).parts:
                    raise ValueError("업데이트 파일 안에 올바르지 않은 경로가 있어요")
            z.extractall(out)
        new_root = next((p.parent.parent for p in out.glob("*/python/python.exe")), None)
        if not new_root or not (new_root / "tools" / "install.py").exists():
            raise ValueError("업데이트 파일 구성이 올바르지 않아요")
        _state.update(state="restarting", progress=100)
        cmd = [str(new_root / "python" / "python.exe"), str(new_root / "tools" / "install.py"),
               "--apply-update", str(store.ROOT), str(os.getpid()), json.dumps(sys.argv[1:])]
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:  # 서비가 꺼질 때 설치 도우미까지 같이 꺼지지 않도록 작업 묶음(job)에서 빠져나옵니다
            subprocess.Popen(cmd, cwd=str(new_root), creationflags=flags | 0x01000000, close_fds=True)
        except OSError:  # 빠져나오기를 허용하지 않는 환경
            subprocess.Popen(cmd, cwd=str(new_root), creationflags=flags, close_fds=True)
        time.sleep(1.5)  # 화면이 '다시 켜는 중' 상태를 받아 갈 시간
        os._exit(0)
    except Exception as exc:
        _state.update(state="error", error=str(exc)[:300])


def auto_on_startup() -> None:
    """켤 때 한 번: 새 버전이 있고 자동 업데이트가 켜져 있으면 바로 설치합니다."""
    time.sleep(3)
    c = check()
    if c["available"] and c["auto"] and installed() and not c["error"]:
        try:
            start(c["_manifest"])
        except Exception as exc:
            _state.update(state="error", error=str(exc)[:300])
