"""메일 발신부(어댑터). 발신 전용 — 받은 메일을 읽지 않습니다.

- provider: none → 발신 안 함(기본값). 결과는 ok=False.
- provider: smtp → SMTP로 담당자 본인 메일로 안내 요약·기한 알림을 보냅니다.
  계정 비밀번호는 config.yaml에 적지 않고 환경변수 이름(pass_env)만 적습니다.
"""
from __future__ import annotations

import os
import smtplib
from email.header import Header
from dataclasses import dataclass
from email.mime.text import MIMEText

from .store import load_config


@dataclass
class SendResult:
    ok: bool
    error: str | None = None


def _provider() -> dict:
    cfg = load_config()
    mail = cfg.get("mail", {})
    name = mail.get("provider", "none")
    return mail.get("providers", {}).get(name) or {"type": "none"}


def enabled() -> bool:
    return _provider().get("type") == "smtp"


def send(to: str, subject: str, body: str) -> SendResult:
    if not to or not to.strip():
        return SendResult(False, "받는 사람 메일 주소가 없습니다")
    provider = _provider()
    if provider.get("type") != "smtp":
        return SendResult(False, "메일 발신 연결 안 함(관리자 화면에서 연결)")

    user_env, pass_env = provider.get("user_env"), provider.get("pass_env")
    user = os.environ.get(user_env or "", "")
    password = os.environ.get(pass_env or "", "")
    if not user or not password:
        return SendResult(False, "보내는 메일 계정과 비밀번호가 저장되지 않았어요. 설정 → 메일 알림 연결에서 넣어 주세요")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = provider.get("from_addr") or user
    msg["To"] = to
    host, port = provider.get("host", ""), int(provider.get("port", 587))
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
        with server as s:
            if port != 465:
                s.starttls()
            s.login(user, password)
            s.sendmail(msg["From"], [to], msg.as_string())
        return SendResult(True)
    except smtplib.SMTPAuthenticationError:
        return SendResult(False, "계정이나 비밀번호가 맞지 않아요. 네이버·Gmail·다음은 평소 비밀번호가 아니라 "
                                 "'앱 비밀번호'를 따로 만들어 넣어야 해요(연결 방법 보기 참고)")
    except smtplib.SMTPRecipientsRefused:
        return SendResult(False, f"받는 주소({to})를 메일 서버가 거부했어요. 주소를 확인해 주세요")
    except smtplib.SMTPSenderRefused:
        return SendResult(False, "보내는 주소를 메일 서버가 거부했어요. '보내는 주소'를 계정과 같은 주소로 맞춰 보세요")
    except (OSError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected) as exc:
        return SendResult(False, f"메일 서버({host}:{port})에 연결하지 못했어요. 주소·포트를 확인해 주세요. "
                                 f"기관 내부망에서는 외부 메일 서버가 막혀 있을 수 있어요 ({str(exc)[:80]})")
    except Exception as exc:  # 발신 실패해도 본체 동작에는 영향 없음
        return SendResult(False, str(exc)[:200])
