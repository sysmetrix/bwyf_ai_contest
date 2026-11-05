"""AI 연결부(어댑터) — **이 기기 안에서 도는 모델만** 씁니다.

서무비서 본체는 이 모듈의 `chat(role, messages)`만 부르고, 어떤 모델이 연결됐는지 모릅니다.
모델을 바꿀 때는 config.yaml의 roles 설정만 바꾸면 됩니다.

- type: none  → AI를 쓰지 않음. 호출 결과는 None이고, 본체는 규칙 기반으로 처리합니다.
- type: local → 이 기기에서 도는 모델(Ollama, vLLM, llama.cpp, colibri 등).

**바깥으로 나가지 않습니다.** 기관 규정과 담당자의 질문이 외부 사업자 서버로
흘러가면 안 되기 때문에, 주소가 이 기기(127.0.0.1·localhost)가 아니면
`_assert_local()` 이 호출 자체를 막습니다. 설정을 잘못 적어도 새어 나가지 않습니다.
전송 규격은 OpenAI 호환 /v1/chat/completions 를 그대로 씁니다. 로컬 추론
서버들이 공통으로 쓰는 규격이라서지, 외부 서비스에 붙기 위한 것이 아닙니다.
"""
from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .store import load_config


# ---------- 이 기기 바깥으로 나가지 못하게 막는 문지기 ----------
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}


def is_local_url(url: str) -> bool:
    """이 기기를 가리키는 주소인지 봅니다. 아니면 쓰지 않습니다."""
    try:
        host = (urlparse(url).hostname or "").strip().lower()
    except Exception:
        return False
    if not host:
        return False
    if host in LOCAL_HOSTS or host.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _assert_local(url: str) -> str | None:
    if is_local_url(url):
        return None
    return ("이 기기 안의 모델만 쓸 수 있습니다(127.0.0.1 · localhost). "
            f"바깥 주소로는 보내지 않습니다: {url[:60]}")


@dataclass
class CallResult:
    text: str | None
    provider: str
    model: str
    ok: bool
    error: str | None = None
    seconds: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)


def _role_target(role: str, override: dict | None = None) -> tuple[dict, str, str]:
    cfg = load_config()
    target = dict(cfg.get("roles", {}).get(role, {}))
    if override:
        target.update({k: v for k, v in override.items() if v})
    provider_name = target.get("provider", "none")
    provider = cfg.get("providers", {}).get(provider_name)
    if provider is None:
        provider = {"type": "none"}
    return provider, provider_name, target.get("model", "")


def role_enabled(role: str) -> bool:
    provider, _, _ = _role_target(role)
    return provider.get("type") != "none"


