"""
Legal Researcher v2 — 한국 법률 리서치 웹 에이전트 (법제처 API 직접 연동)
TeamNubiz | 2026-04-13

v1 → v2 변경:
- Anthropic Claude Tool Use 기반으로 재설계
- 법제처 국가법령 공동활용 센터 Open API (https://open.law.go.kr) 직접 호출
- Claude가 필요에 따라 법령·판례·법령해석·헌재결정을 실시간 검색하여
  근거 있는 답변 생성
- OC 인증 방식 (query parameter), XML 응답 파싱
- 최대 5라운드의 tool_use 루프 (무한 루프 방지)

원본: .claude/agents/custom/legal-researcher.md (Claude Code 로컬 에이전트)
"""

import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

import streamlit as st

# ─────────────────────────── Page Config ───────────────────────────
st.set_page_config(
    page_title="Legal Researcher | NUBIZ",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────── 공통 CSS (13개 표준 서비스 블록) ──────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;600;700;800;900&family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@24,400,0,0&display=swap');
html, body, [class*="st-"], h1, h2, h3, h4, h5, h6, p, span, div, li, a, button, label {
    font-family: 'Noto Sans KR', sans-serif !important;
}
[data-testid="stIconMaterial"], [data-testid="stIconMaterial"] * {
    font-family: 'Material Symbols Rounded' !important;
}
h1 { font-weight: 900 !important; }
h2 { font-weight: 700 !important; }
h3 { font-weight: 600 !important; }
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent !important; }
.stDeployButton { display: none; }
section[data-testid="stSidebar"] { background: #060b16; border-right: 1px solid #1e293b; }

.nav-link {
    display: block; padding: 5px 12px; margin: 2px 0;
    color: #9ca3af; text-decoration: none !important;
    border-radius: 6px; font-size: 0.82rem; transition: all 0.2s ease;
}
.nav-link:hover { color: #00c2a8 !important; background: rgba(0,194,168,0.08); padding-left: 16px; }

.legal-hero {
    text-align: center; padding: 32px 20px 20px;
    background: linear-gradient(180deg, rgba(0,194,168,0.08) 0%, transparent 100%);
    border-radius: 16px; margin-bottom: 24px;
}
.legal-logo {
    font-size: 2rem; font-weight: 900; letter-spacing: 2px;
    background: linear-gradient(135deg, #00c2a8, #8b5cf6);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.legal-sub {
    font-size: 0.85rem; color: #9ca3af; margin-top: 6px; letter-spacing: 1px;
}
.v2-badge {
    display: inline-block; padding: 3px 10px; margin-left: 8px;
    font-size: 0.7rem; font-weight: 700; letter-spacing: .08em;
    background: rgba(0,194,168,0.15); color: #00c2a8;
    border: 1px solid rgba(0,194,168,0.4); border-radius: 10px;
    vertical-align: middle;
}

.disclaimer {
    background: rgba(232,184,75,0.08);
    border: 1px solid rgba(232,184,75,0.3);
    border-radius: 8px;
    padding: 14px 18px;
    font-size: 0.82rem;
    color: #e8b84b;
    line-height: 1.7;
    margin: 16px 0;
}

.tool-call {
    font-size: 0.78rem;
    color: #9ca3af;
    background: rgba(139,92,246,0.08);
    border-left: 3px solid #8b5cf6;
    padding: 6px 12px;
    margin: 4px 0;
    font-family: 'IBM Plex Mono', monospace;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────── 법제처 API 클라이언트 ────────────────────
LAW_BASE = "https://www.law.go.kr/DRF"
LAW_OC = os.environ.get("LAW_GO_KR_OC", "ch8773").strip() or "ch8773"

TARGET_LABELS = {
    "law": "법령",
    "prec": "판례",
    "expc": "법령해석례",
    "decc": "헌법재판소 결정",
    "admrul": "행정규칙",
}


def _http_get_xml(url: str, timeout: int = 15) -> str:
    """XML 응답을 문자열로 가져온다. SSL 검증 생략 (일부 환경에서 실패 방지)."""
    import ssl
    req = urllib.request.Request(url, headers={"User-Agent": "nubiz-legal-researcher/2.0"})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, context=ctx, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _clean_cdata(text: str) -> str:
    return re.sub(r"^<!\[CDATA\[|\]\]>$", "", (text or "").strip())


def law_search_api(target: str, query: str, display: int = 5) -> dict:
    """
    법제처 통합 검색 API 호출.
    target: law / prec / expc / decc / admrul
    """
    params = {
        "OC": LAW_OC,
        "target": target,
        "type": "XML",
        "query": query,
        "display": str(display),
    }
    url = f"{LAW_BASE}/lawSearch.do?" + urllib.parse.urlencode(params)

    try:
        xml_text = _http_get_xml(url)
    except Exception as e:
        return {"ok": False, "error": f"API 호출 실패: {type(e).__name__}: {str(e)[:150]}"}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        return {"ok": False, "error": f"XML 파싱 실패: {str(e)[:150]}"}

    total = int(root.findtext("totalCnt") or "0")
    result_code = root.findtext("resultCode") or ""
    if result_code != "00" and total == 0:
        return {"ok": True, "total": 0, "items": []}

    # target 별로 item 태그가 다름: law/prec/expc/Decc/admrul
    item_tags = {
        "law": "law",
        "prec": "prec",
        "expc": "expc",
        "decc": "Decc",
        "admrul": "admrul",
    }
    item_tag = item_tags.get(target, target)

    items = []
    for elem in root.findall(item_tag):
        item = {}
        for child in elem:
            text = _clean_cdata(child.text or "")
            if text:
                item[child.tag] = text
        if item:
            items.append(item)

    return {"ok": True, "total": total, "items": items}


def format_search_result(target: str, result: dict) -> str:
    """Claude에 전달할 검색 결과 요약 텍스트 생성."""
    label = TARGET_LABELS.get(target, target)
    if not result.get("ok"):
        return f"[{label} 검색 실패] {result.get('error', 'unknown')}"

    total = result["total"]
    items = result["items"]
    if total == 0 or not items:
        return f"[{label} 검색] 결과 없음 (totalCnt=0). 다른 키워드로 재시도 권장."

    lines = [f"[{label} 검색] 총 {total}건 중 상위 {len(items)}건:\n"]

    # target 별 핵심 필드 매핑
    field_map = {
        "law": [
            ("법령명한글", "법령명"),
            ("법령일련번호", "MST"),
            ("공포일자", "공포일"),
            ("소관부처명", "소관부처"),
            ("법령구분명", "구분"),
            ("시행일자", "시행일"),
        ],
        "prec": [
            ("사건명", "사건명"),
            ("사건번호", "사건번호"),
            ("선고일자", "선고일"),
            ("법원명", "법원"),
            ("판결유형", "판결유형"),
            ("사건종류명", "사건종류"),
            ("판례일련번호", "판례ID"),
        ],
        "expc": [
            ("안건명", "안건명"),
            ("해석기관명", "해석기관"),
            ("회신일자", "회신일"),
            ("안건번호", "안건번호"),
            ("해석례일련번호", "해석ID"),
        ],
        "decc": [
            ("사건명", "사건명"),
            ("사건번호", "사건번호"),
            ("종국일자", "종국일"),
            ("종국결과", "결정유형"),
            ("헌재결정례일련번호", "결정ID"),
        ],
        "admrul": [
            ("행정규칙명", "규칙명"),
            ("행정규칙일련번호", "규칙ID"),
            ("발령일자", "발령일"),
            ("소관부처명", "소관부처"),
            ("행정규칙종류", "종류"),
        ],
    }
    fields = field_map.get(target, [])

    for i, item in enumerate(items, 1):
        lines.append(f"{i}. " + (item.get(fields[0][0], "(이름 없음)") if fields else "(이름 없음)"))
        for key, label_ko in fields[1:]:
            val = item.get(key, "")
            if val:
                lines.append(f"   - {label_ko}: {val}")
        lines.append("")

    return "\n".join(lines).strip()


# ─────────────────────────── Claude Tool 정의 ──────────────────────
TOOLS = [
    {
        "name": "search_law",
        "description": "법제처 국가법령 API에서 법령명·키워드로 현행 법령을 검색합니다. 예: '민법', '근로기준법', '전자상거래법'. 법령명·MST(법령일련번호)·공포일자·소관부처·시행일 반환.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색할 법령명 또는 키워드"},
                "display": {"type": "integer", "description": "반환 결과 수 (기본 5, 최대 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_precedent",
        "description": "법제처 판례 검색 API. 법률 용어(예: '하자담보책임', '청약철회', '부당해고')로 대법원·하급심 판례 검색. 사건명·사건번호·선고일자·법원·판결유형 반환. 문장보다는 단일 법률 용어가 효과적.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색할 법률 용어 또는 키워드"},
                "display": {"type": "integer", "description": "반환 결과 수 (기본 5, 최대 10)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_interpretation",
        "description": "법제처 법령해석례 검색. 정부 부처가 법령 조문의 의미를 해석한 공식 회신. 안건명·해석기관·회신일자 반환. 판례가 없는 애매한 조문 해석에 유용.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색할 키워드"},
                "display": {"type": "integer", "description": "반환 결과 수 (기본 5)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_constitutional_decision",
        "description": "헌법재판소 결정례 검색. 위헌·한정위헌·합헌·각하 등 헌재 결정 검색. 기본권 관련 질문에 사용. 사건명·사건번호·종국일자·종국결과 반환.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색할 키워드"},
                "display": {"type": "integer", "description": "반환 결과 수 (기본 5)"},
            },
            "required": ["query"],
        },
    },
]


def execute_tool(name: str, inp: dict) -> str:
    """Claude가 호출한 tool을 실행하여 텍스트 결과 반환."""
    query = (inp or {}).get("query", "").strip()
    display = int((inp or {}).get("display", 5))
    display = max(1, min(display, 10))

    if not query:
        return "오류: query 파라미터가 비어있습니다."

    target_map = {
        "search_law": "law",
        "search_precedent": "prec",
        "search_interpretation": "expc",
        "search_constitutional_decision": "decc",
    }
    target = target_map.get(name)
    if target is None:
        return f"오류: 알 수 없는 도구 '{name}'"

    result = law_search_api(target, query, display)
    return format_search_result(target, result)


# ─────────────────────────── System Prompt ─────────────────────────
SYSTEM_PROMPT = """당신은 한국 법률·판례 리서치 전문 에이전트입니다.
법령·판례·행정해석·헌재결정 관련 질문을 받으면 **반드시 제공된 도구를 먼저 호출**하여
법제처 국가법령 공동활용 센터(open.law.go.kr)의 공식 데이터를 조회한 뒤 답변합니다.

## 도구 사용 원칙

1. **반드시 도구 먼저 호출**: 법률 판단이 필요한 질문에 추측이나 일반 지식으로 답하지 말고
   가장 적합한 도구(search_law / search_precedent / search_interpretation /
   search_constitutional_decision)를 먼저 호출하여 근거를 확보할 것.
2. **검색 키워드 최소화**: 법령은 짧은 정식명칭("민법", "근로기준법"), 판례는 단일 법률
   용어("하자담보책임", "청약철회", "부당해고") 사용. 긴 문장은 ❌.
3. **단계적 탐색**: 법령 검색 → 관련 판례 검색 → 필요시 법령해석례 검색 순. 한 질문에
   최대 3~4회 도구 호출이 적정.
4. **검색 결과 0건이면 키워드 변형**: 1회까지 재시도, 그래도 0건이면 답변에 명시.

## 절대 원칙

1. **답변 근거 명시** — 도구에서 확인된 법령명·MST·판례 사건번호·선고일자를 그대로 인용
2. **한국법 우선** — 외국법·국제법은 한국법 적용 후 보조 언급
3. **추측 금지** — 도구에서 확인되지 않은 조문 번호·판례 번호는 절대 창작 금지
4. **면책 고지 필수** — 모든 답변 말미에 "본 답변은 일반 정보 제공 목적이며 구체적 사안은
   변호사 상담을 권장합니다" 첨부

## 표준 답변 템플릿

모든 답변은 아래 4단 구조를 따릅니다:

```
## 결론
[한 줄 결론]

## 법적 근거

### 1) 관련 법령
- 【법률명(MST)】 조문 요지 — 도구 검색 결과 기반
- 공포일 / 소관부처 명시

### 2) 관련 판례 / 법령해석 / 헌재결정
- 【법원명 YYYY.MM.DD. 선고 ○○○○다○○○○○ 판결】 (도구로 확인된 것만)
  - 사건명, 판결유형

## 해석
[도구로 확보한 근거를 사실관계에 대입한 분석]

## 주의사항
[예외·한계·실무 팁, 최신 개정 확인 필요 여부]

---
본 답변은 일반 정보 제공 목적이며 구체적 사안은 변호사 상담을 권장합니다.
```

## 출력 톤

- 평이한 한국어, 법률 용어는 괄호 주석
- 실무자가 바로 활용할 수 있도록 구체적 조치까지 제시
- 도구에서 0건 검색되면 "법제처 API에서 직접 관련 판례를 찾지 못해 일반 법률 해석으로
  답변드립니다"로 명시

## 금지 사항

- ❌ 도구 호출 없이 법률 조언
- ❌ 판례 번호 창작 (확신 없으면 생략)
- ❌ "일반적으로는…" 같은 모호한 단정
- ❌ 면책 고지 없는 답변
"""


# ─────────────────────────── Anthropic Tool Use 루프 ──────────────
MAX_TOOL_ROUNDS = 5


def call_claude_with_tools(question: str, status_container) -> tuple[str, list[dict]]:
    """
    Claude Tool Use 루프 실행.
    반환: (최종 답변 텍스트, 호출된 tool 로그 리스트)
    """
    try:
        import anthropic
    except ImportError:
        return ("❌ anthropic 라이브러리가 설치되지 않았습니다.", [])

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return ("❌ ANTHROPIC_API_KEY가 설정되지 않았습니다. Railway Variables 탭에서 환경변수를 추가해주세요.", [])

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": "user", "content": question}]
    tool_log = []

    for round_idx in range(MAX_TOOL_ROUNDS):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
        except Exception as e:
            return (f"❌ Claude API 호출 실패: {type(e).__name__}: {str(e)[:250]}", tool_log)

        if response.stop_reason != "tool_use":
            # 최종 답변 추출
            final = ""
            for block in response.content:
                if getattr(block, "type", None) == "text":
                    final += block.text
            return (final or "(응답 비어있음)", tool_log)

        # tool_use 처리
        assistant_content = response.content
        tool_results = []
        for block in assistant_content:
            if getattr(block, "type", None) == "tool_use":
                tname = block.name
                tinput = block.input or {}
                query_preview = tinput.get("query", "")[:40]
                status_container.markdown(
                    f'<div class="tool-call">🔍 법제처 API 호출 · <strong>{tname}</strong>(query="{query_preview}")</div>',
                    unsafe_allow_html=True,
                )
                result_text = execute_tool(tname, tinput)
                tool_log.append({
                    "round": round_idx + 1,
                    "tool": tname,
                    "input": tinput,
                    "result_preview": result_text[:400],
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_text,
                })

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

    return (f"⚠️ 최대 도구 호출 횟수({MAX_TOOL_ROUNDS}) 초과. 복잡한 질문이라 현재 답변을 생성할 수 없습니다. 더 구체적인 질문으로 재시도 부탁드립니다.", tool_log)


# ─────────────────────────── Sidebar ───────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:1.2rem 0 0.5rem;">
        <div style="font-size:1.8rem; font-weight:900;
                    background:linear-gradient(135deg,#00c2a8,#8b5cf6);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                    letter-spacing:2px;">NUBIZ</div>
        <div style="font-size:0.75rem; color:#9ca3af; margin-top:4px;">Legal Researcher v2</div>
        <div style="font-size:0.68rem; color:#6b7280; margin-top:2px;">한국 법률 리서치 · 법제처 API 연동</div>
    </div>
    <hr style="border-color:#1e293b;">
    """, unsafe_allow_html=True)

    st.markdown("### 빠른 질문")

    sample_questions = [
        "부당해고를 당했을 때 구제 절차는?",
        "전자상거래 청약철회 기한과 예외 사유는?",
        "상가임대차 계약갱신요구권은 몇 년?",
        "하자담보책임 제척기간은?",
        "저작권 침해 손해배상 산정 방식은?",
        "공정거래법상 시장지배적 지위 남용 기준은?",
    ]

    for i, q in enumerate(sample_questions):
        if st.button(q, key=f"sq_{i}", use_container_width=True):
            st.session_state["legal_question"] = q

    st.markdown(f"""
    <hr style="border-color:#1e293b;">
    <div style="font-size:0.72rem; color:#6b7794; padding:6px 0;">
        <strong style="color:#9ca3af;">API 상태</strong><br>
        법제처 Open API 연동<br>
        OC: <code style="color:#00c2a8;">{LAW_OC}</code><br>
        엔드포인트: law.go.kr/DRF
    </div>
    <hr style="border-color:#1e293b;">
    <a class="nav-link" href="https://www.teamnubiz.com" target="_blank">홈페이지</a>
    <a class="nav-link" href="https://www.teamnubiz.com/projects" target="_blank">프로젝트</a>
    <hr style="border-color:#1e293b;">
    <div style="text-align:center; padding:6px 0;">
        <a href="https://teamnubiz.com" target="_blank" style="color:#00c2a8; text-decoration:none; font-size:0.8rem;">teamnubiz.com</a><br>
        <span style="color:#4b5563; font-size:0.7rem;">contact@teamnubiz.com</span>
    </div>
    """, unsafe_allow_html=True)


# ─────────────────────────── Main ──────────────────────────────────
st.markdown("""
<div class="legal-hero">
    <div class="legal-logo">⚖️ Legal Researcher<span class="v2-badge">v2 · 법제처 API</span></div>
    <div class="legal-sub">한국 법률 · 판례 · 행정해석 · 헌재결정 실시간 리서치</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="disclaimer">
⚠️ <strong>면책 고지</strong>: 본 서비스는 한국 법률에 대한 <strong>일반 정보 제공</strong> 목적이며,
구체적 사안에 대한 법률 자문을 대체하지 않습니다. 응답에 포함된 법령·판례는
법제처 국가법령 공동활용 센터(<code>open.law.go.kr</code>) Open API에서 실시간 조회한 결과이며,
Claude가 해석·요약한 것입니다. 실제 분쟁 또는 중요한 법적 결정을 앞두고 계신 경우 반드시
<strong>변호사와 상담</strong>하시기 바랍니다.
</div>
""", unsafe_allow_html=True)

if "legal_history" not in st.session_state:
    st.session_state["legal_history"] = []

col_q, col_btn = st.columns([5, 1])
with col_q:
    question = st.text_area(
        "법률 질문을 입력하세요",
        value=st.session_state.get("legal_question", ""),
        placeholder="예) 임차인이 월세를 2개월 연체했을 때 임대인의 권리와 의무는 무엇인가요?",
        height=100,
        key="legal_question_input",
    )
with col_btn:
    st.markdown("<br>", unsafe_allow_html=True)
    submit = st.button("🔍 리서치", use_container_width=True, type="primary")

if submit and question.strip():
    status_area = st.empty()
    status_area.info("⏳ Claude가 질문을 분석하고 법제처 API를 호출합니다...")

    tool_status = st.container()

    with st.spinner("한국 법률 데이터 검색 및 분석 중... (15~40초)"):
        answer, tool_log = call_claude_with_tools(question.strip(), tool_status)

    status_area.empty()

    if not answer.startswith("❌") and not answer.startswith("⚠️"):
        st.session_state["legal_history"].insert(
            0,
            {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "question": question.strip(),
                "answer": answer,
                "tool_log": tool_log,
            },
        )
        st.session_state.pop("legal_question", None)

    st.markdown("---")

    if tool_log:
        with st.expander(f"🛠️ 법제처 API 호출 이력 ({len(tool_log)}회)", expanded=False):
            for entry in tool_log:
                st.markdown(f"**Round {entry['round']}** · `{entry['tool']}` · query=`{entry['input'].get('query', '')}`")
                st.code(entry["result_preview"], language="text")

    st.markdown("### 🔎 답변")
    st.markdown(answer)

    if not answer.startswith("❌") and not answer.startswith("⚠️"):
        st.download_button(
            label="📄 답변 다운로드 (.md)",
            data=f"# 법률 리서치 답변\n\n**질문**: {question.strip()}\n\n**생성일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n**데이터 출처**: 법제처 국가법령 공동활용 센터 Open API\n\n---\n\n{answer}",
            file_name=f"legal_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
        )

if st.session_state["legal_history"]:
    st.markdown("---")
    st.markdown("### 📚 질문 이력")
    st.caption(f"현재 세션에서 {len(st.session_state['legal_history'])}건 저장 (브라우저 종료 시 사라짐)")

    for i, item in enumerate(st.session_state["legal_history"]):
        q_short = item["question"][:70] + ("..." if len(item["question"]) > 70 else "")
        with st.expander(f"[{item['ts']}] {q_short}", expanded=(i == 0)):
            st.markdown(f"**질문**: {item['question']}")
            if item.get("tool_log"):
                st.caption(f"법제처 API 호출 {len(item['tool_log'])}회")
            st.markdown("---")
            st.markdown(item["answer"])
