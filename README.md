# bwyf_ai_contest

부천여성청소년재단(BWYF) 팀의 AI 경진대회 출품작 **서무비서** 작업 레포입니다. (공개)

> 처음 오셨다면 [시작하기.md](시작하기.md)와 [docs/협업가이드.md](docs/협업가이드.md)부터 읽어 주세요.
> AI 도구는 [AGENTS.md](AGENTS.md)의 규칙을 따릅니다.

## 폴더 구조

```
bwyf_ai_contest/
├─ app/             서무비서 메인 프로그램              영운
├─ data/            규정·서식 정리본 (개인정보 제외)    지은
├─ intranet/        가상 인트라넷 (모의 그룹웨어)        준호
├─ AGENTS.md        모든 AI가 따르는 공통 규칙          원하
├─ 시작하기.md       팀원용 첫 안내                      원하
├─ docs/            협업가이드, 연동약속, 이관요청문    원하
├─ .github/         PR 양식, 폴더 담당자(CODEOWNERS)   원하
└─ .githooks/       main 직접 커밋·푸시 막기            원하
```

CLAUDE.md, GEMINI.md는 AGENTS.md를 불러오기만 합니다.

## 팀

| 사람 | 맡은 일 |
|---|---|
| 이영운 (@leeknow2) | 서무비서 메인 프로그램 구축 |
| 김지은 (@Jenna9314) | 규정·서식 정리본 제작 |
| 김준호 (@junhohooo12-cell) | 가상 인트라넷 구축 |
| 서원하 (@sysmetrix) | 전체 총괄 |

## 실행

Python 3.10 이상이 필요합니다. **서무비서 하나만 켜면 인트라넷도 같이 열립니다.**

```bash
cd app && pip install -r requirements.txt && python run.py
```

- 서무비서: http://localhost:8000
- 가상 인트라넷: http://localhost:8000/intranet/ (연결 작업 중. `docs/연동약속.md` 3장)

## 일정

(정할 것)
