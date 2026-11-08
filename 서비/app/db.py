"""이 PC 안의 데이터베이스 — 파일 하나(SQLite)입니다.

서버를 따로 켜지 않습니다. 설치할 것도 없습니다. `data/서비.db` 파일 하나가
전부이고, 파이썬에 기본으로 들어 있는 기능만 씁니다. 윈도우 설치판에 동봉한
파이썬에도 들어 있어 받는 PC에서 바로 됩니다.

**무엇을 파일에 두고 무엇을 DB에 둘지**

  설정·규정은 파일        profile.yaml, tasks.yaml, data/ 의 규정·서식.
                          사람이 열어 고치고, 깃으로 함께 관리하는 것들입니다.
  쌓이는 자료는 DB        개인 학습, 업무 이력, 기억, 감사로그.
                          수가 늘어나고, 사람별로 갈라야 하고, 찾아 써야 하는 것들입니다.

이렇게 나누면 규정은 지금처럼 눈으로 보고 고칠 수 있고, 개인 자료는 사람별로
안전하게 갈라 둘 수 있습니다.

**옮기는 방식**

한 번에 갈아엎지 않습니다. 영역 하나씩 DB로 옮기고, 옮긴 뒤에도 예전 파일은
지우지 않고 남겨 둡니다(`migrated_*` 표시). 잘못되면 되돌릴 수 있어야 합니다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from . import store

DB_NAME = "서비.db"
SCHEMA_VERSION = 1

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def path() -> Path:
    return store.ROOT / "data" / DB_NAME


def connect() -> sqlite3.Connection:
    """연결 하나를 돌려씁니다. 여러 곳에서 동시에 써도 되게 잠금을 씁니다."""
    global _conn
    with _lock:
        if _conn is None:
            path().parent.mkdir(parents=True, exist_ok=True)
            _conn = sqlite3.connect(str(path()), check_same_thread=False)
            _conn.row_factory = sqlite3.Row
            # 쓰기 중에도 읽을 수 있게. 갑자기 꺼져도 자료가 덜 깨집니다.
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA foreign_keys=ON")
            _conn.execute("PRAGMA busy_timeout=5000")
            _migrate(_conn)
        return _conn


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    """한 덩어리로 쓰고, 중간에 잘못되면 통째로 되돌립니다."""
    c = connect()
    with _lock:
        try:
            yield c
            c.commit()
        except Exception:
            c.rollback()
            raise


# ---------- 표 만들기 ----------
# 바꿀 때는 새 번호를 붙여 아래에 덧붙입니다. 이미 깔린 PC 도 켤 때 알아서 따라옵니다.

MIGRATIONS: list[tuple[int, str]] = [
    (1, """
    -- 사람. 조직도에서 읽어 오거나 사람이 등록합니다.
    CREATE TABLE IF NOT EXISTS users (
        org_id   TEXT NOT NULL,
        user_id  TEXT NOT NULL,
        name     TEXT,
        dept     TEXT,
        title    TEXT,            -- 직위 (센터장, 부장 …)
        rank     INTEGER,         -- 직급 (0 대표이사 … 5 직원)
        grade    TEXT,
        source   TEXT,            -- intranet / rpa / 사람이 등록
        updated  TEXT,
        PRIMARY KEY (org_id, user_id)
    );

    -- 개인 학습. 사람·업무·항목마다 어떤 값을 몇 번 썼는지.
    CREATE TABLE IF NOT EXISTS learning (
        org_id   TEXT NOT NULL,
        user_id  TEXT NOT NULL,
        task_id  TEXT NOT NULL,
        field    TEXT NOT NULL,   -- destination, item, approval_line …
        value    TEXT NOT NULL,
        score    INTEGER NOT NULL DEFAULT 1,   -- 그냥 쓰면 1, 사람이 고치면 2
        last_at  TEXT,
        PRIMARY KEY (org_id, user_id, task_id, field, value)
    );

    -- 마지막으로 올린 건. "지난번처럼" 에 씁니다.
    CREATE TABLE IF NOT EXISTS last_use (
        org_id   TEXT NOT NULL,
        user_id  TEXT NOT NULL,
        task_id  TEXT NOT NULL,
        payload  TEXT NOT NULL,   -- JSON
        at       TEXT,
        PRIMARY KEY (org_id, user_id, task_id)
    );

    -- 그 사람이 쓰는 말투. 쓸수록 넓어집니다.
    CREATE TABLE IF NOT EXISTS phrases (
        org_id   TEXT NOT NULL,
        user_id  TEXT NOT NULL,
        kind     TEXT NOT NULL,   -- '지난번' 등
        phrase   TEXT NOT NULL,
        count    INTEGER NOT NULL DEFAULT 1,
        last_at  TEXT,
        PRIMARY KEY (org_id, user_id, kind, phrase)
    );

    -- 업무 이력. 물어본 것과 처리 기한.
    CREATE TABLE IF NOT EXISTS work_history (
        id        TEXT PRIMARY KEY,
        org_id    TEXT NOT NULL,
        user_id   TEXT,
        task_id   TEXT,
        task_name TEXT,
        message   TEXT,
        deadline_label TEXT,
        deadline_due   TEXT,
        package_id     TEXT,
        done_at   TEXT,
        at        TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS ix_hist_org_user
        ON work_history(org_id, user_id, deadline_due);

    -- 장기 기억. 사람이 확인하고 승인한 것만 씁니다.
    CREATE TABLE IF NOT EXISTS memories (
        id        TEXT PRIMARY KEY,
        org_id    TEXT NOT NULL,
        user_id   TEXT,            -- 비어 있으면 기관 공통
        kind      TEXT NOT NULL,   -- 업무스타일 / 문서작성 / 부서지식 …
        content   TEXT NOT NULL,
        source    TEXT,
        task_id   TEXT,
        confidence REAL DEFAULT 0.5,
        approved  INTEGER DEFAULT 0,
        scope     TEXT DEFAULT 'private',   -- private / dept / org
        keep_until TEXT,
        created   TEXT NOT NULL,
        updated   TEXT
    );
    CREATE INDEX IF NOT EXISTS ix_mem_org_user ON memories(org_id, user_id, kind);

    -- 감사로그. 누가 언제 무엇을 했는지.
    CREATE TABLE IF NOT EXISTS audit_logs (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        at      TEXT NOT NULL,
        org_id  TEXT,
        user_id TEXT,
        action  TEXT NOT NULL,
        target  TEXT,
        detail  TEXT,
        ok      INTEGER DEFAULT 1
    );
    CREATE INDEX IF NOT EXISTS ix_audit_at ON audit_logs(at);
    """),
]


def _migrate(c: sqlite3.Connection) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY, at TEXT)")
    row = c.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
    now = row["v"] if row and row["v"] is not None else 0
    for ver, sql in MIGRATIONS:
        if ver > now:
            c.executescript(sql)
            c.execute("INSERT INTO schema_version(version, at) VALUES (?,?)",
                      (ver, datetime.now().isoformat(timespec="seconds")))
    c.commit()


# ---------- 자주 쓰는 것 ----------

def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def log(action: str, *, org_id: str | None = None, user_id: str | None = None,
        target: str | None = None, detail: Any = None, ok: bool = True) -> None:
    """감사로그 한 줄. 실패해도 본 작업을 막지 않습니다."""
    try:
        with tx() as c:
            c.execute(
                "INSERT INTO audit_logs(at, org_id, user_id, action, target, detail, ok)"
                " VALUES (?,?,?,?,?,?,?)",
                (now(), org_id, user_id, action, target,
                 json.dumps(detail, ensure_ascii=False) if detail is not None else None,
                 1 if ok else 0))
    except Exception:
        pass


def recent_logs(limit: int = 50, org_id: str | None = None) -> list[dict]:
    c = connect()
    sql = "SELECT * FROM audit_logs"
    args: list[Any] = []
    if org_id:
        sql += " WHERE org_id = ?"
        args.append(org_id)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in c.execute(sql, args)]


def info() -> dict:
    """화면에 보여 줄 상태."""
    p = path()
    if not p.exists():
        return {"있음": False, "경로": str(p)}
    c = connect()
    counts = {}
    for t in ("users", "learning", "last_use", "phrases",
              "work_history", "memories", "audit_logs"):
        try:
            counts[t] = c.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"]
        except Exception:
            counts[t] = None
    ver = c.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()["v"]
    return {"있음": True, "경로": str(p),
            "크기KB": round(p.stat().st_size / 1024, 1),
            "판번호": ver, "줄수": counts,
            "설명": "이 PC 안의 파일 하나입니다. 서버도, 설치도 필요 없습니다."}
