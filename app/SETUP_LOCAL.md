# 로컬 환경 설정 및 실행 가이드

**목표**: 로컬 규정 파일과 인트라넷 연동을 통합해서 서비를 실행

---

## 📋 필수 요구사항

| 항목 | 요구사항 |
|------|---------|
| **OS** | macOS, Linux, Windows |
| **Python** | 3.9+ |
| **디스크** | 최소 500MB |
| **메모리** | 최소 2GB |

---

## 🚀 빠른 시작 (5분)

### 1단계: 패키지 설치

```bash
# Python 가상환경 생성
python3 -m venv venv

# 활성화 (macOS/Linux)
source venv/bin/activate

# 활성화 (Windows)
venv\Scripts\activate

# 패키지 설치
pip install -r requirements.txt
```

### 2단계: 환경 설정

```bash
# .env 파일 생성
cp .env.example .env

# (선택) 인트라넷 API 키가 있으면 추가
# INTRANET_API_KEY=your-key
```

### 3단계: 서버 실행

```bash
# macOS/Linux
python run.py

# Windows
python.exe run.py
```

### 4단계: 브라우저 열기

```
http://localhost:8000
```

---

## 📖 상세 설정

### config.yaml 설정

#### A. 로컬 규정만 사용 (기본값)

```yaml
# config.yaml
intranet:
  enabled: false        # 로컬만 사용
  use_local: true       # 로컬 파일 사용
```

#### B. 로컬 + 인트라넷 규정 사용

```yaml
# config.yaml
approval:
  provider: intranet    # 인트라넷으로 기안 전송

intranet:
  enabled: true                    # 활성화
  base_url: https://gw.bwyf.or.kr # 인트라넷 URL
  api_key_env: INTRANET_API_KEY    # API 키 환경변수
  use_regulations: true            # 규정 가져오기
  use_forms: true                  # 서식 가져오기
```

#### C. AI 모델 선택

```yaml
# config.yaml (로컬 Ollama 사용)
models:
  default:
    provider: ollama
    base_url: http://127.0.0.1:11434/v1
    model: gemma2:9b  # 또는 다른 모델

# 또는 OpenAI API 사용
models:
  default:
    provider: openai
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-4
```

### .env 파일 설정

```bash
# AI 모델 (선택)
OPENAI_API_KEY=sk-...

# 인트라넷 (선택)
INTRANET_API_KEY=your-api-key
INTRANET_BASE_URL=https://gw.bwyf.or.kr

# 이메일 (선택)
MAIL_USER=your-email@example.com
MAIL_PASS=your-password
```

---

## 🧪 테스트

### 1. 로컬 규정 확인

```bash
# 로컬 규정 목록 출력
python3 test_intranet_local.py
```

**출력 예시:**
```
📋 로컬 규정 목록

총 17개 규정

🏢 COMMON (5개)
  • 공통_기안결재지침 [general]
  • 공통_물품구매지침 [general]
  • 공통_복무지침 [general]
  • 공통_여비지침 [general]
  • 공통_행사운영지침 [general]

🏢 DEMO-CITY (6개)
  • 복무조례 [general]
  • 사무전결처리규칙 [general]
  • 여비조례 [general]
  ...
```

### 2. IntranetClient 테스트

```bash
python3 -c "from app import intranet_local; c = intranet_local.IntranetClient_Mock(); print('✅' if c.is_configured() else '❌')"
```

### 3. 규칙 엔진 테스트

```bash
python3 -c "
from app.rules import get_index
idx = get_index('demo-city')
results = idx.search('출장', k=5)
for art, score in results:
    print(f'{art.title} - {art.ref} ({score:.2f})')
"
```

**출력 예시:**
```
여비조례 - 제4조 (0.75)
공통_여비지침 - 제3조 (0.70)
...
```

### 4. 완전한 통합 테스트

```bash
# 서버 실행
python run.py

# 다른 터미널에서 테스트
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "demo-city",
    "message": "출장 가는데 뭐 해야 해?",
    "user_id": "test"
  }' | python3 -m json.tool
```

---

## 🗂️ 규정 파일 구조

