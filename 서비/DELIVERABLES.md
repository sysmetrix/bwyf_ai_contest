# 서비(Seobi) v1.1.0 납품 구성

**작성일**: 2026-11-05  
**버전**: v1.1.0 (Windows 설치판 + Desktop 앱)  
**상태**: ✅ 완성 및 배포 준비 완료

---

## 📦 납품물

### 1. 압축 파일: `서비_v1.1.0_완전패키지.zip` (288MB)

**포함 내용:**
- ✅ Python FastAPI 백엔드 (app/)
- ✅ 웹 UI (web/ - HTML/CSS/JavaScript)
- ✅ Electron Desktop 앱 (desktop/)
- ✅ Windows 설치/빌드 도구 (tools/)
- ✅ 기관 규정 데이터 (data/)
- ✅ GitHub Actions CI/CD (github/workflows/)
- ✅ 설명서 (*.md)

**미포함** (용량 절감):
- `.git/` (깃 이력) → GitHub에 있음
- `__pycache__/` (Python 캐시)
- `node_modules/` (npm 패키지)
- `outputs/` (생성 파일)
- 주소: https://github.com/sysmetrix/bwyf_ai_contest

---

## 📚 문서 (3개)

### 1. `QUICKSTART.md` ⭐ 먼저 읽기
**대상**: 설치자, 사용자  
**내용**:
- 5분 안에 시작하기
- Windows/macOS 설치 방법
- AI 모델 선택
- 기본 사용법
- 문제해결

### 2. `INTRANET_INTEGRATION_GUIDE.md` ⭐ 개발자용
**대상**: 개발자  
**내용**:
- 현재 로컬 기반 구조 설명
- 인트라넷 연동 4단계 계획
- IntranetClient 클래스 구현 방법
- 규정/서식/기안 연동 코드 샘플
- 설정 방법 (config.yaml, .env)
- 다음 단계

### 3. `README.md` (기본)
**대상**: 모든 사용자  
**내용**: 프로젝트 개요, 라이센스, 기여자

---

## 💻 설치 방법

### Windows (자동 설치판)

#### 단계 1: 다운로드
👉 GitHub Releases에서 `서비_Windows설치판_v1.1.0.zip` 다운로드

#### 단계 2: 설치
```bash
# 1. ZIP 압축 해제
# 2. 폴더 열기 → python\python.exe tools\install.py 실행
# 또는 Windows PowerShell에서:
python\python.exe tools\install.py
```

#### 단계 3: 완료
- ✅ 백엔드 서버 자동 시작
- ✅ Desktop 앱 자동 실행
- ✅ 화면 우측 하단에 캐릭터 표시

### macOS/Linux (수동 설정)

```bash
# 1. 패키지 설치
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 서버 시작
python run.py

# 3. 브라우저에서
http://localhost:8000
```

---

## 🎯 주요 기능

### 1. 기관 규정 관리
- PDF/DOCX/HWPX 파일 자동 파싱
- 조문 단위 검색 (바이그램 방식)
- 공통·기관·부서 규정 3층 구조

### 2. 기본 서식 제공
- 출장 신청서 / 정산서
- 연가 신청서 / 병가
- 구매 요청서
- 행사 기획서

### 3. AI 비서 기능
- 자연어 질문 → 관련 규정 + 서식 검색
- 기관 프로필에서 자동으로 값 추출
- 서식 {{항목}} 자동 채우기
- 빠른 답변 + AI 요약

### 4. Desktop 앱
- 모니터 화면에 떠있는 캐릭터
- 캐릭터 클릭하면 검색 창 오픈
- 포즈 애니메이션 (일하기, 읽기, 아이디어, 걷기)
- 표정 변화 (행복, 무표정, 생각중)

### 5. 결재 연동
- 현재: 모의 테스트 (mock)
- 향후: 인트라넷 API 연동 (amaranth_10, 더존 아마란스)
- 기안 임시저장 → 인트라넷에서 최종 확인 후 상신

### 6. 자동 배포
- GitHub Actions로 Windows 설치판 자동 생성
- 태그 푸시 → 자동 빌드 → Release 업로드
- 별도 빌드 도구 불필요

---

## 🏗️ 기술 스택

| 영역 | 기술 |
|------|------|
| **백엔드** | Python 3.15, FastAPI, Uvicorn |
| **웹 UI** | HTML5, CSS3, JavaScript (Vanilla) |
| **Desktop** | Electron, Node.js |
| **데이터** | YAML, JSON (파일 기반) |
| **AI** | Ollama (로컬) or OpenAI (원격) |
| **배포** | Windows Installer, GitHub Actions |
| **버전 관리** | Git, GitHub |

---

## 📊 코드 통계

```
총 파일: ~698개

언어별 분포:
- Python: 18개 주요 모듈
- JavaScript: web/ UI, desktop/ 앱
- CSS: 포즈 애니메이션
- HTML: 캐릭터 SVG + 검색 UI
- YAML/JSON: 설정 & 데이터
```

주요 모듈:

