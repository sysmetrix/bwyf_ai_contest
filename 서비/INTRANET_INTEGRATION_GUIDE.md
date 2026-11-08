# 서비(Seobi) 인트라넷 연동 가이드

**버전**: v1.1.0  
**작성일**: 2026-11-05  
**대상**: 부천여성청소년재단 그룹웨어(gw.bwyf.or.kr) 연동

---

## 📋 목차

1. [프로젝트 개요](#프로젝트-개요)
2. [현재 구조](#현재-구조)
3. [인트라넷 연동 방법](#인트라넷-연동-방법)
4. [설치 및 실행](#설치-및-실행)
5. [GitHub 활용](#github-활용)

---

## 프로젝트 개요

### 서비(Seobi)란?
- **이름**: 서무비서 (Administrative Assistant Bot)
- **기능**: 기관 규정을 학습해 업무 절차와 서식을 자동으로 안내하는 AI 비서
- **형태**: 모니터 화면에 떠있는 캐릭터 + 검색 창
- **기술**: Python FastAPI + Electron Desktop + AI (Local/Remote)

### 주요 특징
✅ **Desktop 앱** - 화면 우측 하단에 캐릭터 표시  
✅ **캐릭터 애니메이션** - 일, 읽기, 아이디어, 걷기 포즈  
✅ **Windows 설치판** - 자동으로 Seobi.exe 실행  
✅ **로컬 규정 관리** - PDF/Word 규정 파일 자동 파싱  
✅ **기안 자동화** - 서식 초안 자동 작성 및 결재 연동  

---

## 현재 구조

### 폴더 구성

```
서비/
├── app/                      # Python FastAPI 백엔드
│   ├── main.py              # API 엔드포인트 정의
│   ├── store.py             # 파일 저장소 (data/ 관리)
│   ├── rules.py             # 규정 검색 및 인덱싱
│   ├── forms.py             # 서식 초안 생성
│   ├── drafter.py           # 기관 프로필 초안
│   ├── approval.py          # 결재 연동 (amaranth_10)
│   ├── engine.py            # 질문-답변 엔진
│   ├── llm.py               # AI 모델 연결
│   └── ...
├── web/                     # 웹 UI (HTML/CSS/JavaScript)
│   ├── home.html            # 캐릭터 + 검색 창
│   ├── home.css             # 애니메이션 (포즈, 부동)
│   ├── home.js              # 표정, 행동 제어
│   └── ...
├── desktop/                 # Electron 앱
│   ├── main.js              # 윈도우 생성 및 관리
│   └── ...
├── tools/
│   ├── install.py           # Windows 설치 스크립트
│   ├── build_windows.py     # Windows 빌드 도구
│   └── ...
├── data/
│   ├── common/              # 공통 규정 (모든 기관)
│   ├── templates/           # 기관 유형별 템플릿
│   ├── orgs/                # 기관별 데이터
│   │   └── <기관ID>/
│   │       ├── profile.yaml # 기관 프로필
│   │       ├── rules/       # 기관 규정 (PDF/Word)
│   │       └── forms/       # 기관 서식
│   └── ...
├── .github/workflows/
│   └── build-windows.yml    # GitHub Actions (자동 빌드)
├── run.py                   # 실행 진입점
├── requirements.txt         # Python 패키지
├── config.yaml              # 설정 (모델, API 등)
└── .env                     # 비밀값 (API 키)
```

### 데이터 흐름 (현재 로컬 기반)

```
사용자 질문
    ↓
[web/home.js] 마우스 이벤트 감지
    ↓
[app/engine.py] 답변 생성
    ├─ [app/rules.py] 규정 검색 (data/orgs/<기관>/rules/)
    ├─ [app/llm.py] AI 모델 호출
    └─ [app/forms.py] 서식 정보 조회
    ↓
[web/home.html] 답변 표시
    ↓
기안 생성 시:
    ├─ [app/forms.py] 서식 {{항목}} 채우기
    └─ [app/approval.py] 결재 시스템으로 전송
```

---

## 인트라넷 연동 방법

### 📌 목표
인트라넷(gw.bwyf.or.kr)에서 직접 규정·서식을 읽고, 기안을 임시저장/상신하도록 확대

### 4단계 구현 계획

#### **1단계: `app/intranet.py` 생성 - 인트라넷 클라이언트**

```python
# app/intranet.py
"""그룹웨어 API 연동 클라이언트"""

import os
import httpx
from typing import Optional

class IntranetClient:
    """부천여성청소년재단 그룹웨어(gw.bwyf.or.kr) 연동"""
    
    def __init__(self, base_url: str = "https://gw.bwyf.or.kr"):
        self.base_url = base_url.rstrip('/')
        self.api_key = os.environ.get("INTRANET_API_KEY")
        self.timeout = 30
    
    def is_configured(self) -> bool:
        """인트라넷 연동이 설정되었는지 확인"""
        return bool(self.api_key)
    
    # --- 규정 읽기 ---
    def get_regulations(self, category: str = "all") -> list:
        """규정 목록 가져오기
        
        Args:
            category: "all", "general", "finance", "hr" 등
        
        Returns:
            [{"id": "...", "title": "...", "url": "...", "updated": "..."}]
        """
        # POST /api/docs/regulations
        # Content-Type: application/json
        # Authorization: Bearer {API_KEY}
        pass
    
    def download_regulation(self, doc_id: str) -> bytes:
        """규정 파일 다운로드"""
        # GET /api/docs/{doc_id}/content
        pass
    
    # --- 서식 읽기 ---
    def get_forms(self, category: str = "all") -> list:
        """서식 목록 가져오기"""
        # POST /api/templates/forms
        pass
    
    def download_form_template(self, form_id: str) -> bytes:
        """서식 템플릿 다운로드 (.docx, .hwpx)"""
        # GET /api/templates/{form_id}/file
        pass
    
    # --- 기안 저장/상신 ---
    def submit_draft(self, doc: dict, submit: bool = False) -> dict:
        """기안 저장 또는 상신
        
        Args:
            doc: {
                "title": "출장 정산",
                "category": "travel_settlement",
                "content": "...",
                "attachments": [b"..."],
                "approvers": ["팀장", "과장"]
            }
            submit: False=임시저장, True=상신
        
        Returns:
            {"ok": True, "doc_no": "2026-00001", "url": "..."}
        """
        # POST /api/docs/draft
        # Content-Type: multipart/form-data
        pass
    
    def get_draft_status(self, doc_no: str) -> dict:
        """기안 상태 조회"""
        # GET /api/docs/{doc_no}/status
        pass
```

#### **2단계: `app/rules.py` 수정 - 인트라넷 규정 통합**

```python
# app/rules.py에 추가

from . import intranet

def fetch_rules(org_id: str, use_intranet: bool = True) -> list:
    """규정 가져오기 (로컬 + 인트라넷)
    
    우선순위:
    1. 부서 보충(dept/) - 가장 구체적
    2. 기관 규정(org/) - 중간
    3. 인트라넷 규정 - 조직 전체
    4. 공통 규정(common/) - 일반
    """
    articles = []
    
    # 1. 로컬 부서 규정
    dept_rules = (org_dir(org_id) / "rules" / "dept").glob("*.pdf")
    for f in dept_rules:
        articles.extend(split_articles(read_text(f), "dept", str(f), f.stem))
    
    # 2. 로컬 기관 규정
    org_rules = (org_dir(org_id) / "rules").glob("*.pdf")
    for f in org_rules:
        articles.extend(split_articles(read_text(f), "org", str(f), f.stem))
    
    # 3. 인트라넷 규정 (설정되어 있으면)
    if use_intranet:
        client = intranet.IntranetClient()
        if client.is_configured():
            try:
                for reg in client.get_regulations():
                    content = client.download_regulation(reg["id"])
                    articles.extend(split_articles(
                        read_text(content),
                        "intranet",
                        f"intranet://{reg['id']}",
                        reg["title"]
                    ))
            except Exception as e:
                print(f"⚠️ 인트라넷 규정 로드 실패: {e}")
    
    # 4. 공통 규정
    common_rules = COMMON.glob("*.pdf")
    for f in common_rules:
        articles.extend(split_articles(read_text(f), "common", str(f), f.stem))
    
    return articles
```

#### **3단계: `app/forms.py` 수정 - 인트라넷 서식**

```python
# app/forms.py에 추가

def fetch_form_template(org_id: str, form_id: str) -> Path:
    """서식 템플릿 가져오기 (로컬 우선, 없으면 인트라넷)"""
    
    # 1. 로컬 서식 먼저 확인
    local_form = org_dir(org_id) / "forms" / f"{form_id}.docx"
    if local_form.exists():
        return local_form
    
    # 2. 인트라넷에서 다운로드
    client = intranet.IntranetClient()
    if client.is_configured():
        try:
            content = client.download_form_template(form_id)
            # 캐시에 저장
            local_form.parent.mkdir(parents=True, exist_ok=True)
            local_form.write_bytes(content)
            return local_form
        except Exception as e:
            print(f"⚠️ 인트라넷 서식 로드 실패: {e}")
    
    # 3. 기본 서식
    return TEMPLATES / "default" / f"{form_id}.docx"
```

#### **4단계: `app/approval.py` 확장 - 인트라넷 기안**

```python
# app/approval.py에 추가

def submit_to_intranet(org_id: str, manifest: dict, submit: bool = False) -> SendResult:
    """인트라넷으로 기안 전송
    
    Args:
        manifest: 기안 패키지 메타데이터
        submit: False=임시저장, True=상신
    """
    client = intranet.IntranetClient()
    
    if not client.is_configured():
        return SendResult(ok=False, provider="intranet", 
                         error="인트라넷 API 키가 설정되지 않았습니다")
    
    try:
        # 첨부파일 준비
        attachments = _attachments(org_id, manifest)
        
        # 인트라넷 전송
        result = client.submit_draft({
            "title": manifest["title"],
            "category": manifest["form_id"],
            "content": manifest.get("content", ""),
            "attachments": [f.read_bytes() for f in attachments],
            "approvers": manifest.get("approvers", [])
        }, submit=submit)
        
        return SendResult(
            ok=result["ok"],
            provider="intranet",
            doc_no=result.get("doc_no"),
            url=result.get("url"),
            state="submitted" if submit else "draft"
        )
    except Exception as e:
        return SendResult(ok=False, provider="intranet", error=str(e))
```

### 📌 설정 방법

#### **1. 환경변수 설정** (`.env`)

```bash
# .env 파일
INTRANET_API_KEY=your_api_key_here
INTRANET_BASE_URL=https://gw.bwyf.or.kr
```

#### **2. config.yaml 수정**

```yaml
# config.yaml

approval:
  provider: intranet_api
  providers:
    intranet_api:
      type: intranet_api
      base_url: https://gw.bwyf.or.kr
      api_key_env: INTRANET_API_KEY

# 선택사항: 인트라넷 규정/서식 활용 여부
intranet:
  enabled: true
  use_regulations: true    # 인트라넷 규정도 함께 사용
  use_forms: true          # 인트라넷 서식도 함께 사용
```

---

## 설치 및 실행

### Windows 설치

1. **GitHub Releases에서 다운로드**
   - 👉 https://github.com/sysmetrix/bwyf_ai_contest/releases
   - `서비_Windows설치판_v1.1.0.zip` 다운로드

2. **설치**
   ```bash
   # ZIP 압축 해제
   # python\python.exe tools\install.py 실행
   ```
   
3. **결과**
   - ✅ 바탕화면에 "서비" 아이콘 생성
   - ✅ 시작 메뉴에 "서비" 추가
   - ✅ 화면 우측 하단에 캐릭터 표시
   - ✅ 캐릭터 클릭하면 검색 창 오픈

### macOS 실행

```bash
# 1. Python 환경 설정
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 서버 시작
python run.py

# 3. 브라우저에서 열기
# http://localhost:8000
```

### AI 모델 연결

#### **로컬 모델** (권장)
```bash
# Ollama 설치 후 실행
ollama pull gemma2:9b
ollama serve

# config.yaml
models:
  default:
    provider: ollama
    base_url: http://localhost:11434
    model: gemma2:9b
```

#### **원격 모델** (OpenAI 호환)
```bash
# config.yaml
models:
  default:
    provider: openai
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-4-turbo
```

---

## GitHub 활용

### 저장소
- 📍 **URL**: https://github.com/sysmetrix/bwyf_ai_contest
- 📍 **브랜치**: `release/v1.1.0` (프로덕션)

### 최신 커밋

| 커밋 | 설명 |
|------|------|
| `824cb02` | ✅ Desktop 앱 Windows 설치시 자동 실행 |
| `b4dc283` | ✅ 검색창 겹침 문제 수정 |
| `0a3e855` | ✅ 포즈 애니메이션 (일, 읽기, 아이디어, 걷기) |
| `58be218` | ✅ GitHub Actions Windows 자동 빌드 |

### CI/CD 파이프라인

```
git tag v1.1.1
git push origin v1.1.1
    ↓
[GitHub Actions 자동 실행]
    ├─ Windows 빌드
    ├─ Python 3.15 + 패키지 번들
    ├─ Electron 앱 패킹
    └─ Release에 업로드
    ↓
Windows 설치판 자동 생성 ✅
```

---

## 다음 단계

### 1️⃣ 인트라넷 API 확인

부천여성청소년재단 전산팀에 다음 정보 요청:
- API 엔드포인트 문서
- 인증 방식 (OAuth, JWT, API Key)
- 규정 조회 API 스펙
- 서식 관리 API 스펙
- 기안 저장 API 스펙

### 2️⃣ IntranetClient 구현

실제 API에 맞춰 `app/intranet.py` 구현

### 3️⃣ 테스트 및 배포

```bash
# 1. 로컬 테스트
python run.py

# 2. 커밋 및 푸시
git add app/intranet.py app/rules.py app/forms.py app/approval.py
git commit -m "feat: add intranet integration"
git push origin release/v1.1.0

# 3. 태그 및 릴리스
git tag v1.2.0
git push origin v1.2.0
```

---

## 📞 문의

- **GitHub Issues**: https://github.com/sysmetrix/bwyf_ai_contest/issues
- **개발자**: know7846@gmail.com

---

**Last Updated**: 2026-11-05  
**Status**: 🟢 Production Ready (Windows v1.1.0)
