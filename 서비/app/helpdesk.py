"""서비 자신에 대한 질문("규정 어디서 찾아?", "뭐 할 수 있어?")과, 업무로 분류되지 않은 질문에 답합니다.

답은 지어내지 않고 지금 서비의 실제 상태(이 기관에 들어 있는 문서, AI 연결 여부 등)로 만듭니다.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import llm
from .rules import LAYER_LABEL, get_index, list_rule_files
from .store import load_tasks

ASKS_ME = re.compile(r"(^|\s)(너|넌|니가|네가|당신|서비)(는|가|은|야|한테|의)?(\s|$|[?.,!])")

TOPICS: list[tuple[str, re.Pattern]] = [
    ("greeting", re.compile(r"^\s*(안녕|하이|hello|hi\b|반가|고마워|고맙|감사|수고)", re.I)),
    ("identity", re.compile(r"(누구(야|세요|니)|정체|뭐하는 ?(애|거|프로그램)|이름이 뭐)")),
    ("docs", re.compile(r"(내부 ?문서|규정집|매뉴얼|규정 ?(파일|문서|목록)|문서 ?목록).{0,8}(보|확인|열|목록|뭐|있)")),
    ("add_rules", re.compile(r"(규정|매뉴얼|지침|문서).{0,12}(추가|올리|넣|등록|업데이트|바꾸|새로)")),
    ("rules_source", re.compile(r"(규정|근거|자료|매뉴얼|정보).{0,12}(어디|어떻게|무엇|뭘|뭐).{0,8}(찾|보|가져|참고|알아|나와)|"
                                r"어디(서|에서).{0,6}(찾|가져|알아|보고)|(무슨|어떤|어느) ?(규정|자료|문서)")),
    ("forms_help", re.compile(r"(서식|양식).{0,10}(올리|추가|넣|등록|어떻게|만드|바꾸)")),
    ("mail", re.compile(r"메일.{0,10}(연결|설정|등록|안 ?와|어떻게|받으려)")),
    ("transfer", re.compile(r"((PC|피씨|컴퓨터).{0,10}(옮|바꾸|이전|교체))|(데이터.{0,6}(이전|백업|옮))", re.I)),
    ("update", re.compile(r"(업데이트|새 ?버전|최신 ?버전)")),
    ("formats", re.compile(r"(한글|hwp|hwpx|pdf|워드|docx|엑셀|xlsx|이미지|사진|스캔|파일).{0,12}(읽|올릴|올려|열|돼|되나|되요|가능|지원|인식)", re.I)),
    ("speed", re.compile(r"(느려|느린|느림|늦게|오래 ?걸|로딩|속도|빨리|빠르게|버벅|지연|기다려야)")),
    ("ai", re.compile(r"((?<![A-Za-z])AI(?![A-Za-z])|인공지능|GPT|제미나이|gemini|클로드|개인정보|외부로|밖으로 (나가|보내))", re.I)),
    ("capabilities", re.compile(r"((뭐|무엇|뭘|어떤 ?걸).{0,6}(할 ?수|해 ?줄 ?수|도와|가능))|기능|사용법|쓰는 ?법|어떻게 (써|사용)")),
]

DOC_PAGE = "docs.html"

SEOBI_FACTS = chr(10).join([
    "당신은 '{org}'의 서무 업무 비서 '서비'입니다. 사용자가 서비 자신·사용법·동작 방식에 대해 물으면 아래 사실만 근거로 친절하게 답합니다. 질문에 대한 답(예/아니요 등)을 첫 문장에 바로 말합니다. 아래에 없는 기능이나 사실은 지어내지 말고 '그건 아직 안 돼요'라고 말합니다.",
    '[서비 사실]',
    '- 출장 신청·여비 정산·연가·병가·물품 구매·행사 개최·일반 기안 절차, 기한, 전결권자·결재선, 필요 서류를 기관 규정 기준으로 안내한다.',
    '- 근거는 인터넷이 아니라 기관에 넣어 둔 규정·매뉴얼 문서에서 조문 단위로 찾는다(부서 보충 > 기관 규정 > 공통 규정 순).',
    '- 기한 계산·전결 판정·근거 찾기는 AI 없이 규칙으로 하고, AI는 질문 이해와 문장 다듬기에만 쓴다. AI 없이도 모든 기능이 동작한다.',
    '- AI를 쓰면 답이 몇 초 늦어질 수 있어 규칙 부분을 먼저 보여 주고 AI 문장은 나중에 바꿔 넣는다. 서비를 켠 직후 큰 PDF를 처음 읽을 때 첫 답이 느릴 수 있다.',
    '- 서식 보관함에 DOCX/HWPX 서식을 올리면 {{항목}} 자리에 값을 채운 초안 파일을 만든다.',
    '- 설정 → 규정·매뉴얼에서 문서를 올리고 원문을 열어 볼 수 있다(PDF·HWPX·DOCX·MD·TXT, 옛 HWP는 안 됨).',
    '- 메일 알림(네이버·Gmail·다음·기관 메일), PC 옮기기(.seobi 파일), 자동 업데이트, 담당자별 내 할 일, 음성 입력이 있다.',
    '- 질문과 관련 조문 일부만 연결한 AI로 보내고, 규정 파일 전체는 보내지 않는다.',
    '- 질문마다 따로 답하고 앞 대화 내용을 이어서 기억하지는 않는다. 처리한 업무는 "최근 처리 이력"과 "내 할 일"에 업무 이름·기한으로 남는다.',
])


def detect(message: str, task_found: bool) -> str | None:
    """서비 자신에 대한 질문이면 주제를 돌려줍니다. 업무로 분류된 질문은 '너/서비'처럼 나를 가리킬 때만 가로챕니다."""
    for topic, pat in TOPICS:
        if pat.search(message):
            if not task_found or topic in ("greeting", "identity") or ASKS_ME.search(message):
                return topic
    if not task_found and ASKS_ME.search(message):
        return "about_me"
    return None


def list_docs(org_id: str) -> list[dict]:
    counts: dict[str, int] = {}
    for a in get_index(org_id).articles:
        counts[a.file] = counts.get(a.file, 0) + 1
    out = []
    for f in list_rule_files(org_id):
        out.append({"file": f["file"], "name": Path(f["file"]).name, "layer": f["layer"],
                    "layer_label": f["layer_label"], "articles": counts.get(f["file"], 0)})
    order = {"org": 0, "dept": 1, "common": 2}
    return sorted(out, key=lambda d: (order[d["layer"]], d["name"]))


def _docs_sentence(docs: list[dict]) -> str:
    parts = []
    for layer in ("org", "dept", "common"):
        group = [d for d in docs if d["layer"] == layer]
        if not group:
            continue
        names = ", ".join(d["name"] for d in group[:3]) + (f" 외 {len(group) - 3}개" if len(group) > 3 else "")
        parts.append(f"{LAYER_LABEL[layer]} {len(group)}개({names})")
    return " / ".join(parts) if parts else "아직 넣어 둔 규정 문서가 없어요"


def answer_topic(org_id: str, org_name: str, topic: str, message: str = "") -> dict:
    links: list[dict] = []
    docs: list[dict] = []
    ai_on = llm.role_enabled("answer")
    task_names = ", ".join(t["name"] for t in load_tasks())

    if topic in ("rules_source", "docs"):
        docs = list_docs(org_id)
        org_docs = [d for d in docs if d["layer"] != "common"]
        text = (f"저는 인터넷이 아니라 {org_name}에 넣어 둔 문서에서만 찾아요. 지금 참고하는 문서: {_docs_sentence(docs)}. "
                "질문이 오면 이 문서들을 조문(제○조) 단위로 나눠 둔 것 중에서 질문과 가장 잘 맞는 조문을 찾아 근거로 붙여요. "
                "기관 규정이 공통 규정보다, 부서 보충이 기관 규정보다 우선이에요.")
        if not org_docs:
            text += " 아직 이 기관만의 규정이 없어서 공통 규정으로만 안내하고 있어요. 기관 규정·매뉴얼을 올려 두면 그 기준으로 안내해 드려요."
        text += " 아래 목록에서 문서를 눌러 원문을 직접 확인할 수 있어요."
        links = [{"label": "규정·매뉴얼 화면 열기", "href": DOC_PAGE}]
    elif topic == "add_rules":
        text = ("규정이나 업무 매뉴얼은 [⚙ 설정 → 규정·매뉴얼] 화면에서 파일을 골라 올리면 돼요(PDF, 한글 HWPX, 워드 DOCX, 텍스트 MD·TXT). "
                "기관 전체에 해당하면 '기관 규정'으로, 우리 부서만의 지침이면 '부서 보충'으로 올리세요. "
                "올리는 즉시 조문 단위로 나눠서 다음 질문부터 근거로 써요. 큰 PDF는 처음 한 번 읽는 데 1분 정도 걸릴 수 있어요. "
                "한글 HWP(옛 형식)는 한글에서 'HWPX'나 'PDF'로 다시 저장해서 올려 주세요.")
        links = [{"label": "규정·매뉴얼 올리기", "href": DOC_PAGE}]
    elif topic == "forms_help":
        text = ("서식은 [⚙ 설정 → 서식 보관함]에서 업무별로 올려요(DOCX 또는 HWPX). 서식 안에 채울 자리를 {{출장지}}, {{출장 기간}}처럼 "
                "중괄호 두 개로 표시해 두면, 질문에서 알아낸 값과 기관 기준(기한·결재선 등)으로 채운 초안을 새 파일로 만들어 드려요. "
                "원본 서식은 바뀌지 않아요.")
        links = [{"label": "서식 보관함 열기", "href": "forms.html"}]
    elif topic == "mail":
        text = ("메일 연결은 [⚙ 설정 → 설정 → 메일 알림 연결]에서 해요. 보내는 메일 서버(SMTP) 주소·포트, 보내는 계정, 비밀번호를 넣으면 "
                "안내를 메일로 받을 수 있어요. 네이버는 smtp.naver.com / 587(메일 환경설정에서 'SMTP 사용' 켜기), "
                "Gmail은 smtp.gmail.com / 587(구글 계정의 '앱 비밀번호' 사용)이에요. 기관 메일은 전산 담당자에게 SMTP 주소를 물어보세요. "
                "자세한 순서는 설정 화면의 '연결 방법 보기'에 있어요.")
        links = [{"label": "메일 연결하러 가기", "href": "settings.html#mail"}]
    elif topic == "transfer":
        text = ("PC를 옮길 때는 [⚙ 설정 → 설정 → PC 옮기기]에서 '데이터 파일 내려받기'로 .seobi 파일을 만들고, "
                "새 PC에 서비를 설치한 뒤 같은 화면에서 '가져오기'를 하면 기관·규정·매뉴얼·서식·이력·설정이 그대로 옮겨져요.")
        links = [{"label": "PC 옮기기 화면", "href": "settings.html#transfer"}]
    elif topic == "update":
        text = ("서비는 인터넷에 연결돼 있으면 켤 때 새 버전이 있는지 확인해요. 새 버전이 있으면 화면 위에 알림이 뜨고, "
                "'업데이트'를 누르면 내려받아 설치한 뒤 다시 켜져요. 만들어 둔 기관·규정·서식·설정은 그대로 남아요. "
                "[⚙ 설정 → 설정 → 업데이트]에서 직접 확인할 수도 있어요.")
        links = [{"label": "업데이트 확인", "href": "settings.html#update"}]
    elif topic == "formats":
        text = ("규정·매뉴얼은 PDF, 한글(HWPX), 워드(DOCX), 텍스트(MD·TXT)를 읽어요. 옛 한글 형식(HWP)은 읽지 못해서, "
                "한글에서 '다른 이름으로 저장 → HWPX 또는 PDF'로 바꿔 올려 주세요. 글자가 아니라 사진처럼 스캔된 PDF는 글자를 뽑을 수 없어서 "
                "근거로 쓰지 못해요. 서식(초안 자동 채우기)은 DOCX와 HWPX를 지원하고, 엑셀·이미지는 아직 안 돼요.")
        links = [{"label": "규정·매뉴얼 올리기", "href": DOC_PAGE}, {"label": "서식 보관함", "href": "forms.html"}]
    elif topic == "about_me" and ai_on:
        ai = ai_general_answer(org_id, org_name, message)
        if ai:
            return {**ai, "kind": "help", "topic": topic, "suggestions": []}
        return answer_topic(org_id, org_name, "capabilities")
    elif topic == "speed":
        if ai_on:
            _, provider, model = llm._role_target("answer", None)
            text = (f"지금 AI({provider} · {model})가 연결돼 있어서, 답을 만들 때 인터넷으로 AI에게 한두 번 물어보느라 몇 초가 걸려요. "
                    "그래서 절차·기한·결재선·근거 조문은 AI 없이 규칙으로 먼저 바로 보여 드리고, AI가 다듬은 안내 문장은 준비되는 대로 바꿔 넣어요. "
                    "업무가 분명한 질문은 AI 분류를 건너뛰어 더 빨라요. 그래도 느리면 ① 무료 AI가 붐비는 시간일 수 있고 "
                    "② 서비를 켠 직후에는 큰 매뉴얼 PDF를 처음 읽느라 첫 질문이 오래 걸릴 수 있어요(한 번 읽으면 저장해 둬요). "
                    "더 빠르게 하려면 AI 모델 연결에서 'lite'처럼 가벼운 모델을 고르거나, AI 연결을 끄면 규칙만으로 즉시 답해요.")
        else:
            text = ("지금은 AI가 연결돼 있지 않아서 규칙으로만 바로 답해요. 그래도 느리다면 서비를 켠 직후 큰 매뉴얼 PDF를 처음 읽는 중일 수 있어요"
                    "(1분 정도, 한 번 읽으면 저장해 두고 다음부터는 바로 답해요).")
        links = [{"label": "AI 모델 연결", "href": "models.html"}]
    elif topic == "ai":
        state = "지금 AI 모델이 연결돼 있어서" if ai_on else "지금은 AI 모델이 연결돼 있지 않아서"
        text = (f"{state} " + ("질문 이해와 안내 문장 다듬기에 AI를 써요. " if ai_on else "규칙 기반으로만 동작해요. ")
                + "기한 계산·전결권자 판정·근거 조문 찾기는 AI 없이 규칙으로 해서, AI가 숫자나 규정을 지어내지 않아요. "
                "AI를 연결하면 질문과 관련 조문 몇 개만 연결한 AI 서비스로 보내고, 규정 파일 전체나 다른 자료는 보내지 않아요.")
        links = [{"label": "AI 모델 연결", "href": "models.html"}]
    elif topic == "identity":
        text = (f"저는 {org_name}의 서무 업무 비서 '서비'예요. 상황을 말씀해 주시면 기관 규정을 찾아 절차·기한·결재선·필요 서류를 "
                "안내하고, 서식 초안까지 만들어 드려요.")
    elif topic == "greeting":
        text = "안녕하세요, 서비예요. 출장·연가·물품 구매처럼 처리할 일을 말씀해 주시면 바로 안내해 드릴게요."
    else:  # capabilities
        text = (f"저는 이런 걸 도와드려요: ① 서무 업무 안내({task_names}) — 절차·기한·결재선·필요 서류를 {org_name} 규정 기준으로 알려 드려요. "
                "② 근거 조문 찾기 — 답마다 어느 규정 몇 조인지 붙여요. ③ 서식 초안 — 올려 둔 서식에 값을 채워 드려요. "
                "④ 내 할 일·메일 알림 — 기한이 있는 일을 모아 보여 드려요. "
                "'다음 주 세종 출장 다녀와서 정산해야 해요'처럼 상황을 그대로 말해 주세요.")
    return {"task": None, "kind": "help", "topic": topic, "summary": text, "summary_by": "서비 안내",
            "links": links, "docs": docs, "suggestions": [], "evidence": []}


ASSISTANT_ROLE = chr(10).join([
    "[하는 일] 당신은 위 기관의 서무·행정 담당자를 돕는 업무 비서입니다. 어떤 질문이든 무시하지 말고 서무 비서로서 도와줍니다.",
    "- 공문·안내문·보고서·이메일 초안 작성, 문장 다듬기, 요약, 회의록 정리, 일정·할 일 정리, 엑셀·한글 사용법, 일반 행정 상식은 바로 해 줍니다.",
    "- 기관 규정이 필요한 내용은 아래 '관련 조문'에 있는 것만 근거로 말하고 [1]처럼 번호를 붙입니다.",
    "- 관련 조문에 없는 이 기관의 기한·금액·전결권자·조문 번호는 절대 지어내지 말고, '기관 규정에서 확인되지 않았어요'라고 한 뒤 담당 부서 확인을 권합니다.",
    "- 업무와 거리가 먼 질문(점심 메뉴, 날씨 등)도 거절하지 말고 짧고 친절하게 답한 뒤, 가능하면 업무에 도움이 되는 한마디(예: 팀 점심이면 회식비 처리 기준 확인)를 덧붙입니다.",
    "- 사용법·방법을 물으면 되묻기 전에 바로 따라 할 수 있는 단계로 먼저 알려 줍니다.",
    "- 관련 조문은 질문과 직접 관계있을 때만 인용합니다. 다른 업무의 조문(예: 행사 규정을 출장에)을 끌어다 쓰지 않습니다.",
    "- 앞 대화를 고쳐 달라는 말(줄여 줘, 바꿔 줘, 다시 써 줘)이면 바로 앞의 답을 고쳐서 다시 씁니다.",
    "- 실제 사람 이름·연락처·개인정보는 만들어 내지 않고 [이름]처럼 빈칸으로 둡니다.",
    "- 존댓말로, 초안은 바로 붙여 넣을 수 있게 완성된 형태로 씁니다. 짧은 질문에는 짧게 답합니다.",
])


WRITING = re.compile(r"(줄여|늘려|다시\s?써|바꿔\s?줘|더\s?짧게|더\s?길게|부드럽게|격식|써\s?줘|써\s?주세요|작성해|초안|다듬어|고쳐\s?줘|요약해|정리해\s?줘|번역해|문구|문장|메일\s?써|이메일|보도자료|인사말|축사)")


def wants_writing(message: str) -> bool:
    """글을 써 달라는 요청인지(서식 파일을 채워 달라는 말은 제외)."""
    return bool(WRITING.search(message)) and "서식" not in message


def is_followup(message: str, history: list | None) -> bool:
    """앞 답을 고쳐 달라는 말인지("방금 거 줄여 줘", "위 내용 공문으로")."""
    return bool(history) and bool(re.search(r"(방금|위\s?(내용|거|답)|이거|그거|앞의|아까)", message))


def ai_general_answer(org_id: str, org_name: str, message: str, history: list | None = None,
                      facts: str = "", evidence: list | None = None) -> dict | None:
    """AI가 연결돼 있을 때: 어떤 질문이든 서무 비서로서 답합니다. 기관 규정은 찾은 조문만 근거로 씁니다.
    evidence를 주면(업무가 정해진 경우) 그 업무의 조문만 근거로 넘깁니다."""
    if not llm.role_enabled("answer"):
        return None
    if evidence is None:
        hits = [(a, s) for a, s in get_index(org_id).search(message, k=4) if s >= 1.5]
        evidence = [a.as_dict(s) for a, s in hits]
    ev = chr(10).join(f"[{i + 1}] {e['label']}: {e['text'][:700]}" for i, e in enumerate(evidence)) or "(관련 조문 없음)"
    today = date.today()
    system = (SEOBI_FACTS.replace("{org}", org_name) + chr(10) + ASSISTANT_ROLE + chr(10)
              + f"- 오늘은 {today.year}년 {today.month}월 {today.day}일입니다. 연도를 쓸 때는 이 날짜를 기준으로 합니다.")
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-4:]:
        q, a = str(h.get("q", ""))[:400], str(h.get("a", ""))[:800]
        if q and a:
            msgs += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    extra = (chr(10) * 2 + "[서비가 규정으로 이미 확인한 사실 — 그대로 쓰세요]" + chr(10) + facts) if facts else ""
    msgs.append({"role": "user", "content": f"{message}" + chr(10) * 2 + "[관련 조문]" + chr(10) + ev + extra})
    res = llm.chat("answer", msgs, max_tokens=1000, timeout=300)
    if not (res.ok and res.text):
        return None
    text = res.text.strip()
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text) if 0 < int(n) <= len(evidence)})
    used = [evidence[n - 1] for n in cited]  # 답에서 실제로 인용한 조문만 근거로 보여 줍니다
    return {"task": None, "kind": "chat", "summary": text, "summary_by": f"AI ({res.model})",
            "grounded": bool(used), "evidence": used, "suggestions": [], "links": [], "docs": []}


def answer_unknown(org_id: str, org_name: str, message: str, history: list | None = None,
                   use_ai: bool = True) -> dict:
    """업무로도, 서비에 대한 질문으로도 분류되지 않은 질문.
    AI가 있으면 서무 비서로서 무엇이든 답하고, 없으면 관련 조문을 찾아 보여 줍니다.

    use_ai=False 면 AI를 부르지 않고 찾은 조문만 바로 돌려줍니다. 화면이 먼저
    띄우고(즉시), 다듬은 문장은 뒤이어 받아 갈아 끼웁니다.
    """
    if use_ai:
        ai = ai_general_answer(org_id, org_name, message, history)
        if ai:
            return ai
    hits = get_index(org_id).search(message, k=4)
    good = [(a, s) for a, s in hits if s >= 1.5]
    evidence = [a.as_dict(s) for a, s in good]
    tasks = [{"id": t["id"], "name": t["name"]} for t in load_tasks()]
    quoted = message.strip()[:40]

    if good:
        text = (f"'{quoted}'에 대해 정해진 서무 업무 절차는 없지만, {org_name} 규정에서 관련 있어 보이는 조문을 찾았어요. "
                "아래 근거를 눌러 원문을 확인해 보세요. 업무 절차 안내가 필요하면 아래에서 골라 주세요.")
    else:
        text = (f"'{quoted}'에 맞는 규정이나 업무를 찾지 못했어요. 저는 {org_name} 규정을 기준으로 서무 업무를 안내해요. "
                "'출장 다녀와서 정산해야 해요', '물품 30만원어치 사야 해요'처럼 상황을 말씀해 주시거나, "
                "'규정 어디서 찾아?', '뭐 할 수 있어?'처럼 저에 대해 물어보셔도 돼요.")
    return {"task": None, "kind": "unknown", "summary": text, "summary_by": "규칙",
            "evidence": evidence, "suggestions": tasks, "links": [], "docs": [],
            "summary_pending": (not use_ai) and bool(good)}
