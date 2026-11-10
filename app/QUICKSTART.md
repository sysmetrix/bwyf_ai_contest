# 서비(Seobi) v1.1.0 빠른 시작 가이드

## 🎯 5분 안에 시작하기

### Windows 설치 (자동)

```bash
# 1. ZIP 다운로드 및 압축 해제
# 2. python\python.exe tools\install.py 실행
# 3. 완료! 바탕화면의 "서비" 아이콘을 클릭하세요
```

**결과:**
- ✅ 백엔드 서버 자동 시작 (포트 8000)
- ✅ Desktop 앱 자동 실행
- ✅ 화면 우측 하단에 캐릭터 표시
- ✅ 캐릭터 클릭 시 검색 창 오픈

### macOS/Linux 설정 (수동)

```bash
# 1. 패키지 설치
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 서버 시작
python run.py

# 3. 브라우저에서 열기
# http://localhost:8000
```

---

## 📁 패키지 구조

```
서비/
├── INTRANET_INTEGRATION_GUIDE.md  ⭐ 인트라넷 연동 방법
├── QUICKSTART.md                  ← 지금 읽고 있는 파일
├── README.md                       서비 소개
├── run.py                          ⭐ 시작 명령어
├── requirements.txt                의존 패키지
├── config.yaml                     설정
├── .env                            비밀값 (API 키)
│
├── app/                            ⭐ Python FastAPI 백엔드
│   ├── main.py                     API 엔드포인트
│   ├── engine.py                   질문-답변 엔진
│   ├── rules.py                    규정 검색
│   ├── forms.py                    서식 초안
│   ├── approval.py                 결재 연동
│   └── ...
│
├── web/                            ⭐ 웹 UI
│   ├── home.html                   캐릭터 + 검색
│   ├── home.css                    애니메이션
│   ├── home.js                     상호작용
│   └── ...
│
├── desktop/                        ⭐ Electron 앱
│   ├── main.js                     윈도우 관리
│   └── ...
│
├── tools/
│   ├── install.py                  ⭐ Windows 설치 스크립트
│   ├── build_windows.py            Windows 빌드 도구
│   └── ...
│
├── data/
│   ├── common/                      공통 규정
│   ├── templates/                   기관 템플릿
│   └── orgs/                        기관 데이터
│       └── demo-city/              (예시 기관)
│           ├── profile.yaml        기관 프로필
│           ├── rules/              기관 규정
│           └── forms/              기관 서식
│
└── .github/workflows/
    └── build-windows.yml            ⭐ 자동 빌드 설정
```

---

## ⚙️ 주요 설정

### 1. AI 모델 선택

#### 옵션 A: 로컬 모델 (권장 - 개인정보 보호)

```bash
# 1. Ollama 설치
# https://ollama.ai

# 2. 모델 다운로드
ollama pull gemma2:9b

# 3. config.yaml 수정
models:
  default:
    provider: ollama
    base_url: http://localhost:11434
    model: gemma2:9b
```

#### 옵션 B: OpenAI API

```bash
# 1. .env 파일에 API 키 추가
OPENAI_API_KEY=sk-...

# 2. config.yaml 수정
models:
  default:
    provider: openai
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    model: gpt-4-turbo
```

### 2. 결재 시스템 연동

#### 현재 (모의 테스트)

```yaml
approval:
  provider: mock          # 가짜 문서번호 생성 (테스트용)
```

#### 향후 (인트라넷 연동)

```yaml
approval:
  provider: intranet_api
  providers:
    intranet_api:
      type: intranet_api
      base_url: https://gw.bwyf.or.kr
      api_key_env: INTRANET_API_KEY
```

👉 자세한 방법: `INTRANET_INTEGRATION_GUIDE.md` 참고

---

## 🎮 사용 예시

### 1. 기관 등록

```
화면 → "기관 추가" → 기관명 입력 → 프로필 작성
```

### 2. 규정 업로드

```
기관 → "규정" → PDF 파일 업로드
(자동으로 조문 단위로 파싱됨)
```

### 3. 질문하기

```
캐릭터 클릭 → 검색창 열림 → "출장 가는데 뭐 해야 해?" 입력
→ 캐릭터가 관련 규정과 서식을 안내
```

### 4. 서식 작성

```
"출장 정산서 초안 만들어줘" 입력
→ 기관 규정에서 출장 기한, 일비 등을 자동으로 찾아
→ 서식에 자동으로 채움
→ DOCX 파일로 다운로드
```

### 5. 기안 올리기

```
서식 작성 완료 → "상신" 버튼 클릭
→ 결재 시스템으로 임시저장
→ 인트라넷에서 최종 확인 후 상신
```

---

## 🔧 문제해결

### Windows 설치 후 검은창만 떴다가 닫힘

**원인**: Python 환경 문제  
**해결**: 
```bash
# Windows PowerShell에서 수동 실행
cd %LOCALAPPDATA%\Seobi
python\python.exe run.py
```

### 캐릭터가 안 떠있음

**원인**: Desktop 앱 빌드 안 됨 (개발 중)  
**해결**: 
```bash
# 웹으로 접속
http://localhost:8000
```

### "모델에 연결할 수 없음" 오류

**원인**: AI 모델이 실행 중이 아님  
**해결**:
```bash
# Ollama 실행 (로컬 모델)
ollama serve

# 또는 OpenAI API 키 확인
echo $OPENAI_API_KEY
```

### 규정을 못 찾음

**원인**: PDF 파일 형식 미지원  
**해결**:
- 지원 형식: PDF, DOCX, HWPX (한글)
- 파일을 규정 폴더에 직접 복사:
  ```
  data/orgs/<기관>/rules/
  ```

---

## 📊 GitHub Actions (자동 빌드)

### 작동 방식

```
코드 변경
    ↓
git push + 태그 추가 (예: v1.2.0)
    ↓
GitHub Actions 자동 실행
    ├─ Python 3.15 설치
    ├─ 패키지 설치
    ├─ Electron 앱 빌드
    └─ Windows 설치판 생성
    ↓
Release 페이지에 자동 업로드
    ↓
https://github.com/sysmetrix/bwyf_ai_contest/releases
```

### 배포 방법

```bash
# 1. 코드 수정 및 커밋
git add .
git commit -m "feat: 새로운 기능"
git push origin release/v1.1.0

# 2. 릴리스 태그 생성 (자동 빌드 트리거)
git tag v1.2.0
git push origin v1.2.0

# 3. Releases 페이지에서 확인
# https://github.com/sysmetrix/bwyf_ai_contest/releases
```

---

## 📞 연락처

- **GitHub Issues**: https://github.com/sysmetrix/bwyf_ai_contest/issues
- **개발자 이메일**: know7846@gmail.com
- **그룹웨어**: gw.bwyf.or.kr

---

## 📋 체크리스트

- [ ] ZIP 파일 다운로드
- [ ] Windows: `tools\install.py` 실행 또는 macOS: `python run.py` 실행
- [ ] http://localhost:8000 접속 확인
- [ ] 기관 추가
- [ ] 규정 PDF 업로드
- [ ] 질문 테스트
- [ ] 서식 초안 생성 테스트
- [ ] 인트라넷 연동 (선택)

---

**Ready to go!** 🚀  
이제 기관 규정을 스마트하게 관리해보세요!
