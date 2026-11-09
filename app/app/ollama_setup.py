"""이 PC 안에서 도는 AI(Ollama)를 깔고 띄웁니다 — 윈도우 기준.

서비는 AI 없이도 다 됩니다. AI는 문장을 다듬는 데만 씁니다.
그래도 있으면 말이 부드러워지니, 사람이 따로 찾아 깔지 않게 여기서 처리합니다.

세 가지 길이 있고 위에서부터 시도합니다.

  1. 설치판에 함께 담긴 것    `서비/ollama/ollama.exe` + `서비/ollama/models/`
     관리자 권한도, 인터넷도 필요 없습니다. 압축을 풀면 끝입니다.
     기관 PC 는 설치 권한이 막혀 있는 경우가 많아 이 길을 기본으로 둡니다.
  2. 내려받아서 풀기            공식 압축본을 받아 `서비/ollama/` 에 풉니다.
     이것도 관리자 권한이 필요 없습니다. 설치 프로그램(OllamaSetup.exe)은 쓰지 않습니다.
  3. 이미 PC 에 깔려 있는 것    사람이 전에 깔아 둔 `ollama` 를 그대로 씁니다.

모델도 같은 순서입니다. 함께 담긴 것이 있으면 받지 않고 그걸 씁니다.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

from . import store

HOST = "127.0.0.1:11434"
BASE = f"http://{HOST}"

# 기본 모델. config.yaml 의 roles 가 이 이름을 가리킵니다.
DEFAULT_MODEL = "gemma3:4b"

# 공식 배포본(압축). 설치 프로그램이 아니라 풀어 쓰는 쪽을 씁니다.
RELEASE = "v0.40.15"
ZIP_NAME = "ollama-windows-amd64.zip"
# 같은 파일을 주는 자리들. 앞에서부터 해 보고 막히면 다음으로 넘어갑니다.
ZIP_URLS = (
    f"https://github.com/ollama/ollama/releases/download/{RELEASE}/{ZIP_NAME}",
    f"https://objects.githubusercontent.com/github-production-release-asset/{ZIP_NAME}",
    f"https://ollama.com/download/{ZIP_NAME}",
)
ZIP_URL = ZIP_URLS[0]


# ---------- 자리 ----------

def home() -> Path:
    """올라마를 두는 자리. 설치판이면 `서비/ollama`."""
    return store.ROOT / "ollama"


def exe() -> Path | None:
    """쓸 수 있는 ollama 실행 파일. 없으면 None."""
    name = "ollama.exe" if sys.platform == "win32" else "ollama"
    here = home() / name
    if here.exists():
        return here
    found = shutil.which("ollama")
    return Path(found) if found else None


def models_dir() -> Path | None:
    """함께 담긴 모델 자리. 있으면 올라마에게 이 자리를 쓰라고 알려 줍니다."""
    d = home() / "models"
    return d if (d / "manifests").exists() else None


def bundled_models() -> list[str]:
    """함께 담긴 모델 이름들. `registry.ollama.ai/library/gemma3/4b` → `gemma3:4b`."""
    d = models_dir()
    if not d:
        return []
    out: list[str] = []
    for f in (d / "manifests").rglob("*"):
        if not f.is_file():
            continue
        parts = f.relative_to(d / "manifests").parts
        if len(parts) >= 3:                       # registry / …namespace… / 이름 / 태그
            out.append(f"{parts[-2]}:{parts[-1]}")
    return sorted(set(out))


# ---------- 상태 ----------

def _env() -> dict[str, str]:
    env = {**os.environ, "OLLAMA_HOST": HOST}
    d = models_dir()
    if d:
        env["OLLAMA_MODELS"] = str(d)
    # 사무용 PC 기준. 모델을 메모리에 오래 붙들고 있지 않게 합니다.
    env.setdefault("OLLAMA_KEEP_ALIVE", "10m")
    env.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
    return env


def tags(timeout: float = 2.0) -> list[dict] | None:
    """돌고 있으면 올라온 모델 목록, 아니면 None."""
    try:
        import httpx
        r = httpx.get(f"{BASE}/api/tags", timeout=timeout)
        r.raise_for_status()
        return r.json().get("models") or []
    except Exception:
        return None


def state() -> dict[str, Any]:
    """화면에 그대로 보여 줄 수 있는 상태."""
    e = exe()
    up = tags()
    names = [m.get("name", "") for m in (up or [])]
    want = DEFAULT_MODEL
    ready = up is not None and any(n == want or n.startswith(want.split(":")[0] + ":") for n in names)
    return {
        "담겨 있음": bool((home() / ("ollama.exe" if sys.platform == "win32" else "ollama")).exists()),
        "깔려 있음": bool(e),
        "경로": str(e) if e else None,
        "돌고 있음": up is not None,
        "모델": names,
        "담긴 모델": bundled_models(),
        "쓸 모델": want,
        "쓸 수 있음": ready,
        "한줄": ("AI 를 쓰고 있습니다" if ready else
                 "AI 가 깔려 있는데 모델이 없습니다" if up is not None else
                 "AI 를 바로 켤 수 있습니다" if e else
                 "AI 없이 규칙으로 답하고 있습니다"),
        "작업": job(),
    }


# ---------- 띄우기 ----------

_proc: subprocess.Popen | None = None


def serve(wait: float = 25.0) -> bool:
    """올라마를 띄웁니다. 이미 돌고 있으면 그냥 True."""
    global _proc
    if tags() is not None:
        return True
    e = exe()
    if not e:
        return False
    flags = 0
    if sys.platform == "win32":                   # 검은 콘솔 창이 뜨지 않게
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        _proc = subprocess.Popen([str(e), "serve"], env=_env(), creationflags=flags,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        return False
    end = time.time() + wait
    while time.time() < end:
        if tags() is not None:
            return True
        time.sleep(0.5)
    return False


def serve_in_background() -> None:
    """서비가 켜질 때 부르는 자리. 켜지는 것을 기다리지 않습니다."""
    if not exe():
        return
    threading.Thread(target=serve, daemon=True).start()


def stop() -> None:
    """서비가 띄운 올라마만 끕니다. 사람이 깔아 둔 것은 건드리지 않습니다."""
    global _proc
    if _proc and _proc.poll() is None:
        try:
            _proc.terminate()
            _proc.wait(timeout=5)
        except Exception:
            try:
                _proc.kill()
            except Exception:
                pass
    _proc = None


# ---------- 진행 알림 ----------
# 받는 데 몇 분 걸립니다. 화면이 멈춘 것처럼 보이지 않게 진행률을 남깁니다.

_job: dict[str, Any] = {}
_lock = threading.Lock()


def job() -> dict[str, Any]:
    with _lock:
        return dict(_job)


def _say(step: str, *, pct: float | None = None, note: str = "",
         done: bool = False, error: str | None = None) -> None:
    with _lock:
        _job.update({"단계": step, "퍼센트": None if pct is None else round(pct, 1),
                     "설명": note, "끝남": done, "오류": error, "시각": time.time()})


# ---------- 내려받아 풀기 ----------

def _prepared_zip() -> Path | None:
    """사람이 미리 받아 둔 압축본 찾기. 기관 망이 막혀 있을 때 쓰는 길입니다."""
    for d in (home(), store.ROOT, store.ROOT.parent, Path.home() / "Downloads"):
        try:
            p = d / ZIP_NAME
            if p.exists() and p.stat().st_size > 50_000_000:
                return p
        except Exception:
            continue
    return None


def download(progress: Callable[[float, str], None] | None = None) -> Path:
    """올라마를 `서비/ollama` 에 풉니다. 관리자 권한이 필요 없습니다.

    먼저 **미리 받아 둔 압축본**이 있는지 봅니다. 공공기관 망에서는 GitHub
    내려받기가 막혀 있는 경우가 많습니다(504). 그때는 인터넷 되는 PC 에서
    받아 `서비\\ollama\\` 에 넣어 두면 그대로 씁니다.
    """
    import httpx

    if sys.platform != "win32":
        raise RuntimeError("윈도우용 압축본입니다. 맥에서는 ollama.com 에서 직접 받으세요")

    home().mkdir(parents=True, exist_ok=True)
    z = home() / ZIP_NAME

    local = _prepared_zip()
    if local:
        if progress:
            progress(100.0, f"받아 두신 파일을 씁니다: {local.name}")
        if local != z:
            shutil.copy2(local, z)
    else:
        tmp = home() / (ZIP_NAME + ".part")
        errs = []
        for url in ZIP_URLS:
            try:
                got, total = 0, 0
                with httpx.stream("GET", url, follow_redirects=True, timeout=60.0) as r:
                    r.raise_for_status()
                    total = int(r.headers.get("content-length") or 0)
                    with tmp.open("wb") as f:
                        for chunk in r.iter_bytes(1 << 20):
                            f.write(chunk)
                            got += len(chunk)
                            if progress and total:
                                progress(got / total * 100,
                                         f"{got/1e6:.0f} / {total/1e6:.0f} MB")
                if got < 50_000_000:
                    raise RuntimeError(f"받은 크기가 너무 작습니다 ({got/1e6:.0f}MB)")
                tmp.replace(z)
                break
            except Exception as exc:
                errs.append(f"{url.split('/')[2]}: {str(exc)[:60]}")
                tmp.unlink(missing_ok=True)
        else:
            raise RuntimeError(
                "AI 프로그램을 받지 못했습니다. 기관 망이 막고 있는 것 같습니다.\n"
                f"({' / '.join(errs)})\n"
                "인터넷 되는 PC 에서 아래 파일을 받아 "
                f"{home()} 폴더에 넣고 다시 눌러 주세요.\n{ZIP_URLS[0]}\n"
                "또는 'AI 포함 설치판' 을 받으시면 이 과정이 아예 없습니다.")

    if progress:
        progress(100.0, "푸는 중…")
    with zipfile.ZipFile(z) as zf:
        zf.extractall(home())
    z.unlink(missing_ok=True)

    got_exe = home() / "ollama.exe"
    if not got_exe.exists():
        raise RuntimeError("압축을 풀었는데 ollama.exe 가 없습니다")
    return got_exe


# ---------- 모델 ----------

def pull(model: str, progress: Callable[[float, str], None] | None = None) -> None:
    """모델을 받습니다. 함께 담겨 있으면 부를 필요가 없습니다."""
    import httpx

    with httpx.stream("POST", f"{BASE}/api/pull", json={"model": model},
                      timeout=None) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("error"):
                raise RuntimeError(str(d["error"]))
            total, done = d.get("total") or 0, d.get("completed") or 0
            if progress:
                progress(done / total * 100 if total else 0.0,
                         d.get("status", "") + (f"  {done/1e9:.1f} / {total/1e9:.1f} GB" if total else ""))


# ---------- 한 번에 ----------

def setup(model: str | None = None) -> dict[str, Any]:
    """깔기 → 띄우기 → 모델 확인까지 한 번에. 진행률은 `job()` 으로 봅니다.

    이미 되어 있는 단계는 건너뜁니다. 여러 번 불러도 괜찮습니다.
    """
    model = model or DEFAULT_MODEL
    try:
        # 1. 실행 파일
        if not exe():
            _say("AI 프로그램 받는 중", pct=0, note="처음 한 번만 받습니다")
            download(lambda p, n: _say("AI 프로그램 받는 중", pct=p, note=n))

        # 2. 띄우기
        _say("AI 켜는 중", pct=None)
        if not serve():
            raise RuntimeError("AI 를 띄우지 못했습니다")

        # 3. 모델
        names = [m.get("name", "") for m in (tags() or [])]
        head = model.split(":")[0] + ":"
        if not any(n == model or n.startswith(head) for n in names):
            if model in bundled_models():
                # 함께 담긴 것을 못 본 경우. 자리를 알려 주고 다시 띄웁니다.
                _say("담긴 모델 읽는 중", pct=None)
                stop()
                if not serve():
                    raise RuntimeError("AI 를 다시 띄우지 못했습니다")
            else:
                _say("모델 받는 중", pct=0, note=f"{model} · 3GB 가 넘어 몇 분 걸립니다")
                pull(model, lambda p, n: _say("모델 받는 중", pct=p, note=n))

        _say("끝", pct=100, note="AI 를 쓸 수 있습니다", done=True)
    except Exception as e:                        # 실패해도 서비는 규칙으로 계속 돕니다
        _say("멈춤", done=True, error=str(e))
    return job()


def setup_in_background(model: str | None = None) -> dict[str, Any]:
    """화면이 기다리지 않게 뒤에서 합니다."""
    if (job().get("단계") and not job().get("끝남")):
        return job()                              # 이미 하고 있으면 그대로
    _say("시작", pct=0)
    threading.Thread(target=setup, args=(model,), daemon=True).start()
    return job()


# ---------- 사양 ----------

def can_run(model: str | None = None) -> dict[str, Any]:
    """이 PC 메모리로 그 모델이 돌지. 모자라면 작은 것을 권합니다."""
    from . import system_check
    model = model or DEFAULT_MODEL
    ram = system_check._ram_gb()
    need = system_check.MODEL_SIZE_GB.get(model, 3.3)
    ok = ram is None or ram >= need + 3.0         # 윈도우와 사무용 프로그램 몫을 남깁니다
    alt = None
    if not ok:
        for m in ("gemma3:1b", "llama3.2:3b"):
            if ram and ram >= system_check.MODEL_SIZE_GB.get(m, 1.0) + 2.0:
                alt = m
                break
    return {"메모리 GB": ram, "모델": model, "모델 GB": need,
            "돌아감": ok, "대신 권하는 모델": alt,
            "한줄": ("괜찮습니다" if ok else
                     f"메모리가 모자랍니다. {alt} 를 권합니다" if alt else
                     "메모리가 모자랍니다. AI 없이 쓰시는 편이 낫습니다")}
