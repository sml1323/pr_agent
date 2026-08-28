"""Finding — 시스템 전체를 흐르는 단 하나의 단위.

여기서 정하는 스키마가 M8 게이트까지 그대로 간다.
필드 근거: docs/02-architecture.md §6.1
불변식: INV-3 — 모든 finding은 confidence와 rationale을 갖는다.
        "코드 규약"이 아니라 이 스키마가 거부하게 만드는 게 목표다.
"""

from typing import Literal

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────
# 에이전트 넷의 이름. **여기가 이 값의 집이다** (2026-08-28, M6-4 배선).
#
# 왜 여기냐: 이건 "이 시스템에 에이전트가 넷 있다"는 **도메인 어휘**지
# 프롬프트나 오케스트레이터의 소유물이 아니다. 프롬프트가 계약을 알아야지
# 계약이 프롬프트를 알 이유가 없다 — 의존 방향을 한쪽으로만 흐르게 둔다.
#
# ⚠️ 옮기기 전엔 **세 곳에 복붙**돼 있었다:
#     backend/agents/schema.py       Finding.agent_type 의 인라인 Literal (지금은 삭제됨)
#     backend/prompts/review.py:34   AgentType = Literal[...]
#     backend/orchestration/langgraph_engine.py:46   AgentType = Literal[...]
#   앞의 둘은 여기로 모았다. `langgraph_engine.py` 는 **다음 조각에서** 모은다
#   (지금 건드리면 M6-4 배선과 섞여서 뭐 때문에 깨졌는지 못 찾는다).
#
# ⚠️ 이 넷은 `backend/prompts/review.py` 의 `PERSPECTIVES` 키와 **글자까지 같아야 한다.**
#    어긋나면 타입 검사는 통과하고 런타임에 KeyError 로 터진다.
# ─────────────────────────────────────────────────────────────────────
AgentType = Literal["security", "quality", "testing", "docs"]


class Finding(BaseModel):
    """PR 리뷰에서 나온 지적 하나.

    ⚠️ **`agent_type` 은 여기 없다** — 일부러 뺐다 (2026-08-28, D3 배선 · b2).

    원래 있었다. `Literal["security","quality","testing","docs"]` 필수 필드였고,
    이 클래스가 곧 `responses.parse(text_format=...)` 의 JSON Schema 라서
    **모델이 그 칸을 채웠다.**

    왜 뺐나 — 이 값은 "누가 찾았나"(출처)이고, **출처는 호출자가 이미 안다.**
    어느 노드를 부를지 코드가 정하니까. 아는 걸 물어보면 정확도가 100%에서
    내려갈 일만 남는다 (📖 책 10.4.4 — 전문 에이전트를 호출자가 부르는 도구로 모델링).
    "무슨 종류인가"(분류)는 아래 `category` 가 이미 답한다 — 한 필드가 두 질문에
    답하려 하면 반드시 한쪽이 틀린다.

    ⚠️ **틀리면 뭐가 깨지나**: security 노드가 `agent_type="docs"` 를 뱉으면
    결과만 봐선 security 가 0개다. 그런데 원인이 둘이다 — 죽어서 0개인가,
    찾을 게 없어서 0개인가. M8 게이트의 커버리지 판정(G2)이 **조용히 거짓말한다.**
    실측 아님/시뮬레이션 근거: `learning/notebooks/04-agent-type-source.ipynb`

    ⚠️ **확인함 (2026-08-28)**: 필드를 뺐어도 `Finding(agent_type="security", ...)` 는
    **조용히 통과한다** — pydantic 기본이 `extra="ignore"` 라서. 덕분에 옛 체크포인트·
    옛 `evals/runs/` 데이터는 안 깨지지만, **오타난 필드도 똑같이 조용히 무시된다.**
    `extra="forbid"` 로 조일지는 아직 안 정했다 (M6-4 배선이 끝나고 다시 본다).

    📌 **대신 어디서 붙나**: `backend/agents/base.py:review_diff()`.
    거기는 프롬프트를 조립하려고 `agent_type` 을 이미 인자로 갖고 있다 —
    없는 값을 새로 들여오는 게 아니라 손에 든 값을 쓰는 것이다.
    ⚠️ `_run_specialist` 가 아니라 `review_diff` 인 이유: `scripts/eval_prompt.py` 가
       오케스트레이터를 안 지나가고 `review_diff` 를 **직접 부른다.**
       거기서 붙여야 평가 데이터에도 출처가 남는다.
    """

    # M8 게이트의 첫 번째 축: critical 하나라도 있으면 무조건 사람에게.
    # 그래서 자유 문자열이면 안 된다 — "Critical" 과 "critical" 을 게이트가 다르게 본다.
    severity: Literal["critical", "high", "medium", "low", "informational"] = Field(
        description=(
            "이 지적이 사실이라고 가정했을 때 얼마나 심각한가. "
            "확신도(confidence)와는 독립이다 — 확신이 30%여도 사실이면 심각한 건 critical이다.\n"
            "critical: 악용 가능한 취약점, 데이터 손실, 서비스 중단\n"
            "high: 명백한 버그, 중요한 엣지 케이스 누락\n"
            "medium: 특정 조건에서 문제가 되는 것, 리소스 누수\n"
            "low: 동작은 하지만 고치는 편이 나은 것\n"
            "informational: 스타일, 문서 누락, 취향의 문제"
        )
    )

    category: str = Field(
        description="분류 태그. 예: sql-injection, resource-leak, missing-docstring"
    )

    file: str = Field(description="파일 경로. diff의 +++ 줄에서 나온다")

    # ge=1 인 이유: 파일에 0번 줄은 없다. 타입만 int 로 두면 모델이 "모르겠으니 0"을
    # 뱉어도 스키마가 통과시키고, M8에서 GitHub 0번 줄에 코멘트를 달려다 실패한다.
    # 실제로 M0에서 line=0 이 나왔고 완료 판정 ②를 그대로 통과했다.
    line: int = Field(
        ge=1,
        description="새 파일 기준 줄 번호. diff의 @@ 헤더를 보고 계산할 것"
    )

    # M8 게이트의 두 번째 축.
    # 범위(0~1)는 여기서 강제하지만, 임계값(초기 0.6)은 여기 두지 않는다 —
    # 그건 게이트의 정책이고 시스템이 성숙하면 바뀐다. 정책이 스키마에 새면 못 바꾼다.
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "이 지적이 사실일 확률. 심각도와 무관하게 '내가 틀렸을 가능성'만 본다.\n"
            "1.0에 가깝다: 문제가 코드에 그대로 드러나 있고, "
            "주어진 diff 안의 정보만으로 판단이 끝난다.\n"
            "0.5 근처: 문제일 가능성이 높지만 추론이 섞여 있다.\n"
            "0.0에 가깝다: diff 밖의 코드(호출부·설정·테스트·프레임워크 동작)를 "
            "봐야 확정할 수 있다.\n"
            "확신이 서로 다른 지적에 같은 숫자를 붙이지 말 것."
        ),
    )

    rationale: str = Field(
        description=(
            "왜 문제인지 + 코드의 어느 부분이 근거인지. "
            "'이거 좀 이상함'이 아니라 "
            "'16번 줄에서 username이 이스케이프 없이 쿼리 문자열에 연결됨' 수준으로."
        )
    )


