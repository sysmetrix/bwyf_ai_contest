"""서비(서무비서) 웹 서버 (FastAPI).

화면(web/)과 API(/api/...)를 함께 제공합니다. 실행: python run.py
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from urllib.parse import quote
from datetime import date, timedelta

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (FileResponse, HTMLResponse, RedirectResponse,
                               Response)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import (approval, credentials, drafter, engine, forms, helpdesk, intranet,
               intranet_ui, learning, llm, mailer, package, roles, rpa, store,
               sync, transfer, understand, updater)
from .rules import get_index, list_rule_files, warm_all
from .version import VERSION

app = FastAPI(title="서비", version=VERSION)
store.load_secrets_into_env()


@app.on_event("startup")
def _warm_rule_indexes():
    # 큰 규정 PDF를 첫 질문 때가 아니라 서버가 켜질 때 미리 읽어 둡니다
    threading.Thread(target=warm_all, args=([o["id"] for o in store.list_orgs(all_orgs=True)],), daemon=True).start()
    threading.Thread(target=updater.auto_on_startup, daemon=True).start()


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ---------- 기관 ----------
@app.get("/api/orgs")
def orgs():
    visible = store.list_orgs()
    examples = [o for o in store.list_orgs(all_orgs=True) if o["example"]]
    return {"orgs": visible, "templates": store.TEMPLATE_NAMES,
            "examples": {"total": len(examples), "hidden": len([o for o in examples if o not in visible]),
                         "show": bool(store.load_config().get("show_example_orgs"))}}


class ExampleOrgsBody(BaseModel):
    show: bool


@app.put("/api/settings/example_orgs")
def set_example_orgs(body: ExampleOrgsBody):
    store.set_show_example_orgs(body.show)
    return orgs()


# ---------- PC 옮기기(데이터 이전) ----------
@app.get("/api/transfer/export")
def transfer_export(include_keys: bool = False):
    data, name = transfer.export_bytes(include_keys)
    return Response(data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f"attachment; filename=\"seobi-data.seobi\"; filename*=UTF-8''{quote(name)}"})


@app.post("/api/transfer/import")
async def transfer_import(file: UploadFile = File(...)):
    return _guard(transfer.import_bytes, await file.read())


class NewOrg(BaseModel):
    id: str
    name: str
    template: str = "agency"


@app.post("/api/orgs")
def create_org(body: NewOrg):
    profile = _guard(store.create_org, body.id, body.name, body.template)
    from . import standard_forms
    standard_forms.generate(body.id)  # 새 기관도 바로 서식 초안을 만들 수 있게 기본 서식을 넣어 둡니다
    return store.load_profile(body.id) or profile


@app.delete("/api/orgs/{org_id}")
def delete_org(org_id: str):
    _guard(store.delete_org, org_id)
    return {"ok": True}


@app.get("/api/orgs/{org_id}/profile")
def get_profile(org_id: str):
    profile = _guard(store.load_profile, org_id)
    rule_files = _guard(list_rule_files, org_id)
    profile_path = store.org_dir(org_id) / "profile.yaml"
    profile_mtime = profile_path.stat().st_mtime if profile_path.exists() else 0
    # 공통 규정(데모 예시)은 기관이 손댈 수 없으니 빼고, 기관·부서 규정만 "바뀌었나" 비교합니다.
    changed = [f for f in rule_files if f["layer"] != "common" and f["mtime"] > profile_mtime]
    return {"profile": profile, "conflicts": drafter.check_conflicts(profile),
            "rule_files": rule_files, "rules_changed": [f["file"] for f in changed]}


class ProfileBody(BaseModel):
    profile: dict


@app.put("/api/orgs/{org_id}/profile")
def put_profile(org_id: str, body: ProfileBody):
    p = body.profile
    for key in ("org", "approval", "deadlines"):
        if not isinstance(p.get(key), dict):
            raise HTTPException(400, f"프로필에 '{key}' 항목이 없습니다")
    _guard(store.save_profile, org_id, p)
    return {"ok": True, "conflicts": drafter.check_conflicts(p)}


@app.post("/api/orgs/{org_id}/draft")
def draft_profile(org_id: str, use_model: bool = True):
    return _guard(drafter.make_draft, org_id, use_model)


@app.get("/api/tasks")
def tasks_list():
    return {"tasks": [{"id": t["id"], "name": t["name"], "category": t["category"]} for t in store.load_tasks()]}


@app.get("/api/orgs/{org_id}/tasks/{task_id}/steps")
def get_task_steps(org_id: str, task_id: str):
    tasks = {t["id"]: t for t in store.load_tasks()}
    task = tasks.get(task_id)
    if task is None:
        raise HTTPException(404, "알 수 없는 업무입니다")
    profile = _guard(store.load_profile, org_id)
    custom = (profile.get("task_overrides") or {}).get(task_id, {}).get("steps")
    return {"task_id": task_id, "name": task["name"], "default_steps": task.get("steps", []),
            "custom_steps": custom}


class TaskStepsBody(BaseModel):
    steps: list[str]


@app.put("/api/orgs/{org_id}/tasks/{task_id}/steps")
def put_task_steps(org_id: str, task_id: str, body: TaskStepsBody):
    _guard(store.save_task_steps, org_id, task_id, body.steps)
    return {"ok": True}


@app.post("/api/orgs/{org_id}/tasks/{task_id}/draft_steps")
def draft_task_steps(org_id: str, task_id: str):
    return _guard(drafter.draft_task_steps, org_id, task_id)


class ImportBody(BaseModel):
    source_dir: str


@app.post("/api/orgs/{org_id}/import")
def import_rules(org_id: str, body: ImportBody):
    return _guard(store.import_rules, org_id, body.source_dir)


@app.get("/api/orgs/{org_id}/history")
def history(org_id: str, user_id: str | None = None):
    return {"items": _guard(store.read_history, org_id, 8, user_id)}


# ---------- 담당자(개인) ----------
class UserBody(BaseModel):
    id: str | None = None
    name: str
    dept: str = ""
    email: str = ""


@app.get("/api/orgs/{org_id}/users")
def list_users(org_id: str):
    return {"users": _guard(store.list_users, org_id)}


@app.post("/api/orgs/{org_id}/users")
def add_user(org_id: str, body: UserBody):
    uid = _guard(store.save_user, org_id, body.model_dump())
    return {"id": uid}


# ---------- 내 할 일(대시보드) ----------
# ---------- 결재시스템 연결 (설치할 때 한 번) ----------

class ConnectBody(BaseModel):
    base_url: str
    mode: str = "api"         # api: 연동 API / rpa: 아이디·비밀번호로 로그인
    api_key: str = ""
    user_id: str = ""         # rpa 일 때 그룹웨어 아이디
    password: str = ""        # rpa 일 때 비밀번호. 파일에 적지 않고 저장소에 맡깁니다
    org_id: str = ""          # 결재시스템 쪽 기관 코드
    learn: bool = True        # 연결되면 바로 읽어 들일지


@app.get("/api/intranet/methods")
def intranet_methods():
    """이 PC에서 쓸 수 있는 연결 방식. 설치 화면이 이걸 보고 고르게 합니다."""
    rpa_ok, rpa_why = rpa.available()
    vault_ok, vault_why = credentials.available()
    return {
        "api": {"usable": True,
                "label": "연동 API (권장)",
                "note": "기관에서 읽기 전용 API 키를 받아 넣습니다. 화면이 바뀌어도 깨지지 않습니다."},
        "rpa": {"usable": rpa_ok, "detail": rpa_why,
                "label": "아이디·비밀번호로 로그인",
                "note": "API가 없는 그룹웨어용입니다. 사람과 똑같이 로그인해 읽고 씁니다. "
                        "그룹웨어 화면이 바뀌면 다시 맞춰야 합니다."},
        "vault": {"usable": vault_ok, "detail": vault_why},
    }


@app.post("/api/intranet/rpa/test")
def intranet_rpa_test(body: ConnectBody):
    """아이디·비밀번호로 실제 로그인이 되는지만 봅니다. 아무것도 저장하지 않습니다."""
    ok, why = rpa.available()
    if not ok:
        raise HTTPException(400, why)
    res = rpa.read_pending(body.base_url, body.user_id, body.password, headless=True)
    if not res.ok:
        raise HTTPException(400, res.error or "로그인하지 못했습니다")
    return {"ok": True, "결재대기": res.data, "seconds": round(res.seconds, 1)}


@app.get("/api/intranet/status")
def intranet_status():
    """지금 어디에 붙어 있고 무엇을 읽어 두었는지."""
    cfg = store.load_config().get("intranet") or {}
    env = cfg.get("api_key_env", "INTRANET_API_KEY")
    mode = cfg.get("mode") or "api"
    out = {"enabled": bool(cfg.get("enabled")), "base_url": cfg.get("base_url"),
           "org_id": cfg.get("org_id"), "api_key_env": env, "mode": mode,
           "user_id": cfg.get("user_id"),
           "api_key_set": store.secret_is_set(env), "reachable": False}
    if mode == "rpa":
        # 아이디·비밀번호 방식은 비밀번호가 보관돼 있으면 '닿는다'로 봅니다.
        # (확인하려고 매번 로그인하면 느리고, 계정 잠금 위험도 있습니다)
        out["password_saved"] = bool(credentials.load(cfg.get("base_url") or "",
                                                      cfg.get("user_id") or ""))
        out["reachable"] = out["password_saved"]
        return out
    if cfg.get("enabled"):
        try:
            client = intranet.IntranetClient(base_url=cfg.get("base_url"),
                                             api_key=os.environ.get(env))
            res = client._get("/api/v1/orgs")
            out["reachable"] = "error" not in res
            out["orgs"] = res.get("data") or []
        except Exception as exc:
            out["error"] = str(exc)[:160]
    return out


@app.post("/api/intranet/connect")
def intranet_connect(body: ConnectBody):
    """주소와 키를 받아 연결하고, 규정·서식·조직도를 한 번에 읽어 들입니다.

    키는 설정 파일이 아니라 .env 에 따로 둡니다(깃에 올라가지 않습니다).
    """
    base = (body.base_url or "").strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        raise HTTPException(400, "주소는 http:// 또는 https:// 로 시작해야 합니다")

    if body.mode == "rpa":
        ok, why = rpa.available()
        if not ok:
            raise HTTPException(400, why)
        if not body.user_id.strip() or not body.password:
            raise HTTPException(400, "그룹웨어 아이디와 비밀번호를 입력해 주세요")
        probe = rpa.read_pending(base, body.user_id, body.password, headless=True)
        if not probe.ok:
            raise HTTPException(400, probe.error or "로그인하지 못했습니다")
        saved, note = credentials.save(base, body.user_id, body.password)
        cfg = store.load_config()
        cfg["intranet"] = {**(cfg.get("intranet") or {}), "enabled": True, "mode": "rpa",
                           "base_url": base, "user_id": body.user_id,
                           "org_id": body.org_id.strip() or "",
                           "use_regulations": True, "use_forms": True}
        store._write_config_keep_comments(cfg)
        learned = {}
        if body.learn:
            for org in store.list_orgs():
                oid = org["id"] if isinstance(org, dict) else org
                try:
                    learned[oid] = {"users": store.sync_users_from_intranet(oid)}
                except Exception as exc:
                    learned[oid] = {"error": str(exc)[:160]}
        return {"ok": True, "mode": "rpa", "base_url": base, "user_id": body.user_id,
                "password_saved": saved, "note": note, "learned": learned}

    env = "INTRANET_API_KEY"
    if body.api_key.strip():
        _guard(store.set_secret, env, body.api_key)

    # 저장하기 전에 먼저 닿는지 봅니다.
    client = intranet.IntranetClient(base_url=base, api_key=os.environ.get(env))
    if not client.is_configured():
        raise HTTPException(400, "이 주소는 키가 필요합니다. API 키를 입력해 주세요")
    probe = client._get("/api/v1/orgs")
    if "error" in probe:
        raise HTTPException(400, f"연결하지 못했습니다: {probe['error']}")

    orgs = probe.get("data") or []
    org_code = body.org_id.strip() or (orgs[0].get("id") if orgs else "")

    cfg = store.load_config()
    cfg["intranet"] = {**(cfg.get("intranet") or {}), "enabled": True,
                       "base_url": base, "api_key_env": env, "org_id": org_code,
                       "use_regulations": True, "use_forms": True}
    store._write_config_keep_comments(cfg)

    learned = {}
    if body.learn:
        for org in store.list_orgs():
            oid = org["id"] if isinstance(org, dict) else org
            try:
                learned[oid] = {"users": store.sync_users_from_intranet(oid),
                                "documents": sync.apply(oid)}
            except Exception as exc:
                learned[oid] = {"error": str(exc)[:160]}

    return {"ok": True, "base_url": base, "org_id": org_code,
            "orgs": orgs, "learned": learned}


@app.get("/api/orgs/{org_id}/me")
def my_role(org_id: str, user_id: str | None = None):
    """내가 누구이고 무엇을 전결할 수 있는지. 전결표에서 계산한 값입니다."""
    profile = _guard(store.load_profile, org_id)
    user = _guard(store.find_user, org_id, user_id)
    return roles.authority(profile, user, store.load_tasks())


def _pending_in_mock(who: dict, profile: dict | None = None) -> list[dict]:
    """가상 결재함에서 이 사람이 결재할 문서를 고릅니다.

    결재선에는 '실장'처럼 대표 직위가 적히는데, 실장·관장·센터장은 같은 1급입니다.
    그래서 글자가 아니라 **직급**으로 맞춥니다(역할 판정과 같은 방식).
    결재선이 비어 있으면 결재자 모두에게 보여 줍니다.
    """
    profile = profile or {}
    my_rank = who.get("rank")

    def mine(label: str) -> bool:
        r = roles._approver_rank(profile, label)
        if r is not None and my_rank is not None:
            return r == my_rank
        t = (who.get("title") or "").strip()
        return bool(t) and (t in label or label in t)

    out = []
    for doc in approval.mock_documents(limit=200):
        if doc.get("state") not in ("submitted", "in_progress"):
            continue
        labels = [str(a.get("label") if isinstance(a, dict) else a)
                  for a in (doc.get("approval_line") or [])]
        if labels and not any(mine(x) for x in labels):
            continue
        out.append({
            "doc_no": doc["doc_no"], "title": doc.get("title"),
            "date": (doc.get("created") or "")[:10], "status": doc.get("state"),
            "form_title": (intranet_ui.BY_ID.get(f"form:{doc.get('form_code')}") or {}).get("title"),
            "task": doc.get("task"), "amount": doc.get("amount_won"),
            "drafter": doc.get("drafter"), "approvers": labels,
            "attachments": len(doc.get("attachments") or []),
        })
    out.sort(key=lambda d: d["doc_no"], reverse=True)
    return out


@app.get("/api/orgs/{org_id}/briefing")
def briefing(org_id: str, user_id: str | None = None):
    """화면을 열 때 먼저 보여 줄 브리핑.

    결재자면 결재할 문서를, 담당자면 내 할 일을 앞세웁니다. 규정이 바뀐 것이
    있으면 누구에게나 알립니다.
    """
    profile = _guard(store.load_profile, org_id)
    user = _guard(store.find_user, org_id, user_id)
    who = roles.authority(profile, user, store.load_tasks())

    pending = []
    reachable = True
    if who["is_approver"]:
        if intranet.is_intranet_enabled():
            # 바깥 그룹웨어에 붙여 둔 경우
            try:
                st = intranet_status()
                reachable = bool(st.get("reachable"))
                if reachable:
                    pending = intranet.fetch_pending_approvals(who.get("title"))
                    if not pending:
                        pending = intranet.fetch_pending_approvals()
            except Exception:
                reachable = False
        else:
            # 기본값: 서무비서 안의 가상 결재함(약속 v0.2)
            pending = _pending_in_mock(who, profile)

    changes = {}
    try:
        changes = sync.check(org_id)
    except Exception:
        changes = {}

    lines = []
    if who["is_approver"] and pending:
        kinds = {}
        for d in pending:
            kinds[d.get("form_title") or d.get("task") or "기안"] = \
                kinds.get(d.get("form_title") or d.get("task") or "기안", 0) + 1
        detail = ", ".join(f"{k} {v}건" for k, v in kinds.items())
        lines.append(f"결재하실 문서가 {len(pending)}건 있습니다. {detail}.")
    elif who["is_approver"] and not reachable:
        lines.append("결재시스템에 연결하지 못해 결재함을 확인하지 못했습니다.")
    elif who["is_approver"]:
        lines.append("결재를 기다리는 문서는 없습니다.")

    note = sync.message(changes) if changes else ""
    if note and not changes.get("first_time"):
        lines.append(note + " 다시 읽어 둘까요?")

    return {"me": who, "pending": pending, "changes": changes, "reachable": reachable,
            "sync_note": note, "lines": lines}


@app.post("/api/orgs/{org_id}/sync")
def sync_now(org_id: str):
    """결재시스템을 다시 읽습니다. 조직도와 바뀐 규정·서식을 반영합니다."""
    users = _guard(store.sync_users_from_intranet, org_id)
    changed = _guard(sync.apply, org_id)
    return {"users": users, "documents": changed, "note": sync.message(changed)}


@app.get("/api/orgs/{org_id}/dashboard")
def dashboard(org_id: str, user_id: str | None = None):
    items = _guard(store.open_items, org_id, user_id)
    today = date.today().isoformat()
    soon = (date.today() + timedelta(days=7)).isoformat()
    overdue = [i for i in items if i["deadline_due"] < today]
    this_week = [i for i in items if today <= i["deadline_due"] <= soon]
    recent = _guard(store.count_recent, org_id, user_id, 7)
    # 작업내역에서 다음 작업으로 바로 이어 갈 수 있게 연결 정보를 붙입니다.
    tasks = {t["id"]: t for t in store.load_tasks()}
    for it in items:
        t = tasks.get(it.get("task_id"))
        nxt = tasks.get((t or {}).get("next_task") or "")
        if nxt:
            it["next"] = {"task_id": nxt["id"], "name": nxt["name"],
                          "prompt": t.get("next_prompt") or f"{nxt['name']} 알려주세요"}
        if t:
            it["steps_left"] = t.get("next_actions") or []
    return {"open": items, "overdue": len(overdue), "this_week": len(this_week),
            "total_open": len(items), "recent_processed": recent}


@app.post("/api/orgs/{org_id}/history/{item_id}/done")
def complete_item(org_id: str, item_id: str):
    _guard(store.mark_done, org_id, item_id)
    return {"ok": True}


@app.get("/api/orgs/{org_id}/search")
def search(org_id: str, q: str, k: int = 5):
    idx = _guard(get_index, org_id)
    return {"results": [a.as_dict(s) for a, s in idx.search(q, k=k)]}


# ---------- 비서 ----------
class ChatBody(BaseModel):
    org_id: str
    message: str
    user_id: str | None = None
    fast: bool = False
    history: list[dict] = []


@app.post("/api/chat")
def chat(body: ChatBody):
    if not body.message.strip():
        raise HTTPException(400, "질문을 입력해 주세요")
    return _guard(engine.answer, body.org_id, body.message, user_id=body.user_id, ai_summary=not body.fast,
                  history=body.history[-4:])


class SummaryBody(BaseModel):
    org_id: str
    message: str
    task_id: str = ""        # 업무로 분류되지 않은 규정 질문이면 빈 값
    slots: dict = {}
    method: str | None = None


@app.post("/api/chat/summary")
def chat_summary(body: SummaryBody):
    """빠른 답(fast)을 먼저 보여 준 뒤, AI가 다듬은 안내 문장만 따로 받아 갑니다(다시 분류하지 않음)."""
    r = _guard(engine.answer, body.org_id, body.message, log=False, ai_summary=True,
               understood={"task_id": body.task_id or None, "slots": body.slots,
                           "method": body.method})
    return {"summary": r["summary"], "summary_by": r["summary_by"]}


class FormBody(BaseModel):
    org_id: str
    form_id: str
    message: str


@app.post("/api/forms/draft")
def form_draft(body: FormBody):
    result = _guard(forms.make_draft, body.org_id, body.form_id, body.message)
    result["download"] = f"/api/files?path={result['file']}"
    return result


FILE_MEDIA_TYPES = {
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".hwpx": "application/haansofthwpx",
}


@app.get("/api/files")
def download(path: str):
    p = _guard(forms.safe_output_path, path)
    return FileResponse(p, filename=p.name,
                        media_type=FILE_MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream"))


# ---------- 서식 보관함 ----------
@app.get("/api/orgs/{org_id}/forms")
def list_forms(org_id: str):
    return {"forms": _guard(store.list_org_forms, org_id)}


@app.post("/api/orgs/{org_id}/forms/defaults")
def add_default_forms(org_id: str):
    """비어 있는 업무에 서비 기본 서식을 넣습니다(이미 올린 서식은 그대로)."""
    from . import standard_forms
    created = _guard(standard_forms.generate, org_id, True)
    return {"created": created, "forms": store.list_org_forms(org_id)}


@app.post("/api/orgs/{org_id}/forms/{form_id}/file")
async def upload_form(org_id: str, form_id: str, file: UploadFile = File(...)):
    content = await file.read()
    return _guard(store.save_form_upload, org_id, form_id, file.filename or "", content)


@app.get("/api/orgs/{org_id}/forms/{form_id}/file")
def download_form_template(org_id: str, form_id: str):
    p = _guard(store.form_template_path, org_id, form_id)
    return FileResponse(p, filename=p.name,
                        media_type=FILE_MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream"))


# ---------- 모델 연결 ----------
def _models_payload(cfg: dict) -> dict:
    return {"providers": {k: {"type": v.get("type"), "base_url": v.get("base_url"),
                              "api_key_env": v.get("api_key_env"),
                              "api_key_set": store.secret_is_set(v.get("api_key_env"))}
                          for k, v in cfg.get("providers", {}).items()},
            "roles": cfg.get("roles", {})}


@app.get("/api/models")
def models():
    return _models_payload(store.load_config())


class NewProvider(BaseModel):
    name: str
    base_url: str
    api_key_env: str = ""


@app.post("/api/models/providers")
def add_provider(body: NewProvider):
    cfg = _guard(store.add_provider, body.name, body.base_url, body.api_key_env)
    return _models_payload(cfg)


@app.delete("/api/models/providers/{name}")
def delete_provider(name: str):
    cfg = _guard(store.delete_provider, name)
    return _models_payload(cfg)


class RolesBody(BaseModel):
    roles: dict
    provider_urls: dict | None = None


@app.put("/api/models")
def put_models(body: RolesBody):
    for name, url in (body.provider_urls or {}).items():
        _guard(store.save_provider_url, name, url)
    _guard(store.save_roles, body.roles)
    return models()


@app.post("/api/models/test")
def test_models():
    out = {}
    for role in store.load_config().get("roles", {}):
        if not llm.role_enabled(role):
            out[role] = {"ok": None, "message": "AI 연결 안 함(규칙 기반으로 동작)"}
            continue
        r = llm.ping(role)
        out[role] = {"ok": r.ok, "message": "연결됨" if r.ok else r.error,
                     "seconds": round(r.seconds, 2), "provider": r.provider, "model": r.model}
    return out


class FetchModelsBody(BaseModel):
    provider: str


@app.post("/api/models/fetch")
def fetch_models(body: FetchModelsBody):
    cfg = store.load_config()
    provider = cfg.get("providers", {}).get(body.provider)
    if not provider:
        raise HTTPException(400, "알 수 없는 연결입니다")
    return llm.list_models(provider)


@app.post("/api/models/auto")
def auto_detect_model():
    """이 기기에서 켜져 있는 모델 서버를 찾아 역할까지 자동으로 맞춥니다.
    키를 받지 않습니다. 인터넷에 나가지 않습니다."""
    result = llm.discover_local()
    if not result["ok"]:
        raise HTTPException(400, result["error"] or "쓸 수 있는 로컬 모델을 찾지 못했어요")
    best = next(s for s in result["servers"] if s.get("model"))
    _guard(store.upsert_provider, best["name"], best["base_url"], "")
    roles = {r: {"provider": best["name"], "model": best["model"]}
             for r in store.load_config().get("roles", {})}
    _guard(store.save_roles, roles)
    return {"ok": True, "service": best["name"], "base_url": best["base_url"],
            "model": best["model"], "roles": list(roles),
            "found": [{"name": s["name"], "models": len(s["models"]), "usable": bool(s["model"])}
                      for s in result["servers"]]}


@app.get("/api/models/local")
def list_local_servers():
    """이 기기에서 도는 모델 서버와 올라와 있는 모델 목록."""
    return llm.discover_local()


class SecretBody(BaseModel):
    env_name: str
    value: str


@app.post("/api/secrets")
def set_secret(body: SecretBody):
    _guard(store.set_secret, body.env_name, body.value)
    return {"ok": True}


@app.delete("/api/secrets/{env_name}")
def delete_secret(env_name: str):
    store.delete_secret(env_name)
    return {"ok": True}


class EvalBody(BaseModel):
    candidates: list[dict] = []   # [{"provider": "ollama", "model": "gemma3:4b"}, ...]


@app.post("/api/models/eval")
def eval_models(body: EvalBody):
    questions = store.load_eval_set()
    started = time.perf_counter()
    results = [{"name": "규칙(키워드)", **understand.eval_classifier(questions, use_model=False)}]
    for c in body.candidates[:4]:
        res = understand.eval_classifier(questions, override=c, use_model=True)
        results.append({"name": f"{c.get('provider')} · {c.get('model')}", **res})
    return {"results": results, "seconds": round(time.perf_counter() - started, 1)}


# ---------- 메일 알림(발신 전용) ----------
@app.get("/api/mail")
def mail_status():
    cfg = store.load_config().get("mail", {})
    smtp = cfg.get("providers", {}).get("smtp", {})
    return {"provider": cfg.get("provider", "none"), "enabled": mailer.enabled(),
            "smtp": {"host": smtp.get("host", ""), "port": smtp.get("port", 587),
                     "user_env": smtp.get("user_env", "MAIL_USER"), "pass_env": smtp.get("pass_env", "MAIL_PASS"),
                     "from_addr": smtp.get("from_addr", ""),
                     "user": os.environ.get(smtp.get("user_env", "MAIL_USER"), ""),
                     "pass_set": bool(os.environ.get(smtp.get("pass_env", "MAIL_PASS")))}}


class MailBody(BaseModel):
    provider: str
    smtp: dict | None = None
    user: str | None = None
    password: str | None = None


@app.put("/api/mail")
def put_mail(body: MailBody):
    mail = _guard(store.save_mail, body.provider, body.smtp)
    smtp = mail.get("providers", {}).get("smtp", {})
    if body.provider == "smtp" and (body.user or "").strip():
        _guard(store.set_secret, smtp.get("user_env") or "MAIL_USER", body.user)
    if body.provider == "smtp" and (body.password or "").strip():
        _guard(store.set_secret, smtp.get("pass_env") or "MAIL_PASS", body.password.replace(" ", ""))
    return mail_status()


class MailTestBody(BaseModel):
    to: str


@app.post("/api/mail/test")
def mail_test(body: MailTestBody):
    res = mailer.send(body.to.strip(), "[서비] 메일 연결 테스트",
                      "서비 메일 알림이 잘 연결됐어요.\n앞으로 안내 요약과 기한 알림을 이 주소로 보내 드릴게요.")
    if not res.ok:
        raise HTTPException(status_code=400, detail=res.error)
    return {"ok": True}


class NotifyBody(BaseModel):
    org_id: str
    user_id: str
    history_id: str


@app.post("/api/notify")
def notify(body: NotifyBody):
    users = {u["id"]: u for u in _guard(store.list_users, body.org_id)}
    user = users.get(body.user_id)
    if not user or not user.get("email"):
        raise HTTPException(400, "등록된 담당자 메일 주소가 없습니다")
    items = _guard(store.read_history, body.org_id, 200, body.user_id)
    item = next((i for i in items if i.get("id") == body.history_id), None)
    if not item:
        raise HTTPException(404, "처리 이력을 찾을 수 없습니다")
    lines = [f"- {a}" for a in item.get("next_actions") or []]
    if item.get("deadline_due"):
        lines.append(f"- 기한: {item['deadline_due']}까지")
    text = f"{user['name']}님,\n\n[서비] {item.get('task')} 안내 요약입니다.\n\n" + "\n".join(lines)
    res = mailer.send(user["email"], f"[서비] {item.get('task')} 안내", text)
    if not res.ok:
        raise HTTPException(400, res.error or "메일 발신에 실패했습니다")
    return {"ok": True}


# ---------- 화면 ----------


# ---------- 규정·매뉴얼 문서 ----------
@app.get("/api/orgs/{org_id}/docs")
def list_docs(org_id: str):
    return {"docs": _guard(helpdesk.list_docs, org_id)}


INLINE_TYPES = {".pdf": "application/pdf", ".md": "text/plain; charset=utf-8", ".txt": "text/plain; charset=utf-8"}


@app.get("/api/orgs/{org_id}/docs/open")
def open_doc(org_id: str, file: str):
    p = _guard(store.org_rule_file, org_id, file)
    ext = p.suffix.lower()
    if ext in INLINE_TYPES:
        return FileResponse(p, media_type=INLINE_TYPES[ext], filename=p.name, content_disposition_type="inline")
    return FileResponse(p, filename=p.name, media_type=FILE_MEDIA_TYPES.get(ext, "application/octet-stream"))


@app.post("/api/orgs/{org_id}/docs")
async def upload_doc(org_id: str, file: UploadFile = File(...), layer: str = Form("org")):
    saved = _guard(store.save_rule_upload, org_id, file.filename or "", await file.read(), layer)
    threading.Thread(target=warm_all, args=([org_id],), daemon=True).start()  # 큰 PDF는 미리 읽어 둡니다
    return saved


@app.delete("/api/orgs/{org_id}/docs")
def delete_doc(org_id: str, file: str):
    _guard(store.delete_rule_file, org_id, file)
    return {"ok": True}


# ---------- 버전·자동 업데이트 ----------
# ---------- 결재 패키지 & 전자결재 연동 ----------
# 흐름: 패키지 생성 → 사람이 확인·보정 → 인트라넷 기안 등록(임시저장)
#       → 사람이 인트라넷에서 눈으로 검증 → 상신 → 후속 업무가 할 일로 쌓임
# 서비는 스스로 상신하지 않습니다. 마지막 한 걸음은 항상 사람입니다.

class PackageBody(BaseModel):
    org_id: str
    message: str
    user_id: str | None = None
    understood: dict | None = None


@app.post("/api/packages")
def package_create(body: PackageBody):
    return _guard(package.build, body.org_id, body.message,
                  user_id=body.user_id, understood=body.understood)


@app.get("/api/orgs/{org_id}/packages")
def package_list(org_id: str):
    return {"packages": _guard(package.list_all, org_id)}


@app.get("/api/orgs/{org_id}/packages/{pkg_id}")
def package_get(org_id: str, pkg_id: str):
    return _guard(package.load, org_id, pkg_id)


class CorrectBody(BaseModel):
    changes: dict


@app.put("/api/orgs/{org_id}/packages/{pkg_id}")
def package_correct(org_id: str, pkg_id: str, body: CorrectBody):
    """사람이 확인하며 고친 값(제목·본문·결재선 등)을 반영합니다."""
    return _guard(package.correct, org_id, pkg_id, body.changes)


@app.post("/api/orgs/{org_id}/packages/{pkg_id}/ready")
def package_ready(org_id: str, pkg_id: str):
    """확인을 마쳤습니다. 이제 인트라넷으로 넘겨도 됩니다."""
    return _guard(package.set_state, org_id, pkg_id, "ready", "사람이 확인을 마침")


@app.post("/api/orgs/{org_id}/packages/{pkg_id}/attachments")
async def package_attach(org_id: str, pkg_id: str,
                         file: UploadFile = File(...), label: str = Form("")):
    """영수증·증빙을 끌어다 놓으면 붙임으로 들어갑니다."""
    data = await file.read()
    return _guard(package.add_attachment, org_id, pkg_id,
                  file.filename or "첨부", data, label.strip() or None)


class AttachRef(BaseModel):
    file: str


@app.delete("/api/orgs/{org_id}/packages/{pkg_id}/attachments")
def package_detach(org_id: str, pkg_id: str, body: AttachRef):
    return _guard(package.remove_attachment, org_id, pkg_id, body.file)


@app.post("/api/orgs/{org_id}/packages/{pkg_id}/read-receipt")
def package_read_receipt(org_id: str, pkg_id: str, body: AttachRef):
    """붙인 영수증을 이 기기의 모델로 읽어 상호·금액·날짜를 뽑습니다.
    값을 바로 반영하지 않고 돌려만 줍니다. 넣을지는 사람이 정합니다."""
    return _guard(package.read_receipt, org_id, pkg_id, body.file)


@app.get("/api/approval")
def approval_settings():
    return approval.settings()


class ApprovalProviderBody(BaseModel):
    provider: str


@app.put("/api/approval")
def approval_save(body: ApprovalProviderBody):
    return _guard(approval.save_provider, body.provider)


@app.post("/api/orgs/{org_id}/packages/{pkg_id}/send")
def approval_send(org_id: str, pkg_id: str):
    """인트라넷에 기안을 올립니다. 임시저장까지만 하고 상신하지 않습니다."""
    m = _guard(package.load, org_id, pkg_id)
    if m["state"] not in ("draft", "ready"):
        raise HTTPException(400, "이미 인트라넷으로 넘어간 건입니다")
    res = approval.send(org_id, m)
    if res.ok:
        m["intranet"] = res.as_dict()
        package.save(org_id, m)
        m = _guard(package.set_state, org_id, pkg_id, "staged",
                   f"인트라넷 기안 등록({res.provider}) 문서번호 {res.doc_no}")
    return {"result": res.as_dict(), "package": m}


@app.post("/api/orgs/{org_id}/packages/{pkg_id}/submit")
def approval_submit(org_id: str, pkg_id: str):
    """사람이 검증을 마치고 '상신'을 직접 누른 경우에만 호출됩니다."""
    m = _guard(package.load, org_id, pkg_id)
    info = m.get("intranet") or {}
    if m["state"] != "staged" or not info.get("doc_no"):
        raise HTTPException(400, "인트라넷에 올라간 기안이 아직 없습니다")
    res = approval.submit(info["doc_no"])
    if res.ok:
        m["intranet"] = {**info, **res.as_dict()}
        package.save(org_id, m)
        m = _guard(package.set_state, org_id, pkg_id, "submitted", "사람이 상신함")
    return {"result": res.as_dict(), "package": m}


@app.get("/api/approval/mock")
def approval_mock_list():
    """가상 결재함. 시연에서 '올라갔는지' 눈으로 확인하는 용도입니다."""
    return {"documents": approval.mock_documents()}


@app.get("/api/approval/mock/{doc_no}")
def approval_mock_get(doc_no: str):
    doc = approval.mock_document(doc_no)
    if not doc:
        raise HTTPException(404, "가상 결재함에 그 문서가 없습니다")
    return doc


# ---------- 인트라넷 화면 (약속 v0.2: 서무비서가 /intranet/ 으로 함께 내줍니다) ----------

@app.get("/intranet", include_in_schema=False)
def intranet_root():
    return RedirectResponse("/intranet/", status_code=307)


@app.get("/intranet/", response_class=HTMLResponse)
def intranet_page(user_id: str | None = None):
    """가상 인트라넷. 결재함은 서무비서 것을 그대로 보여 줍니다."""
    try:
        return HTMLResponse(intranet_ui.page_html(intranet_ui.member(user_id or "")))
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/intranet/state")
def intranet_state():
    """화면이 새로고침 없이 결재함을 다시 읽을 때 씁니다."""
    return {"ok": True, "state": intranet_ui.bootstrap_state()}


@app.get("/api/intranet/users")
def intranet_users():
    return {"ok": True, "data": intranet_ui.members()}


@app.get("/api/files/{file_id:path}")
def intranet_file(file_id: str):
    """인트라넷 화면이 붙임·규정 원문을 내려받는 곳입니다."""
    doc = intranet_ui.BY_ID.get(file_id)
    if doc:
        body = Path(doc["_path"]).read_bytes()
        return Response(body, media_type="text/markdown; charset=utf-8", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(doc['_name'])}"})
    f = intranet_ui.attachment_path(file_id)
    if f:
        return Response(f.read_bytes(), media_type="application/octet-stream", headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(f.name)}"})
    raise HTTPException(404, "그 파일을 찾지 못했습니다")


class ApprovalActionBody(BaseModel):
    user_id: str = ""
    action: str = "approve"      # approve / agree / reject
    comment: str = ""


@app.post("/api/approval/mock/{doc_no}/submit")
def approval_mock_submit(doc_no: str, body: ApprovalActionBody | None = None):
    """사람이 인트라넷 화면에서 상신을 누른 경우입니다."""
    res = _guard(approval.submit, doc_no)
    if not res.ok:
        raise HTTPException(400, res.error or "상신하지 못했습니다")
    doc = approval.mock_document(doc_no)
    _reflect_package(doc, "submitted")
    return doc


@app.post("/api/approval/mock/{doc_no}/actions")
def approval_mock_action(doc_no: str, body: ApprovalActionBody):
    """결재선의 승인·협조 동의·반려."""
    doc = _guard(approval.act, doc_no, body.user_id, body.action, body.comment)
    _reflect_package(doc, doc.get("state"))
    return doc


def _reflect_package(doc: dict | None, state: str | None) -> None:
    """결재함에서 일어난 일을 서무비서의 결재 패키지 상태에도 반영합니다."""
    if not doc or not doc.get("package_id"):
        return
    org_id = doc.get("org_id")
    mapping = {"submitted": "submitted", "approved": "done"}
    target = mapping.get(state or "")
    if not (org_id and target):
        return
    try:
        package.set_state(org_id, doc["package_id"], target, "인트라넷 결재함에서 처리됨")
    except Exception:
        pass


# ---------- 개인 학습 (이 PC 안에만 있습니다) ----------

@app.get("/api/orgs/{org_id}/learning")
def learning_summary(org_id: str, user_id: str | None = None):
    """무엇을 배웠는지 그대로 보여 줍니다. 사람이 확인하고 지울 수 있게."""
    return _guard(learning.summary, org_id, user_id)


@app.delete("/api/orgs/{org_id}/learning")
def learning_forget(org_id: str, user_id: str | None = None,
                    task_id: str | None = None, key: str | None = None):
    """배운 것을 지웁니다. 범위를 좁혀 하나만 지울 수도 있습니다."""
    return _guard(learning.forget, org_id, user_id, task_id, key)


@app.get("/api/version")
def version_info():
    return {"version": VERSION, "install_id": store.install_id(), **updater.status()}


@app.post("/api/update/check")
def update_check():
    return {k: v for k, v in updater.check().items() if not k.startswith("_")}


@app.post("/api/update/apply")
def update_apply():
    return _guard(updater.start)


class UpdateSettingsBody(BaseModel):
    url: str | None = None
    auto: bool | None = None


@app.put("/api/settings/update")
def update_settings(body: UpdateSettingsBody):
    return _guard(updater.save_settings, body.url, body.auto)


@app.get("/api/settings/update")
def get_update_settings():
    return updater.settings()


@app.post("/api/shutdown")
def shutdown(request: Request):
    """서비 끄기(이 PC에서 온 요청만). 작업 표시줄 아이콘·설정 화면·시작 메뉴의 '서비 끄기'가 씁니다."""
    if (request.client.host if request.client else "") not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="이 PC에서만 끌 수 있어요")
    stop = getattr(app.state, "request_shutdown", None)
    if stop:
        threading.Timer(0.5, stop).start()
    else:
        threading.Timer(0.5, lambda: os._exit(0)).start()
    return {"ok": True}


@app.middleware("http")
async def no_stale_pages(request: Request, call_next):
    # 화면(.html)은 매번 새 버전인지 확인하게 합니다. 업데이트 뒤에 예전 화면이 남아 있지 않도록.
    response = await call_next(request)
    path = request.url.path
    if path.endswith(".html") or path.endswith("/"):
        response.headers["Cache-Control"] = "no-cache"
    return response


app.mount("/", StaticFiles(directory=str(store.ROOT / "web"), html=True), name="web")
