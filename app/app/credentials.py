"""그룹웨어 계정 보관 — 비밀번호를 파일에 적지 않습니다.

운영체제의 자격 증명 저장소에 맡깁니다. 윈도우는 **자격 증명 관리자**,
맥은 **키체인**입니다. 파일을 복사해 가도 다른 계정·다른 PC에서는 풀 수 없습니다.

코드 안에 마스터 키를 두고 직접 암호화하는 방식은 쓰지 않습니다. 그렇게 하면
소스를 가진 사람이 모두 풀 수 있어서, 암호화해 둔 뜻이 없어집니다.

저장소를 쓸 수 없는 환경(일부 리눅스 서버 등)에서는 아이디만 설정에 남기고
비밀번호는 **보관하지 않습니다.** 그때는 실행할 때마다 사람이 넣어야 합니다.
조용히 파일에 적어 두지 않습니다.
"""
from __future__ import annotations

SERVICE = "seobi-groupware"


def _backend():
    try:
        import keyring
        from keyring.backends.fail import Keyring as FailKeyring
    except ImportError:
        return None
    try:
        kr = keyring.get_keyring()
        if isinstance(kr, FailKeyring):
            return None
        return keyring
    except Exception:
        return None


def available() -> tuple[bool, str]:
    """이 PC에서 비밀번호를 안전하게 보관할 수 있는지."""
    kr = _backend()
    if kr is None:
        return False, "이 환경에는 자격 증명 저장소가 없습니다(비밀번호를 보관하지 않습니다)"
    try:
        return True, kr.get_keyring().__class__.__name__
    except Exception as exc:
        return False, str(exc)[:120]


def save(base_url: str, user_id: str, password: str) -> tuple[bool, str]:
    """비밀번호를 저장소에 넣습니다. 넣지 못하면 그 사실을 분명히 알립니다."""
    kr = _backend()
    if kr is None:
        return False, "자격 증명 저장소를 쓸 수 없어 비밀번호를 보관하지 않았습니다"
    try:
        kr.set_password(SERVICE, _key(base_url, user_id), password)
        return True, "자격 증명 저장소에 보관했습니다"
    except Exception as exc:
        return False, f"보관하지 못했습니다: {str(exc)[:120]}"


def load(base_url: str, user_id: str) -> str | None:
    kr = _backend()
    if kr is None:
        return None
    try:
        return kr.get_password(SERVICE, _key(base_url, user_id))
    except Exception:
        return None


def delete(base_url: str, user_id: str) -> bool:
    kr = _backend()
    if kr is None:
        return False
    try:
        kr.delete_password(SERVICE, _key(base_url, user_id))
        return True
    except Exception:
        return False


def _key(base_url: str, user_id: str) -> str:
    return f"{(base_url or '').rstrip('/')}|{user_id or ''}"