```
data/
├── common/                    # 공통 규정 (모든 기관 공통)
│   └── rules/
│       ├── 공통_기안결재지침.md
│       ├── 공통_여비지침.md
│       └── ...
│
├── orgs/
│   ├── demo-city/            # 기관 1: 지자체
│   │   ├── profile.yaml      # 기관 프로필
│   │   ├── rules/            # 기관 규정
│   │   │   ├── 여비조례.md
│   │   │   ├── 복무조례.md
│   │   │   └── ...
│   │   ├── rules/dept/       # 부서별 보충 규정
│   │   │   └── 총무과_업무지침.md
│   │   └── forms/            # 기관 서식
│   │       └── travel_settlement.docx
│   │
│   └── demo-agency/          # 기관 2: 기금
│       ├── profile.yaml
│       ├── rules/
│       └── forms/
│
└── templates/                # 기관 유형별 템플릿
    ├── agency.yaml
    ├── local.yaml
    └── central.yaml
```

### 규정 파일 추가하는 방법

#### 1. 공통 규정 추가

```bash
# data/common/rules/ 에 파일 추가
cp 새로운_규정.md data/common/rules/
```

#### 2. 기관 규정 추가

```bash
# data/orgs/demo-city/rules/ 에 파일 추가
cp 새로운_규정.md data/orgs/demo-city/rules/
```

#### 3. 부서 규정 추가

```bash
# data/orgs/demo-city/rules/dept/ 에 파일 추가
cp 부서_규정.md data/orgs/demo-city/rules/dept/
```

---

## 🔧 문제해결

### 패키지 설치 오류

```bash
# pip 업그레이드
pip install --upgrade pip

# 다시 설치
pip install -r requirements.txt
```

### "ModuleNotFoundError: No module named 'fastapi'"

```bash
# 가상환경 활성화 확인
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows

# 패키지 재설치
pip install -r requirements.txt
```

### 포트 8000 이미 사용 중

```bash
# 다른 포트로 실행
python run.py --port 8001
```

### 규정을 못 찾음

```bash
# data/orgs/demo-city/rules/ 에 파일이 있는지 확인
ls data/orgs/demo-city/rules/

# 파일 인코딩 확인 (UTF-8이어야 함)
file data/orgs/demo-city/rules/*.md
```

### 인트라넷 연동 오류

```bash
# .env 파일에 API 키 설정 확인
cat .env | grep INTRANET

# 인트라넷 서버 통신 확인
curl https://gw.bwyf.or.kr/api/v1/regulations \
  -H "Authorization: Bearer $INTRANET_API_KEY"
```

---

## 📚 규정 파일 포맷

### Markdown (.md) 형식

```markdown
# 여비 조례

제1조(목적) 이 조례는 ...

제2조(정의) 이 조례에서 "여비"란 ...

제3조(출장) 출장자는 ...
```

### Word (.docx) 형식 (읽기만)

```
PDF 등에서 docx로 변환 가능
```

### 한글 (.hwpx) 형식 (읽기만)

```
한글에서 hwpx로 저장
```

---

## 🎯 다음 단계

### 1. 기관 추가

```
서비 화면 → "기관 추가" → 이름 입력 → 프로필 작성
```

### 2. 규정 업로드

```
기관 → "규정" → PDF 파일 업로드
```

### 3. AI 모델 연결

#### Ollama (로컬)
```bash
# 1. Ollama 설치 & 실행
ollama pull gemma2:9b
ollama serve

# 2. config.yaml 수정
# models.default.provider = ollama
```

#### OpenAI (클라우드)
```bash
# 1. .env에 API 키 추가
OPENAI_API_KEY=sk-...

# 2. config.yaml 수정
# models.default.provider = openai
```

### 4. 결재 시스템 연동

#### 모의 테스트 (기본값)
```yaml
approval:
  provider: mock  # 가짜 문서번호 생성
```

#### 인트라넷 실제 연동
```yaml
approval:
  provider: intranet  # 실제 기안 전송
```

---

## 📖 추가 학습

- **FastAPI**: app/main.py
- **규정 검색**: app/rules.py
- **기안 시스템**: app/approval.py
- **인트라넷 연동**: app/intranet.py
- **웹 UI**: web/home.html

---

## 🆘 도움말

### 로그 확인

```bash
# 앱 로그 보기
python run.py 2>&1 | tail -50

# 상세 로그
python run.py --debug
```

### 데이터베이스 초기화

```bash
# 캐시 삭제 (규정 인덱스)
rm -rf .cache/rule_text/

# 임시 저장소 삭제
rm -rf data/approval_mock.json
```

### 백업

```bash
# 현재 상태 백업
cp -r data data_backup_$(date +%Y%m%d_%H%M%S)
```

---

**🎉 완료!** 이제 로컬에서 서비를 완벽하게 실행할 수 있습니다!

질문이 있으면 다음을 확인하세요:
- GitHub Issues: https://github.com/sysmetrix/bwyf_ai_contest/issues
- 개발자: know7846@gmail.com
