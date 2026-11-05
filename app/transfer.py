"""PC 옮기기: 지금까지의 데이터를 파일 하나(.seobi)로 내보내고, 새 PC에서 그대로 가져옵니다.

옮기는 것: 모든 기관(프로필·규정·업무 매뉴얼·서식·담당자·처리 이력·프로필 변경 기록),
          만들어 둔 서식 초안(outputs), AI·메일 연결 설정(config.yaml),
          그리고 원할 때만 API 키(.env).
가져오기 전에는 지금 PC의 데이터를 data_backups/ 에 먼저 백업합니다.
"""
from __future__ import annotations

import io
import json
import os
import re
import threading
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from . import rules, store

APP_TAG = "seobi"
FORMAT_VERSION = 1
BACKUPS = store.ROOT / "data_backups"
MAX_TOTAL_BYTES = 1024 * 1024 * 1024  # 압축을 풀었을 때 1GB까지
CACHE_RE = re.compile(r"^cache/rule_text/[0-9a-f]{40}\.txt$")


def _org_name(org_dir: Path) -> str:
    try:
        return (store.read_yaml(org_dir / "profile.yaml").get("org") or {}).get("name") or org_dir.name
    except Exception:
        return org_dir.name


def _add_tree(z: zipfile.ZipFile, folder: Path, arc_prefix: str) -> int:
    n = 0
    for p in sorted(folder.rglob("*")):
        if p.is_file():
            z.write(p, f"{arc_prefix}/{p.relative_to(folder).as_posix()}")
            n += 1
    return n


def export_bytes(include_keys: bool = False) -> tuple[bytes, str]:
    buf = io.BytesIO()
    orgs = [d for d in sorted(store.ORGS.iterdir()) if d.is_dir() and (d / "profile.yaml").exists()] \
        if store.ORGS.exists() else []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        files = 0
        for d in orgs:
            files += _add_tree(z, d, f"data/orgs/{d.name}")
            for f in (d / "rules").rglob("*") if (d / "rules").exists() else []:
                cached = rules.text_cache_path(f) if f.is_file() else None
                if cached and cached.exists():  # 새 PC에서 큰 PDF를 다시 읽지 않도록 뽑아 둔 글자도 함께
                    z.write(cached, f"cache/rule_text/{cached.name}")
        if store.OUTPUTS.exists():
            files += _add_tree(z, store.OUTPUTS, "outputs")
        if store.CONFIG.exists():
            z.write(store.CONFIG, "config.yaml")
            files += 1
        keys = include_keys and store.SECRETS.exists()
        if keys:
            z.write(store.SECRETS, ".env")
        manifest = {"app": APP_TAG, "version": FORMAT_VERSION, "created": datetime.now().isoformat(timespec="seconds"),
                    "orgs": [{"id": d.name, "name": _org_name(d)} for d in orgs], "files": files, "include_keys": keys}
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return buf.getvalue(), f"서비_데이터_{datetime.now():%Y%m%d-%H%M}.seobi"


def _safe_name(name: str) -> PurePosixPath:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name or ":" in name:
        raise ValueError(f"올바르지 않은 파일 경로가 들어 있습니다: {name}")
    return p


def _check(z: zipfile.ZipFile) -> dict:
    try:
        manifest = json.loads(z.read("manifest.json").decode("utf-8"))
    except KeyError:
        raise ValueError("서비에서 내보낸 데이터 파일이 아닙니다 (manifest.json 없음)")
    if manifest.get("app") != APP_TAG:
        raise ValueError("서비에서 내보낸 데이터 파일이 아닙니다")
    if int(manifest.get("version", 0)) > FORMAT_VERSION:
        raise ValueError("더 새 버전의 서비에서 만든 파일입니다. 이 PC의 서비를 먼저 업데이트해 주세요")
    total = 0
    for info in z.infolist():
        p = _safe_name(info.filename)
        total += info.file_size
        if info.is_dir() or p.as_posix() in ("manifest.json", "config.yaml", ".env"):
            continue
        if p.parts[0] == "outputs":
            continue
        if CACHE_RE.match(p.as_posix()):
            continue
        if p.parts[:2] == ("data", "orgs") and len(p.parts) >= 4 and store.ORG_ID_RE.match(p.parts[2]):
            continue
        raise ValueError(f"옮길 수 없는 파일이 들어 있습니다: {info.filename}")
    if total > MAX_TOTAL_BYTES:
        raise ValueError("데이터 파일이 너무 큽니다")
    return manifest


def backup_current() -> Path:
    BACKUPS.mkdir(exist_ok=True)
    data, _ = export_bytes(include_keys=True)
    out = BACKUPS / f"가져오기_전_백업_{datetime.now():%Y%m%d-%H%M%S}.seobi"
    out.write_bytes(data)
    return out


def import_bytes(raw: bytes) -> dict:
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        raise ValueError("데이터 파일을 열 수 없습니다. 서비에서 내보낸 .seobi 파일인지 확인해 주세요")
    with z:
        manifest = _check(z)
        backup = backup_current()
        org_ids = sorted({PurePosixPath(n).parts[2] for n in z.namelist() if n.startswith("data/orgs/")})
        for org_id in org_ids:  # 같은 기관은 통째로 바꿔서 지운 파일이 남지 않게 합니다
            shutil.rmtree(store.ORGS / org_id, ignore_errors=True)
        root = store.ROOT.resolve()
        for info in z.infolist():
            if info.is_dir() or info.filename == "manifest.json":
                continue
            dest = (rules.TEXT_CACHE / PurePosixPath(info.filename).name if CACHE_RE.match(info.filename)
                    else (root / info.filename).resolve())
            if not CACHE_RE.match(info.filename) and root not in dest.parents:
                raise ValueError(f"올바르지 않은 파일 경로: {info.filename}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)
        keys = ".env" in z.namelist()
    if keys:
        for k, v in store._read_secrets().items():
            os.environ[k] = v
    threading.Thread(target=rules.warm_all, args=(org_ids,), daemon=True).start()
    return {"orgs": manifest.get("orgs", []), "files": manifest.get("files"), "keys": keys,
            "created": manifest.get("created"), "backup": str(backup.relative_to(store.ROOT))}
