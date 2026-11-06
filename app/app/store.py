"""파일 저장소: 설정, 기관 프로필, 템플릿, 처리 이력.

데이터는 모두 data/ 아래 파일로 관리합니다(데이터베이스 불필요).
  data/common/        공통 규정·업무 정의(모든 기관 공통)
  data/templates/     기관 유형별 기본 프로필
  data/orgs/<기관>/   기관 프로필, 기관 규정(rules/), 부서 보충(rules/dept/), 서식(forms/)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
COMMON = DATA / "common"
ORGS = DATA / "orgs"
TEMPLATES = DATA / "templates"
OUTPUTS = ROOT / "outputs"
CONFIG = ROOT / "config.yaml"
SECRETS = ROOT / ".env"

ORG_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
TEMPLATE_NAMES = {"agency": "출연기관형", "local": "지자체형", "central": "중앙부처형"}


def read_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def write_yaml(path: Path, data: Any, header: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    if header:
        text = header.rstrip() + "\n" + text
    path.write_text(text, encoding="utf-8")


# ---------- 설정 ----------
def load_config() -> dict:
    return read_yaml(CONFIG)


# ---------- API 키(비밀값) ----------
# 실제 키 값은 config.yaml(깃에 올라감)에 적지 않고, 깃에 올리지 않는 .env 파일에만 저장합니다.
# config.yaml에는 환경변수 "이름"만 적고, 실행 중인 서버는 이 이름으로 os.environ에서 값을 읽습니다.
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,60}$")


def _read_secrets() -> dict[str, str]:
    if not SECRETS.exists():
        return {}
    out: dict[str, str] = {}
    for line in SECRETS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def load_secrets_into_env() -> None:
    """서버 시작 시 .env의 값을 os.environ에 올립니다. 이미 터미널에서 직접 설정한 값이 있으면 그걸 우선합니다."""
    for k, v in _read_secrets().items():
        os.environ.setdefault(k, v)


def secret_is_set(env_name: str | None) -> bool:
    return bool(env_name) and bool(os.environ.get(env_name))


def set_secret(env_name: str, value: str) -> None:
    env_name = (env_name or "").strip()
    if not ENV_NAME_RE.match(env_name):
        raise ValueError("환경변수 이름은 대문자로 시작하는 영문 대문자·숫자·밑줄(2~61자)만 쓸 수 있습니다")
    value = (value or "").strip()
    if not value:
        raise ValueError("키 값을 입력해 주세요")
    if "\n" in value or "\r" in value:
        raise ValueError("키 값에 줄바꿈을 넣을 수 없습니다")
    secrets = _read_secrets()
    secrets[env_name] = value
    SECRETS.write_text("".join(f"{k}={v}\n" for k, v in secrets.items()), encoding="utf-8")
    os.environ[env_name] = value


def delete_secret(env_name: str) -> None:
    secrets = _read_secrets()
    if env_name in secrets:
        del secrets[env_name]
        SECRETS.write_text("".join(f"{k}={v}\n" for k, v in secrets.items()), encoding="utf-8")
    os.environ.pop(env_name, None)


def save_roles(roles: dict) -> dict:
    cfg = load_config()
    providers = cfg.get("providers", {})
    for role, target in roles.items():
        if role not in cfg.get("roles", {}):
            raise ValueError(f"알 수 없는 역할: {role}")
        if target.get("provider") not in providers:
            raise ValueError(f"알 수 없는 연결: {target.get('provider')}")
        cfg["roles"][role] = {"provider": target["provider"], "model": str(target.get("model", ""))}
    _write_config_keep_comments(cfg)
    return cfg


def save_provider_url(name: str, base_url: str) -> None:
    cfg = load_config()
    if name not in cfg.get("providers", {}) or cfg["providers"][name].get("type") == "none":
        raise ValueError("주소를 바꿀 수 없는 연결입니다")
    if not re.match(r"^https?://", base_url):
        raise ValueError("주소는 http:// 또는 https:// 로 시작해야 합니다")
    from .llm import is_local_url
    if not is_local_url(base_url):
        raise ValueError("이 기기 안의 모델만 연결할 수 있어요(127.0.0.1 · localhost)")
    cfg["providers"][name]["base_url"] = base_url
    _write_config_keep_comments(cfg)


PROVIDER_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,29}$")


def add_provider(name: str, base_url: str, api_key_env: str = "") -> dict:
    """이 기기에서 도는 모델 서버를 새 연결로 등록합니다(개수 제한 없음).

    바깥 주소는 받지 않습니다. 기관 규정과 담당자의 질문이 외부 사업자 서버로
    나가면 안 되기 때문에, 설정 단계에서 미리 막습니다."""
    from .llm import is_local_url

    name = (name or "").strip()
    if not PROVIDER_ID_RE.match(name):
        raise ValueError("연결 이름은 영문 소문자로 시작하는 소문자·숫자·밑줄(2~30자)만 쓸 수 있습니다")
    if not re.match(r"^https?://", base_url or ""):
        raise ValueError("주소는 http:// 또는 https:// 로 시작해야 합니다")
    if not is_local_url(base_url):
        raise ValueError("이 기기 안의 모델만 연결할 수 있어요(127.0.0.1 · localhost). "
                         "규정과 질문을 밖으로 내보내지 않기 위해서입니다")
    cfg = load_config()
    providers = cfg.setdefault("providers", {})
    if name in providers:
        raise ValueError("이미 있는 연결 이름입니다")
    providers[name] = {"type": "local", "base_url": base_url}
    _write_config_keep_comments(cfg)
    return cfg


def upsert_provider(name: str, base_url: str, api_key_env: str) -> dict:
    """이 이름의 연결이 있으면 주소·키 환경변수를 맞추고, 없으면 새로 만듭니다(키 자동 인식용)."""
    cfg = load_config()
    providers = cfg.setdefault("providers", {})
    if name in providers and providers[name].get("type") in ("local", "openai_compatible"):
        providers[name]["type"] = "local"
        providers[name]["base_url"] = base_url
        providers[name].pop("api_key_env", None)
        _write_config_keep_comments(cfg)
        return cfg
    return add_provider(name, base_url, api_key_env)


def save_mail(provider: str, smtp: dict | None = None) -> dict:
    cfg = load_config()
    mail = cfg.setdefault("mail", {"provider": "none", "providers": {"none": {"type": "none"}}})
    if provider not in mail.get("providers", {}) and provider != "smtp":
        raise ValueError("알 수 없는 메일 연결입니다")
    if provider == "smtp":
        smtp = smtp or {}
        if not smtp.get("host"):
            raise ValueError("SMTP 주소를 입력해 주세요")
        mail["providers"]["smtp"] = {
            "type": "smtp", "host": smtp.get("host", ""), "port": int(smtp.get("port") or 587),
            "user_env": smtp.get("user_env") or "MAIL_USER", "pass_env": smtp.get("pass_env") or "MAIL_PASS",
            "from_addr": smtp.get("from_addr") or "",
        }
    mail["provider"] = provider
    _write_config_keep_comments(cfg)
    return mail


def delete_provider(name: str) -> dict:
    cfg = load_config()
    providers = cfg.get("providers", {})
    if name not in providers:
        raise ValueError("없는 연결입니다")
    if providers[name].get("type") == "none":
        raise ValueError("기본 연결(연결 안 함)은 지울 수 없습니다")
    for role, target in cfg.get("roles", {}).items():
        if target.get("provider") == name:
            target["provider"] = "none"
    del providers[name]
    _write_config_keep_comments(cfg)
    return cfg


def _write_config_keep_comments(cfg: dict) -> None:
    header = ("# AI 모델 연결 설정 (화면에서 저장됨)\n"
              "# provider: none 이면 AI 없이 규칙 기반으로 동작합니다.\n"
              "# API 키는 이 파일에 적지 말고 환경변수 이름(api_key_env)만 적습니다.\n")
    write_yaml(CONFIG, cfg, header=header)


# ---------- 기관 ----------
def check_org_id(org_id: str) -> str:
    if not ORG_ID_RE.match(org_id or ""):
        raise ValueError("기관 ID는 영문 소문자·숫자·하이픈(2~40자)만 쓸 수 있습니다")
    return org_id


def org_dir(org_id: str) -> Path:
    return ORGS / check_org_id(org_id)


def list_orgs(all_orgs: bool = False) -> list[dict]:
    """기관 목록. 실제 기관이 하나라도 등록되면 예시 기관(example: true)은 목록에서 숨깁니다.
    (지우지는 않고, 설정에서 '예시 기관 보기'를 켜면 다시 보입니다)"""
    result = []
    for d in sorted(ORGS.iterdir()) if ORGS.exists() else []:
        p = d / "profile.yaml"
        if d.is_dir() and p.exists() and ORG_ID_RE.match(d.name):
            prof = read_yaml(p)
            org = prof.get("org", {})
            result.append({"id": d.name, "name": org.get("name") or d.name,
                           "type": org.get("type", ""), "example": bool(org.get("example"))})
    if all_orgs or load_config().get("show_example_orgs"):
        return result
    real = [o for o in result if not o["example"]]
    return real or result


def set_show_example_orgs(show: bool) -> None:
    cfg = load_config()
    cfg["show_example_orgs"] = bool(show)
    _write_config_keep_comments(cfg)


def load_profile(org_id: str) -> dict:
    p = org_dir(org_id) / "profile.yaml"
    if not p.exists():
        raise FileNotFoundError(f"기관 프로필이 없습니다: {org_id}")
    prof = read_yaml(p)
    prof.setdefault("org", {})["id"] = org_id
    return prof


def save_profile(org_id: str, profile: dict) -> None:
    d = org_dir(org_id)
    p = d / "profile.yaml"
    if p.exists():  # 이전 버전 보관
        hist = d / "profile_history"
        hist.mkdir(exist_ok=True)
        shutil.copy2(p, hist / f"profile_{datetime.now():%Y%m%d-%H%M%S}.yaml")
    profile.setdefault("org", {})["id"] = org_id
    write_yaml(p, profile, header="# 기관 프로필 — 관리자 화면에서 저장됨")


def save_task_steps(org_id: str, task_id: str, steps: list[str]) -> dict:
    """업무별 처리 절차를 기관 맞춤으로 덮어씁니다. 비워두면 공통 템플릿으로 돌아갑니다."""
    if task_id not in {t["id"] for t in load_tasks()}:
        raise ValueError("알 수 없는 업무입니다")
    profile = load_profile(org_id)
    overrides = profile.setdefault("task_overrides", {})
    cleaned = [s.strip() for s in steps if s and s.strip()]
    if cleaned:
        overrides.setdefault(task_id, {})["steps"] = cleaned
    else:
        overrides.pop(task_id, None)
    save_profile(org_id, profile)
    return profile


def create_org(org_id: str, name: str, template: str) -> dict:
    d = org_dir(org_id)
    if d.exists():
        raise ValueError("이미 있는 기관 ID입니다")
    if template not in TEMPLATE_NAMES:
        raise ValueError("템플릿은 agency, local, central 중 하나입니다")
    prof = read_yaml(TEMPLATES / f"{template}.yaml")
    prof["org"].update({"id": org_id, "name": name})
    (d / "rules" / "dept").mkdir(parents=True)
    (d / "forms").mkdir()
    write_yaml(d / "profile.yaml", prof, header="# 기관 프로필 — 템플릿에서 생성됨")
    return prof


def delete_org(org_id: str) -> None:
    """기관을 지웁니다. 영구 삭제 대신 보관 폴더로 옮겨 되돌릴 수 있게 합니다."""
    d = org_dir(org_id)
    if not d.exists():
        raise ValueError("없는 기관입니다")
    if len(list_orgs(all_orgs=True)) <= 1:
        raise ValueError("마지막 남은 기관은 지울 수 없습니다")
    trash = DATA / "orgs_deleted"
    trash.mkdir(exist_ok=True)
    dest = trash / f"{org_id}_{datetime.now():%Y%m%d-%H%M%S}"
    shutil.move(str(d), str(dest))


def import_rules(org_id: str, source_dir: str) -> dict:
    """원본 폴더의 규정 파일을 기관 폴더로 '복사'합니다. 원본은 읽기만 하고 바꾸지 않습니다."""
    from .docs import SUPPORTED

    src = Path(source_dir).expanduser().resolve()
    if not src.is_dir():
        raise ValueError("폴더를 찾을 수 없습니다")
    dest = org_dir(org_id) / "rules" / "imported"
    dest.mkdir(parents=True, exist_ok=True)
    if src == ROOT or ROOT in src.parents or src == dest.resolve() or dest.resolve() in src.parents:
        raise ValueError("이 프로그램 폴더나 이미 가져온 폴더는 다시 가져올 수 없습니다. 원본 규정이 있는 폴더를 선택해 주세요")
    copied, skipped = [], []
    for f in sorted(src.rglob("*")):
        if not f.is_file():
            continue
        if f.suffix.lower() in SUPPORTED:
            target = dest / f.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, target)
            copied.append(str(f.relative_to(src)))
        else:
            skipped.append(str(f.relative_to(src)))
    return {"copied": copied, "skipped": skipped, "dest": str(dest.relative_to(ROOT))}


# ---------- 담당자(개인) ----------
def users_path(org_id: str) -> Path:
    return org_dir(org_id) / "users.yaml"


def list_users(org_id: str) -> list[dict]:
    p = users_path(org_id)
    if not p.exists():
        return []
    return read_yaml(p).get("users", [])


def find_user(org_id: str, user_id: str | None) -> dict | None:
    """담당자 한 명을 찾습니다. 직급·역할을 보고 결재선을 정하는 데 씁니다."""
    if not user_id:
        return None
    for u in list_users(org_id):
        if u.get("id") == user_id:
            return u
    return None


def sync_users_from_intranet(org_id: str) -> dict:
    """결재시스템 조직도를 담당자 목록으로 가져옵니다.

    직급·직위를 사람이 적어 넣지 않게 하려는 것입니다. 역할은 이 직급과
    기관 전결표를 맞춰 서비가 스스로 판정합니다.
    """
    from . import credentials, intranet, rpa
    cfg = load_config().get("intranet") or {}

    if (cfg.get("mode") or "api") == "rpa":
        # 아이디·비밀번호로 들어가는 기관: 화면을 뒤져 조직도를 찾습니다.
        base, uid = cfg.get("base_url") or "", cfg.get("user_id") or ""
        pw = credentials.load(base, uid)
        if not pw:
            return {"ok": False, "count": 0,
                    "error": "그룹웨어 비밀번호가 보관돼 있지 않습니다. 연결 설정을 다시 해 주세요"}
        res = rpa.read_members(base, uid, pw)
        if not res.ok:
            return {"ok": False, "count": 0, "error": res.error}
        members = res.data or []
    else:
        members = intranet.fetch_org_members(org_id)

    if not members:
        return {"ok": False, "count": 0, "error": "조직도를 읽지 못했습니다"}
    users = [{"id": m.get("id"), "name": m.get("name"), "dept": m.get("dept"),
              "rank": m.get("rank"), "title": m.get("title"),
              "grade": m.get("grade"), "source": "intranet"}
             for m in members if m.get("id")]
    write_yaml(users_path(org_id), {"users": users})
    return {"ok": True, "count": len(users)}


def save_user(org_id: str, user: dict) -> str:
    """담당자를 등록하거나(같은 id면) 갱신합니다. id가 없으면 새로 만듭니다."""
    name = (user.get("name") or "").strip()
    if not name:
        raise ValueError("담당자 이름을 입력해 주세요")
    p = users_path(org_id)
    data = read_yaml(p) if p.exists() else {"users": []}
    users = data.get("users", [])
    uid = user.get("id") or uuid.uuid4().hex[:8]
    record = {"id": uid, "name": name, "dept": user.get("dept", ""), "email": user.get("email", "")}
    for i, u in enumerate(users):
        if u.get("id") == uid:
            users[i] = record
            break
    else:
        users.append(record)
    write_yaml(p, {"users": users}, header="# 담당자 목록 (관리자 화면에서 등록)")
    return uid


# ---------- 업무 정의 ----------
def load_tasks() -> list[dict]:
    return read_yaml(COMMON / "tasks.yaml").get("tasks", [])


# ---------- 서식 보관함 ----------
def list_org_forms(org_id: str) -> list[dict]:
    """서식을 연결할 수 있는 업무마다, 지금 연결된 서식(있으면)을 업무 이름·수정일과 함께 반환합니다."""
    profile = load_profile(org_id)
    slots = uploadable_form_slots()
    d = org_dir(org_id)
    out = []
    for form_id, task in slots.items():
        rel = (profile.get("forms") or {}).get(form_id)
        p = (d / rel).resolve() if rel else None
        exists = bool(rel) and d.resolve() in p.parents and p.is_file()
        out.append({
            "id": form_id, "path": rel, "exists": exists,
            "task_name": task["name"], "task_category": task["category"],
            "modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds") if exists else None,
        })
    return out


def uploadable_form_slots() -> dict[str, dict]:
    """서식을 연결할 수 있는 업무(tasks.yaml에 form이 정의된 것만)를 반환합니다."""
    return {t["form"]: t for t in load_tasks() if t.get("form")}


FORM_FILE_EXTS = (".docx", ".hwpx")


def save_form_upload(org_id: str, form_id: str, filename: str, content: bytes) -> dict:
    slots = uploadable_form_slots()
    if form_id not in slots:
        raise ValueError("이 업무에는 서식을 연결할 수 없습니다")
    ext = Path(filename.lower()).suffix
    if ext not in FORM_FILE_EXTS:
        raise ValueError("서식은 .docx 또는 .hwpx 파일만 올릴 수 있습니다")
    if len(content) > 20 * 1024 * 1024:
        raise ValueError("파일이 너무 큽니다 (20MB 이하)")
    d = org_dir(org_id)
    forms_dir = d / "forms"
    forms_dir.mkdir(exist_ok=True)
    # 확장자가 바뀌어 올라오면 이전 파일(다른 확장자)은 지워 하나만 남긴다
    for old_ext in FORM_FILE_EXTS:
        old = forms_dir / f"{form_id}{old_ext}"
        if old.exists() and old_ext != ext:
            old.unlink()
    dest = forms_dir / f"{form_id}{ext}"
    dest.write_bytes(content)

    profile = load_profile(org_id)
    profile.setdefault("forms", {})[form_id] = str(dest.relative_to(d)).replace("\\", "/")
    save_profile(org_id, profile)
    return {"id": form_id, "task_name": slots[form_id]["name"]}


def form_template_path(org_id: str, form_id: str) -> Path:
    profile = load_profile(org_id)
    rel = (profile.get("forms") or {}).get(form_id)
    if not rel:
        raise ValueError("이 기관 프로필에 연결된 서식이 없습니다")
    d = org_dir(org_id)
    p = (d / rel).resolve()
    if d.resolve() not in p.parents or not p.is_file():
        raise ValueError("서식 파일을 찾을 수 없습니다")
    return p


def load_eval_set() -> list[dict]:
    return read_yaml(COMMON / "eval_set.yaml").get("questions", [])


# ---------- 처리 이력 ----------
def append_history(org_id: str, item: dict) -> str:
    p = org_dir(org_id) / "history.jsonl"
    item = {"id": uuid.uuid4().hex[:12], "at": datetime.now().isoformat(timespec="seconds"), **item}
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item["id"]


def _read_all_history(org_id: str) -> list[dict]:
    p = org_dir(org_id) / "history.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def read_history(org_id: str, limit: int = 8, user_id: str | None = None) -> list[dict]:
    items = [h for h in reversed(_read_all_history(org_id)) if not user_id or h.get("user_id") == user_id]
    return items[:limit]


# ---------- 할 일(기한이 있는 처리 건) ----------
def done_path(org_id: str) -> Path:
    return org_dir(org_id) / "done.json"


def _done_ids(org_id: str) -> set[str]:
    p = done_path(org_id)
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return set()


def mark_done(org_id: str, item_id: str) -> None:
    done = _done_ids(org_id) | {item_id}
    done_path(org_id).write_text(json.dumps(sorted(done)), encoding="utf-8")


def open_items(org_id: str, user_id: str | None = None) -> list[dict]:
    """기한이 있고 아직 완료 처리되지 않은 안내 건을 기한 순으로 반환합니다."""
    done = _done_ids(org_id)
    items = [h for h in _read_all_history(org_id)
             if h.get("deadline_due") and h.get("id") not in done
             and (not user_id or h.get("user_id") == user_id)]
    items.sort(key=lambda h: h["deadline_due"])
    return items


def count_recent(org_id: str, user_id: str | None = None, days: int = 7) -> int:
    """최근 N일 동안 처리(질문에 응답)한 건수를 셉니다(완료 여부와 무관)."""
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    return sum(1 for h in _read_all_history(org_id)
               if h.get("at", "") >= since and (not user_id or h.get("user_id") == user_id))


# ---------- 규정·매뉴얼 문서 ----------
RULE_DOC_EXTS = {".md", ".txt", ".docx", ".hwpx", ".pdf"}
BAD_NAME_CHARS = re.compile(r'[\/:*?"<>|\x00-\x1f]')


def save_rule_upload(org_id: str, filename: str, content: bytes, layer: str = "org") -> dict:
    """규정·업무 매뉴얼 파일을 기관 규정(rules/imported) 또는 부서 보충(rules/dept)에 넣습니다."""
    if layer not in ("org", "dept"):
        raise ValueError("올릴 곳은 기관 규정(org) 또는 부서 보충(dept)입니다")
    name = BAD_NAME_CHARS.sub("_", Path(filename or "").name).strip(" .")
    ext = Path(name.lower()).suffix
    if ext == ".hwp":
        raise ValueError("옛 한글 형식(.hwp)은 읽을 수 없어요. 한글에서 'HWPX' 또는 'PDF'로 다시 저장해서 올려 주세요")
    if ext not in RULE_DOC_EXTS or not name:
        raise ValueError("PDF, HWPX, DOCX, MD, TXT 파일만 올릴 수 있어요")
    if len(content) > 200 * 1024 * 1024:
        raise ValueError("파일이 너무 큽니다 (200MB 이하)")
    folder = org_dir(org_id) / "rules" / ("imported" if layer == "org" else "dept")
    folder.mkdir(parents=True, exist_ok=True)
    dest, n = folder / name, 2
    while dest.exists():
        dest = folder / f"{Path(name).stem} ({n}){ext}"
        n += 1
    dest.write_bytes(content)
    return {"file": str(dest.relative_to(ROOT)).replace("\\", "/"), "name": dest.name, "layer": layer}


def org_rule_file(org_id: str, rel: str, allow_common: bool = True) -> Path:
    """화면에서 넘어온 파일 경로가 이 기관이 실제로 쓰는 규정 파일인지 확인하고 실제 경로를 돌려줍니다."""
    from .rules import list_rule_files
    for f in list_rule_files(org_id):
        if f["file"].replace("\\", "/") == (rel or "").replace("\\", "/"):
            if f["layer"] == "common" and not allow_common:
                raise ValueError("공통 규정은 지울 수 없어요")
            return ROOT / f["file"]
    raise ValueError("이 기관의 규정 문서가 아닙니다")


def delete_rule_file(org_id: str, rel: str) -> None:
    """지우지 않고 기관 폴더의 rules_deleted/로 옮겨 되돌릴 수 있게 합니다."""
    p = org_rule_file(org_id, rel, allow_common=False)
    trash = org_dir(org_id) / "rules_deleted"
    trash.mkdir(exist_ok=True)
    shutil.move(str(p), str(trash / f"{datetime.now():%Y%m%d-%H%M%S}_{p.name}"))


# ---------- 설치 ID ----------
INSTALL_ID = ROOT / ".install_id"


def install_id() -> str:
    """설치할 때마다 새로 생기는 번호. 화면은 이 번호가 바뀌면 소개 영상·처음 설정을 다시 보여 줍니다.
    (다시 설치·업데이트해도 유지되고, 제거 후 새로 설치하면 새 번호)"""
    try:
        v = INSTALL_ID.read_text(encoding="utf-8").strip()
        if v:
            return v
    except OSError:
        pass
    v = uuid.uuid4().hex
    INSTALL_ID.write_text(v, encoding="utf-8")
    return v