def _call_raw(base_url: str, api_key: str | None, model: str, messages: list[dict], *,
              temperature: float = 0.1, max_tokens: int = 800, timeout: float = 60) -> tuple[str | None, str | None, float]:
    """주소·키·모델을 직접 받아 /chat/completions를 호출합니다. (text, error, seconds)를 돌려줍니다."""
    base_url = base_url.rstrip("/")
    blocked = _assert_local(base_url)
    if blocked:
        return None, blocked, 0.0
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "stream": False}
    started = time.perf_counter()
    try:
        resp = httpx.post(f"{base_url}/chat/completions", json=body, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"].get("content") or ""
        return _strip_think(text), None, time.perf_counter() - started
    except Exception as exc:
        return None, _short_error(exc), time.perf_counter() - started


def chat(role: str, messages: list[dict], *, override: dict | None = None,
         temperature: float = 0.1, max_tokens: int = 800, timeout: float | None = None) -> CallResult:
    """역할(role)에 연결된 모델로 대화를 보냅니다. 연결이 없거나 실패하면 text=None."""
    provider, provider_name, model = _role_target(role, override)
    ptype = provider.get("type", "none")
    if ptype == "none":
        return CallResult(None, provider_name, model, ok=False, error="AI 연결 안 함(규칙 기반)")
    if ptype not in ("local", "openai_compatible"):   # 예전 설정도 그대로 읽습니다
        return CallResult(None, provider_name, model, ok=False, error=f"지원하지 않는 유형: {ptype}")

    base_url = str(provider.get("base_url", ""))
    key_env = provider.get("api_key_env")
    api_key = None
    if key_env:
        api_key = os.environ.get(key_env)
        if not api_key:
            return CallResult(None, provider_name, model, ok=False,
                              error=f"환경변수 {key_env}에 API 키가 없습니다")

    limit = float(load_config().get("timeout_seconds", 60))
    timeout = min(limit, timeout) if timeout else limit
    text, error, seconds = _call_raw(base_url, api_key, model, messages,
                                      temperature=temperature, max_tokens=max_tokens, timeout=timeout)
    if error:
        return CallResult(None, provider_name, model, ok=False, error=error, seconds=seconds)
    return CallResult(text, provider_name, model, ok=True, seconds=seconds)


def vision(role: str, prompt: str, images_b64: list[str], *,
           max_tokens: int = 400, timeout: float | None = None) -> CallResult:
    """이미지를 함께 보냅니다(영수증·증빙 읽기).

    OpenAI 호환 규격의 `image_url` 파트를 씁니다. 전송 계층은 그대로라
    _call_raw 의 로컬 주소 검사도 그대로 걸립니다. 이미지 역시 이 기기 밖으로
    나가지 않습니다. 로컬 CPU 에서는 이미지 한 장이 수십 초 걸릴 수 있어
    기본 제한을 넉넉히 둡니다."""
    provider, provider_name, model = _role_target(role)
    if provider.get("type") not in ("local", "openai_compatible"):
        return CallResult(None, provider_name, model, ok=False, error="AI 연결 안 함(규칙 기반)")

    parts: list[dict] = [{"type": "text", "text": prompt}]
    for b64 in images_b64[:4]:                       # 한 번에 너무 많이 보내지 않습니다
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:image/*;base64,{b64}"}})

    limit = float(load_config().get("timeout_seconds", 300))
    timeout = min(limit, timeout) if timeout else max(limit, 300.0)
    text, error, seconds = _call_raw(
        str(provider.get("base_url", "")), None, model,
        [{"role": "user", "content": parts}],
        temperature=0.1, max_tokens=max_tokens, timeout=timeout)
    if error:
        return CallResult(None, provider_name, model, ok=False, error=error, seconds=seconds)
    return CallResult(text, provider_name, model, ok=True, seconds=seconds)


def probe_chat(base_url: str, api_key: str, model: str, *, timeout: float = 10.0) -> CallResult:
    """저장하기 전에, 주소·키·모델 하나를 직접 시험해 봅니다(연결 자동 인식용)."""
    text, error, seconds = _call_raw(
        base_url, api_key, model,
        [{"role": "user", "content": "연결 확인입니다. '확인'이라고만 답하세요."}],
        max_tokens=64, timeout=timeout)
    if error:
        return CallResult(None, "", model, ok=False, error=error, seconds=seconds)
    return CallResult(text, "", model, ok=True, seconds=seconds)


def ping(role: str, override: dict | None = None) -> CallResult:
    # max_tokens를 넉넉히 둡니다: 최근 "생각 후 답변" 모델은 답 앞에 보이지 않는 추론 토큰을 먼저 쓰기 때문에,
    # 너무 작으면 실제 답이 나오기 전에 토큰이 바닥나 빈 응답으로 보일 수 있습니다.
    return chat(role, [{"role": "user", "content": "연결 확인입니다. '확인'이라고만 답하세요."}],
                override=override, max_tokens=64)


def probe_models(base_url: str, api_key: str | None, *, timeout: float = 8.0) -> dict:
    """주소·키를 직접 받아 /models를 호출합니다. 성공 여부로 '이 키가 이 서비스 것인지'도 함께 확인합니다."""
    blocked = _assert_local(base_url)
    if blocked:
        return {"ok": False, "models": [], "error": blocked}
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        resp = httpx.get(f"{base_url.rstrip('/')}/models", headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        ids = sorted({m.get("id") for m in data.get("data", []) if m.get("id")})
        return {"ok": True, "models": ids, "error": None}
    except Exception as exc:
        return {"ok": False, "models": [], "error": _short_error(exc)}


def list_models(provider: dict) -> dict:
    """OpenAI 호환 API의 /models를 호출해, 그 서버에 실제로 올라와 있는 모델 목록을 가져옵니다.
    특정 회사·모델에 종속되지 않고, 연결된 서버가 '무엇을 지원하는지' 그대로 보여줍니다."""
    if provider.get("type") not in ("local", "openai_compatible"):
        return {"ok": False, "models": [], "error": "이 연결은 모델 목록을 지원하지 않습니다"}
    base_url = str(provider.get("base_url", ""))
    key_env = provider.get("api_key_env")
    api_key = None
    if key_env:
        api_key = os.environ.get(key_env)
        if not api_key:
            return {"ok": False, "models": [], "error": f"환경변수 {key_env}에 API 키가 없습니다"}
    return probe_models(base_url, api_key)


# ---------- 이 기기에서 도는 모델 찾기 ----------
# 바깥 서비스는 찾지 않습니다. 흔히 쓰는 로컬 추론 서버의 포트만 훑습니다.
LOCAL_SERVERS = [
    {"name": "ollama",  "base_url": "http://127.0.0.1:11434/v1"},
    {"name": "colibri", "base_url": "http://127.0.0.1:8010/v1"},
    {"name": "vllm",    "base_url": "http://127.0.0.1:8001/v1"},
    {"name": "llamacpp","base_url": "http://127.0.0.1:8080/v1"},
    {"name": "lmstudio","base_url": "http://127.0.0.1:1234/v1"},
]

_EXCLUDE_MODEL_RE = re.compile(
    r"(embed|rerank|tts|whisper|audio|video|image|diffusion|moderation)", re.I)
# 작고 빠른 쪽을 먼저 시도합니다. 로컬 CPU 에서는 크기가 곧 대기 시간입니다.
_SMALL_RE = re.compile(r"\b(0\.5b|1b|1\.5b|2b|3b|4b)\b", re.I)
_MID_RE = re.compile(r"\b(7b|8b|9b)\b", re.I)


def _rank_models(ids: list[str]) -> list[str]:
    usable = [m for m in ids if not _EXCLUDE_MODEL_RE.search(m)]
    return sorted(usable, key=lambda m: (
        0 if _SMALL_RE.search(m) else (1 if _MID_RE.search(m) else 2),
        len(m),
    ))


def discover_local(*, probe_timeout: float = 6.0, max_model_tries: int = 4) -> dict:
    """켜져 있는 로컬 모델 서버를 찾아 바로 쓸 수 있는 모델까지 골라 줍니다.
    인터넷에 나가지 않습니다."""
    found: list[dict] = []
    for svc in LOCAL_SERVERS:
        listing = probe_models(svc["base_url"], None, timeout=3.0)
        if not listing["ok"] or not listing["models"]:
            continue
        ranked = _rank_models(listing["models"])
        picked, tried = None, []
        for model in ranked[:max_model_tries]:
            res = probe_chat(svc["base_url"], "", model, timeout=probe_timeout)
            if res.ok:
                picked = model
                break
            tried.append(f"{model}({res.error})")
        found.append({"name": svc["name"], "base_url": svc["base_url"],
                      "models": ranked, "model": picked,
                      "error": None if picked else " · ".join(tried) or "응답하는 모델이 없습니다"})
    if not found:
        return {"ok": False, "servers": [], "error":
                "이 기기에서 켜져 있는 모델 서버를 찾지 못했어요. "
                "Ollama 를 설치해 `ollama serve` 로 띄운 뒤 다시 찾아 주세요."}
    usable = [f for f in found if f["model"]]
    return {"ok": bool(usable), "servers": found,
            "error": None if usable else "서버는 찾았지만 바로 쓸 수 있는 모델이 없습니다"}


def parse_json(text: str | None) -> dict | None:
    """모델 응답에서 첫 번째 JSON 객체를 꺼냅니다."""
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def _strip_think(text: str) -> str:
    # 일부 추론형 모델이 붙이는 <think>…</think> 제거
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()


def _short_error(exc: Exception) -> str:
    if isinstance(exc, httpx.ConnectError):
        return "모델 서버에 연결할 수 없습니다(주소·실행 여부 확인)"
    if isinstance(exc, httpx.TimeoutException):
        return "응답 시간 초과"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}: {exc.response.text[:120]}"
    return str(exc)[:160]
