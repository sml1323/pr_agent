"""Finding — 시스템 전체를 흐르는 단 하나의 단위.

여기서 정하는 스키마가 M8 게이트까지 그대로 간다.
필드 근거: docs/02-architecture.md §6.1
불변식: INV-3 — 모든 finding은 confidence와 rationale을 갖는다.
        "코드 규약"이 아니라 이 스키마가 거부하게 만드는 게 목표다.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """PR 리뷰에서 나온 지적 하나."""

    agent_type: Literal["security", "quality", "testing", "docs"] = Field(
        description="어떤 관점에서 찾았나. M0에선 하나지만 M6에서 4개 에이전트로 갈린다."
    )

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

    line: int = Field(
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
    """

    findings: list[Finding]
