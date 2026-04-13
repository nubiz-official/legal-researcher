"""
Legal Researcher — 한국 법률 리서치 웹 에이전트
TeamNubiz | 2026-04-13

원본: .claude/agents/custom/legal-researcher.md (Claude Code 로컬 에이전트)
본 서비스는 원본 에이전트의 system prompt 및 답변 템플릿을 Anthropic Claude API
호출 형태로 재구현한 Streamlit 웹 서비스다.

⚠️ 한계: 로컬 Claude Code 에이전트와 달리 korean-law MCP 도구를 호출할 수 없으므로
law.go.kr API 직접 연동 전까지는 Claude의 일반 법률 지식에 기반한다. 모든 응답에
"본 답변은 일반 정보 제공 목적이며 구체적 사안은 변호사 상담을 권장합니다" 고지가 포함된다.
"""

import os
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

.question-card {
    background: #101828;
    border: 1px solid #1e293b;
    border-radius: 12px;
    padding: 20px 24px;
    margin: 12px 0;
    cursor: pointer;
    transition: all .2s;
}
.question-card:hover {
    border-color: #00c2a8;
    background: #141e30;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────── System Prompt ─────────────────────────
SYSTEM_PROMPT = """당신은 한국 법률·판례 리서치 전문 에이전트입니다.
법령·판례·행정규칙·자치법규·헌재결정·조세심판·관세해석·조약 관련 질문에 답합니다.

## 절대 원칙

1. **답변 근거 명시** — 모든 법률 판단에는 가능한 한 법률명·조문 번호·판례 번호를 인용
2. **한국법 우선** — 외국법·국제법은 한국법 적용 후 보조 언급
3. **추측 금지** — 확신하지 못하는 조문·판례 번호는 "확인 필요" 표기. 판례 번호 창작 절대 금지
4. **최신 개정 반영** — 2023년 이후 개정 여부가 중요한 질문이면 "최신 개정 확인 필요" 명시
5. **면책 고지 필수** — 모든 답변 말미에 "본 답변은 일반 정보 제공 목적이며 구체적 사안은 변호사 상담을 권장합니다" 첨부

## 표준 답변 템플릿

모든 답변은 아래 4단 구조를 따릅니다:

```
## 결론
[한 줄 결론]

## 법적 근거

### 1) 관련 법령
- 【법률명 제○조】 조문 원문 또는 요지 인용
- 【시행령 제○조】 위임 세부사항 (해당 시)
- 【시행규칙 제○조】 기술적 세부사항 (해당 시)

### 2) 관련 판례
- 【대법원 YYYY.MM.DD. 선고 ○○○○다○○○○○ 판결】 (번호 확실한 것만)
  - 판시사항: ...
  - 판결요지: ...
- 판례 번호가 불확실하면 "대법원 전원합의체 판결(구체 번호 확인 필요)" 형식으로 표기

## 해석
[조문·판례를 사실관계에 대입한 분석]

## 주의사항
[예외·한계·실무 팁]

---
본 답변은 일반 정보 제공 목적이며 구체적 사안은 변호사 상담을 권장합니다.
```

## 출력 톤

- 평이한 한국어, 법률 용어는 괄호 주석
- 실무자가 바로 활용할 수 있도록 구체적 조치까지 제시
- 단정적 어조는 확실한 것에만 사용, 불확실한 것은 "~일 수 있습니다" / "~로 해석될 여지가 있습니다"

## 질문 유형별 접근

| 질문 유형 | 답변 중점 |
|---|---|
| 특정 법률 제○조 내용 | 조문 원문 + 시행령/시행규칙 연계 |
| 권리 유무/의무 유무 | 근거 법조문 + 대법원 판례 + 예외 사유 |
| 최근 판례 경향 | 연도 명시 + 판결 요지 + 실무 영향 |
| 약칭·정식명칭 | 정식명칭 제시 + 주요 조문 요약 |
| 행정해석/질의회신 | 행정해석례 유무 + 소관 부처 |
| 헌법재판소 결정 | 사건 유형(위헌/한정위헌/합헌) + 결정 요지 |

## 금지 사항

- ❌ 판례 번호 창작/추측 (확실하지 않으면 번호 생략하고 내용만)
- ❌ 개정 전 조문을 현행처럼 인용
- ❌ "일반적으로는…" 같은 모호한 단정
- ❌ 면책 고지 없는 답변
"""


# ─────────────────────────── Anthropic API 호출 ────────────────────
def call_claude(prompt: str) -> str:
    try:
        import anthropic
    except ImportError:
        return "❌ anthropic 라이브러리가 설치되지 않았습니다. requirements.txt에 anthropic>=0.40.0 추가 후 재배포 필요."

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return "❌ ANTHROPIC_API_KEY가 설정되지 않았습니다. Railway Variables 탭에서 환경변수를 추가해주세요."

    try:
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text
    except Exception as e:
        return f"❌ API 호출 실패: {type(e).__name__}: {str(e)[:300]}"


# ─────────────────────────── Sidebar ───────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="text-align:center; padding:1.2rem 0 0.5rem;">
        <div style="font-size:1.8rem; font-weight:900;
                    background:linear-gradient(135deg,#00c2a8,#8b5cf6);
                    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
                    letter-spacing:2px;">NUBIZ</div>
        <div style="font-size:0.75rem; color:#9ca3af; margin-top:4px;">Legal Researcher</div>
        <div style="font-size:0.68rem; color:#6b7280; margin-top:2px;">한국 법률 리서치</div>
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

    st.markdown("""
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
    <div class="legal-logo">⚖️ Legal Researcher</div>
    <div class="legal-sub">한국 법률 · 판례 · 행정해석 리서치 에이전트</div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div class="disclaimer">
⚠️ <strong>면책 고지</strong>: 본 서비스는 한국 법률에 대한 일반 정보 제공 목적이며, 구체적 사안에 대한 법률 자문을 대체하지 않습니다.
실제 분쟁 또는 중요한 법적 결정을 앞두고 계신 경우 반드시 <strong>변호사와 상담</strong>하시기 바랍니다.
본 답변에 인용된 법령·판례 번호는 Claude의 학습 데이터 기준이며, 최신 개정·파기 여부는 별도로 확인해 주세요.
</div>
""", unsafe_allow_html=True)

# 세션 상태 초기화
if "legal_history" not in st.session_state:
    st.session_state["legal_history"] = []

# 질문 입력
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
    with st.spinner("한국 법률 데이터 검색 및 분석 중... (10~30초)"):
        answer = call_claude(question.strip())

    # 이력에 저장
    if not answer.startswith("❌"):
        st.session_state["legal_history"].insert(
            0,
            {
                "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "question": question.strip(),
                "answer": answer,
            },
        )
        # 질문 입력창 초기화 트리거
        st.session_state.pop("legal_question", None)

    st.markdown("---")
    st.markdown("### 🔎 답변")
    st.markdown(answer)

    if not answer.startswith("❌"):
        st.download_button(
            label="📄 답변 다운로드 (.md)",
            data=f"# 법률 리서치 답변\n\n**질문**: {question.strip()}\n\n**생성일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n{answer}",
            file_name=f"legal_research_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
            mime="text/markdown",
        )

# 이력 표시
if st.session_state["legal_history"]:
    st.markdown("---")
    st.markdown("### 📚 질문 이력")
    st.caption(f"현재 세션에서 {len(st.session_state['legal_history'])}건의 질문이 저장되어 있습니다. (브라우저 종료 시 사라짐)")

    for i, item in enumerate(st.session_state["legal_history"]):
        q_short = item["question"][:70] + ("..." if len(item["question"]) > 70 else "")
        with st.expander(f"[{item['ts']}] {q_short}", expanded=(i == 0)):
            st.markdown(f"**질문**: {item['question']}")
            st.markdown("---")
            st.markdown(item["answer"])