| 파일 | 역할 | 줄 수 |
|------|------|------|
| app/main.py | API 엔드포인트 | ~500 |
| app/store.py | 파일 저장소 | ~600 |
| app/rules.py | 규정 검색 | ~400 |
| app/forms.py | 서식 초안 | ~350 |
| app/engine.py | 질문-답변 엔진 | ~500 |
| app/approval.py | 결재 연동 | ~300 |
| web/home.js | 상호작용 | ~300 |
| web/home.css | 애니메이션 | ~200 |

---

## 🔐 보안 고려사항

### 1. API 키 관리
- ✅ `.env` 파일에서만 관리 (git 미포함)
- ✅ config.yaml에는 환경변수 이름만 기재
- ✅ os.environ에서만 읽기

### 2. 규정 보호
- ✅ 기관별 데이터 격리 (data/orgs/<기관>/)
- ✅ 공통 규정은 읽기 전용

### 3. 인트라넷 연동 시
- ✅ HTTPS 통신 필수
- ✅ API 키는 환경변수로 관리
- ⚠️ 기관 규정이 외부 서버로 나가지 않도록 주의

---

## ✅ 완료된 작업

### Phase 1: 기본 구조 (✅ 완료)
- [x] FastAPI 백엔드
- [x] 웹 UI (검색, 결과)
- [x] 기관 프로필 관리
- [x] 규정 파싱 & 검색

### Phase 2: Desktop 앱 (✅ 완료)
- [x] Electron 앱 개발
- [x] 캐릭터 SVG 설계
- [x] 포즈 애니메이션 (4가지)
- [x] 표정 시스템

### Phase 3: Windows 설치판 (✅ 완료)
- [x] Python 3.15 번들링
- [x] 설치 스크립트 (install.py)
- [x] 바탕화면 바로가기
- [x] 시작 메뉴 등록
- [x] Desktop 앱 자동 실행

### Phase 4: CI/CD (✅ 완료)
- [x] GitHub Actions 워크플로우
- [x] Windows 설치판 자동 빌드
- [x] Release 자동 업로드

### Phase 5: 인트라넷 연동 (📋 계획 문서)
- [x] 연동 아키텍처 설계
- [x] IntranetClient 샘플 코드
- [x] 구현 가이드 작성
- [ ] 실제 구현 (다음 단계)

---

## 📈 다음 단계

### 1단계: 테스트 및 피드백 (1주)
- [ ] Windows 설치판 테스트
- [ ] 다양한 규정 파일 테스트
- [ ] 사용자 피드백 수집

### 2단계: 인트라넷 API 확인 (1주)
- [ ] 부천여성청소년재단 전산팀에 API 문서 요청
- [ ] API 스펙 분석
- [ ] 테스트 계정 발급 요청

### 3단계: 인트라넷 연동 개발 (2주)
- [ ] app/intranet.py 구현
- [ ] rules.py, forms.py 수정
- [ ] approval.py 확장
- [ ] 테스트

### 4단계: 배포 (1주)
- [ ] v1.2.0 태그 생성
- [ ] Windows 설치판 생성
- [ ] Release 노트 작성

---

## 🎓 학습 자료

### 개발자가 알아야 할 것

1. **Python FastAPI**: app/main.py 참고
2. **규정 검색**: app/rules.py (바이그램 알고리즘)
3. **서식 초안**: app/forms.py (Jinja2 템플릿)
4. **결재 연동**: app/approval.py (API 호출)
5. **웹 UI**: web/home.js (마우스 추적, 애니메이션)
6. **Desktop**: desktop/main.js (Electron IPC)

### 확장 가능한 부분

| 부분 | 확장 방법 |
|------|----------|
| 규정 소스 | app/intranet.py 추가 |
| AI 모델 | config.yaml에서 선택 |
| 결재 시스템 | approval.py에 새 provider 추가 |
| 캐릭터 애니메이션 | web/home.css에 포즈 추가 |
| 서식 템플릿 | data/orgs/<기관>/forms/ 추가 |

---

## 📞 지원

### 문제 해결
1. QUICKSTART.md의 "문제해결" 섹션 참고
2. GitHub Issues에 등록: https://github.com/sysmetrix/bwyf_ai_contest/issues
3. 개발자 이메일: know7846@gmail.com

### 추가 기능 요청
- GitHub Issues에 `enhancement` 라벨로 등록
- 상세 설명 + 사용 사례 포함

### 버그 신고
- GitHub Issues에 `bug` 라벨로 등록
- 재현 단계 + 오류 메시지 포함

---

## 📜 라이센스

MIT License (자유롭게 수정 & 배포 가능)

---

## 🎉 마치며

**서비** v1.1.0은 부천여성청소년재단의 행정 업무를 스마트하게 지원하기 위해 설계된 AI 비서입니다.

이 패키지는:
- ✅ **완전히 자동화된 설치**: Windows 설치판으로 바로 사용 가능
- ✅ **개방된 구조**: 기관 규정 추가, 결재 시스템 확장 용이
- ✅ **프라이버시 우선**: 규정 데이터는 로컬에서만 처리
- ✅ **지속 가능**: GitHub Actions로 자동 빌드 & 배포

**인트라넷 연동**으로 한 단계 업그레이드하면, 
규정·서식·기안을 완전히 통합된 워크플로우로 관리할 수 있습니다.

Happy coding! 🚀

---

**Last Updated**: 2026-11-05 17:46 KST  
**Repository**: https://github.com/sysmetrix/bwyf_ai_contest
