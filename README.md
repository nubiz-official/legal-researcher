# Legal Researcher — 한국 법률 리서치 에이전트

TeamNubiz가 제공하는 한국 법률·판례·행정해석 리서치 웹 에이전트.
Anthropic Claude API 기반으로 법률 질문을 받아 4단 구조(결론 · 법적 근거 · 해석 · 주의사항)로 답변합니다.

## 두 가지 사용 모드

이 리포는 **동일한 에이전트 설계**를 두 가지 환경에서 사용할 수 있도록 구성되어 있습니다.

### 모드 1: 웹 서비스 (Streamlit · Railway 배포용)

누구나 브라우저로 접속해서 법률 질문을 할 수 있는 웹 서비스. 미팅 시연·팀 공유·외부 사용자 지원 등.

**로컬 실행**:
```bash
cd services/legal-researcher
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run streamlit_app/app.py
```

**Railway 배포**:
1. GitHub 리포 연결 (`nubiz-official/legal-researcher` 권장)
2. Railway New Project → Deploy from GitHub
3. Variables 탭에서 `ANTHROPIC_API_KEY` 설정
4. 자동 빌드 + 배포 (`Dockerfile` 기반)
5. Custom Domain 연결 (예: `legal.teamnubiz.com`)

### 모드 2: Claude Code 로컬 에이전트

개발자가 자기 로컬 Claude Code CLI에서 `korean-law` MCP 도구와 함께 전체 기능(법령 조회 · 판례 검색 · 행정해석 등 14종 MCP 도구)을 사용하는 모드.

**설치**:
```bash
# 1. 에이전트 정의 파일 복사
cp claude-agent/legal-researcher.md ~/.claude/agents/custom/

# 2. korean-law MCP 서버 설치 및 설정
# (자세한 설정은 MCP 문서 참조)

# 3. Claude Code 재시작 후 사용
```

## 아키텍처 차이

| 항목 | 웹 서비스 (Streamlit) | Claude Code 로컬 에이전트 |
|---|---|---|
| 환경 | Railway 컨테이너 | 로컬 Claude Code CLI |
| LLM 호출 | Anthropic API 직접 호출 | Claude Code 내장 |
| 법령 데이터 | Claude 학습 데이터 | `korean-law` MCP 14종 도구 (law.go.kr 실시간) |
| 판례 번호 정확도 | 학습 시점 기준 (보조 자료로만) | MCP 실시간 조회 (신뢰) |
| 사용자 접근 | 누구나 브라우저 | 로컬 Claude Code 사용자만 |
| 대상 | 외부 시연·공유 | 개발자·파워유저 |

> **향후**: `law.go.kr` 공식 API 직접 연동을 구현하면 웹 서비스도 MCP 수준의 실시간 조회가 가능해집니다 (v2 계획).

## 시스템 프롬프트

에이전트의 system prompt와 답변 템플릿은 [streamlit_app/app.py](streamlit_app/app.py)의 `SYSTEM_PROMPT` 상수에 포함되어 있습니다. 원본은 [claude-agent/legal-researcher.md](claude-agent/legal-researcher.md)입니다.

## 면책 고지

⚠️ 본 서비스는 한국 법률에 대한 **일반 정보 제공 목적**이며, 구체적 사안에 대한 법률 자문을 대체하지 않습니다. 실제 분쟁 또는 중요한 법적 결정을 앞두고 계신 경우 반드시 **변호사와 상담**하시기 바랍니다. 인용된 법령·판례 번호는 Claude 학습 데이터 시점 기준이며, 최신 개정·파기 여부는 별도 확인해 주세요.

## 참고

- 원본 에이전트 정의: `.claude/agents/custom/legal-researcher.md` (TeamNubiz 내부 기준)
- 디자인 시스템: `_hub/knowledge/nubiz_design_system.md` (TeamNubiz 통합 표준)
- 배포 스킬: `/nubiz-github-deploy`