class ReviewResult(BaseModel):
    """LLM 응답의 최상위 객체.

    왜 Finding 리스트를 그냥 안 쓰고 감쌌나:
    OpenAI structured output은 최상위가 배열이면 거부한다. 최상위는 반드시 object.

    ⚠️ **이건 통신 포맷이지 도메인 타입이 아니다.** API 가 요구해서 만든 껍데기라
    `review_diff()` 안에서 벗기고, 밖으로는 `list[SourcedFinding]` 만 내보낸다.
    이유는 아래 `SourcedFinding` 의 ⚠️ 를 볼 것.
    """

    findings: list[Finding]


class SourcedFinding(Finding):
    """출처가 붙은 finding — **우리 쪽 값이다.**

    `Finding` 의 여섯 필드를 전부 물려받고 `agent_type` 하나를 더한다.
    복붙이 아니라 상속이라, `Finding` 의 `line >= 1` 이나 `0 <= confidence <= 1`
    같은 제약이 그대로 따라온다. `isinstance(sf, Finding)` 도 참이다.

    왜 `Finding` 에 필드를 도로 넣지 않았나 — `Finding` 은 곧
    `responses.parse(text_format=...)` 의 JSON Schema 다. 거기 필드를 넣으면
    **모델에게 묻는 것**이 된다. 우리는 묻지 않고 코드가 붙이기로 했다 (D3, b2).
    묻는 자리와 붙이는 자리를 갈라야 해서 타입이 둘이 됐다.

    ⚠️ **`ReviewResult` 에 담아서 통째로 dump 하면 `agent_type` 이 조용히 사라진다.**
    실측 (2026-08-28):
        rr = ReviewResult(findings=[SourcedFinding(...)])
        rr.findings[0].model_dump()   → agent_type 있음   ✅  (낱개)
        rr.model_dump()               → agent_type 없음   ❌  (통째로)
    `findings` 필드의 선언 타입이 `list[Finding]` 이라 pydantic 이 그 스키마대로
    찍기 때문이다. 객체 안에는 값이 살아 있는데 결과물에서만 빠진다 — **에러도 경고도 없다.**
    → 그래서 `review_diff()` 는 `ReviewResult` 를 **밖으로 안 내보낸다.**
      없앨 수 없는 함정은 닿을 수 없게 만든다.
    """

    agent_type: AgentType = Field(
        description="누가 찾았나(출처). 모델이 아니라 코드가 붙인다 — D3 결정."
    )
