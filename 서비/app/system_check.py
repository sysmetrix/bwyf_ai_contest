"""이 PC에서 서비가 제대로 돌지 미리 봅니다 — 윈도우 기준.

다른 기관 PC에 깔기 전에 "이 컴퓨터에서 돌아갈까?"를 확인할 수 있어야 합니다.
서비는 두 가지 방식으로 동작하고, 필요한 사양이 다릅니다.

  규칙 방식  AI 없이 규정을 찾아 답합니다. 거의 모든 사무용 PC에서 됩니다.
  AI 방식    이 PC 안의 모델이 문장을 다듬습니다. 메모리가 더 필요합니다.

AI가 없어도 모든 기능이 동작합니다. 문장이 조금 딱딱할 뿐입니다.
그래서 '최소'는 규칙 방식 기준이고, AI는 '권장'으로 따로 봅니다.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------- 최소·권장 사양 ----------
# 숫자는 실제로 재 본 값에서 잡았습니다.
#  - 서비 프로그램 자체는 메모리 300MB 안쪽입니다.
#  - gemma3:4b 는 4비트로 줄여도 3.3GB 를 읽어 들입니다. 윈도우와 사무용 프로그램이
#    같이 떠 있는 것을 감안해 8GB 를 AI 최소로 잡았습니다.
#  - 설치판은 압축 170MB, 풀면 약 600MB. 모델까지 받으면 4GB 를 더 씁니다.
SPEC = {
    "최소": {  # 규칙 방식. AI 없이 규정 검색·기안 작성까지 다 됩니다.
        "os": "Windows 10 64비트 이상",
        "ram_gb": 4,
        "disk_gb": 2,
        "cpu_cores": 2,
        "python": (3, 10),
        "비고": "AI 없이 규칙으로 답합니다. 모든 기능이 동작합니다.",
    },
    "권장": {  # 이 PC 안의 모델로 문장까지 다듬는 방식
        "os": "Windows 10/11 64비트",
        "ram_gb": 8,
        "disk_gb": 10,
        "cpu_cores": 4,
        "python": (3, 11),
        "모델": "gemma3:4b (약 3.3GB)",
        "비고": "메모리 16GB 이상이면 답이 눈에 띄게 빨라집니다.",
    },
    "넉넉": {
        "ram_gb": 16,
        "disk_gb": 20,
        "cpu_cores": 8,
        "모델": "gemma3:12b 등 큰 모델도 가능",
        "비고": "그래픽카드(NVIDIA 8GB 이상)가 있으면 몇 배 빨라집니다.",
    },
}

MODEL_SIZE_GB = {"gemma3:1b": 0.9, "gemma3:4b": 3.3, "gemma3:12b": 8.1,
                 "qwen3:4b": 2.6, "llama3.2:3b": 2.0}


@dataclass
class Item:
    name: str
    ok: bool
    value: str = ""
    need: str = ""
    level: str = "최소"          # 최소 / 권장
    fix: str = ""                 # 안 되면 무엇을 하면 되는지

    def as_dict(self) -> dict:
        return {"항목": self.name, "충족": self.ok, "이 PC": self.value,
                "필요": self.need, "구분": self.level, "해결": self.fix}


@dataclass
class Report:
    items: list[Item] = field(default_factory=list)
    def add(self, *a, **k) -> None: self.items.append(Item(*a, **k))

    @property
    def can_run(self) -> bool:
        return all(i.ok for i in self.items if i.level == "최소")

    @property
    def can_ai(self) -> bool:
        return self.can_run and all(i.ok for i in self.items if i.level == "권장")

    def as_dict(self) -> dict:
        lacking = [i.as_dict() for i in self.items if not i.ok]
        return {
            "돌아감": self.can_run,
            "AI까지": self.can_ai,
            "한줄": self._headline(),
            "항목": [i.as_dict() for i in self.items],
            "모자란 것": lacking,
            "사양표": SPEC,
        }

    def _headline(self) -> str:
        if not self.can_run:
            missing = ", ".join(i.name for i in self.items
                                if not i.ok and i.level == "최소")
            return f"이 PC에서는 아직 돌릴 수 없습니다 ({missing})"
        if self.can_ai:
            return "AI 문장 다듬기까지 쓸 수 있는 PC입니다"
        return "규칙 방식으로 모든 기능을 쓸 수 있습니다. AI 문장 다듬기는 어렵습니다"


# ---------- 재는 법 ----------

def _ram_gb() -> float | None:
    try:
        if hasattr(os, "sysconf") and "SC_PAGE_SIZE" in os.sysconf_names:
            return round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1)
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            class MS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MS(); m.dwLength = ctypes.sizeof(MS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return round(m.ullTotalPhys / 1e9, 1)
        except Exception:
            return None
    try:                                     # 맥
        out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
        return round(int(out.stdout.strip()) / 1e9, 1)
    except Exception:
        return None


def _free_disk_gb(path: Path) -> float | None:
    try:
        return round(shutil.disk_usage(path).free / 1e9, 1)
    except Exception:
        return None


def _ollama() -> tuple[bool, list[dict]]:
    """이 PC에 모델이 올라와 있는지. 꺼져 있으면 (False, [])."""
    try:
        import httpx
        r = httpx.get("http://127.0.0.1:11434/api/tags", timeout=3)
        r.raise_for_status()
        return True, r.json().get("models") or []
    except Exception:
        return False, []


def _browser() -> str | None:
    """아이디·비밀번호로 그룹웨어에 들어갈 때 쓰는 브라우저."""
    if sys.platform == "win32":
        for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
            if Path(p).exists():
                return Path(p).name
        return None
    for p in ("/Applications/Google Chrome.app", "/Applications/Microsoft Edge.app"):
        if Path(p).exists():
            return Path(p).name
    return None


# ---------- 점검 ----------

def check(root: Path | None = None) -> Report:
    from . import store
    root = root or store.ROOT
    r = Report()
    lo, hi = SPEC["최소"], SPEC["권장"]

    # 운영체제
    is_win = sys.platform == "win32"
    osname = f"{platform.system()} {platform.release()}"
    r.add("운영체제", True, osname, lo["os"], "최소",
          "" if is_win else "윈도우에서 쓰는 것을 기준으로 만들었습니다. 다른 OS 에서도 돌지만 위젯·RPA 는 확인이 필요합니다")

    # 64비트
    bits = platform.machine()
    r.add("64비트", sys.maxsize > 2**32, f"{bits}", "64비트", "최소",
          "32비트 윈도우에서는 돌지 않습니다")

    # 파이썬
    v = sys.version_info
    r.add("파이썬", v[:2] >= lo["python"], f"{v.major}.{v.minor}.{v.micro}",
          f"{lo['python'][0]}.{lo['python'][1]} 이상", "최소",
          "설치판을 쓰면 파이썬이 함께 들어 있어 따로 깔 필요가 없습니다")

    # 메모리
    ram = _ram_gb()
    r.add("메모리(최소)", ram is None or ram >= lo["ram_gb"],
          f"{ram}GB" if ram else "알 수 없음", f"{lo['ram_gb']}GB 이상", "최소",
          "메모리를 늘리거나, 다른 프로그램을 닫고 써 주세요")
    r.add("메모리(AI용)", ram is None or ram >= hi["ram_gb"],
          f"{ram}GB" if ram else "알 수 없음", f"{hi['ram_gb']}GB 이상", "권장",
          "메모리가 모자라면 AI 없이 규칙으로 씁니다. 기능은 모두 됩니다")

    # 저장공간
    free = _free_disk_gb(root)
    r.add("저장공간(최소)", free is None or free >= lo["disk_gb"],
          f"{free}GB 남음" if free else "알 수 없음", f"{lo['disk_gb']}GB 이상", "최소",
          "필요 없는 파일을 지워 공간을 비워 주세요")
    r.add("저장공간(AI용)", free is None or free >= hi["disk_gb"],
          f"{free}GB 남음" if free else "알 수 없음", f"{hi['disk_gb']}GB 이상", "권장",
          "AI 모델이 3~4GB 를 씁니다")

    # CPU
    cores = os.cpu_count() or 0
    r.add("CPU 코어", cores >= lo["cpu_cores"], f"{cores}코어",
          f"{lo['cpu_cores']}코어 이상", "최소", "")
    r.add("CPU 코어(AI용)", cores >= hi["cpu_cores"], f"{cores}코어",
          f"{hi['cpu_cores']}코어 이상", "권장",
          "코어가 적으면 AI 답이 느립니다. 규칙 방식은 그대로 빠릅니다")

    # 이 PC 안의 AI
    up, models = _ollama()
    names = [m.get("name", "") for m in models]
    r.add("AI 모델", up and bool(models),
          (", ".join(names) if names else ("켜져 있음(모델 없음)" if up else "없음")),
          hi["모델"], "권장",
          "ollama.com 에서 설치한 뒤 `ollama pull gemma3:4b` 를 하면 됩니다. "
          "없어도 규칙으로 모든 기능이 동작합니다")

    # 그룹웨어 자동 로그인용 브라우저
    br = _browser()
    r.add("브라우저(크롬·엣지)", bool(br), br or "없음", "크롬 또는 엣지", "권장",
          "연동 API 가 없는 그룹웨어에 아이디·비밀번호로 들어갈 때만 필요합니다")

    return r


def summary() -> dict:
    return check().as_dict()


def spec_text() -> str:
    """안내문에 그대로 쓸 수 있는 사양표."""
    lo, hi, best = SPEC["최소"], SPEC["권장"], SPEC["넉넉"]
    return (
        f"최소 — {lo['os']}, 메모리 {lo['ram_gb']}GB, 여유 공간 {lo['disk_gb']}GB, "
        f"CPU {lo['cpu_cores']}코어. {lo['비고']}\n"
        f"권장 — 메모리 {hi['ram_gb']}GB, 여유 공간 {hi['disk_gb']}GB, "
        f"CPU {hi['cpu_cores']}코어, {hi['모델']}. {hi['비고']}\n"
        f"넉넉 — 메모리 {best['ram_gb']}GB 이상. {best['비고']}"
    )
