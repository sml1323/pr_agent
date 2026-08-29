"""Finding — 시스템 전체를 흐르는 단 하나의 단위.

여기서 정하는 스키마가 M8 게이트까지 그대로 간다.
필드 근거: docs/02-architecture.md §6.1
불변식: INV-3 — 모든 finding은 confidence와 rationale을 갖는다.
        "코드 규약"이 아니라 이 스키마가 거부하게 만드는 게 목표다.
"""

from typing import Literal, get_args

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
    #
    # ──────────────────────────────────────────────────────────────────
    # TODO(human) ④ — **critical 과 high 의 경계를 이 description 에 적을 것인가** (M6-0a)
    #
    # ── 실측이 예상과 반대로 나왔다 (2026-08-28, `evals/runs/` 21판) ──
    #   같은 `sql-injection` 을 **critical 17 / high 4** 로 갈랐는데,
    #   **rationale 이 사실상 같다:**
    #
    #     critical  "username을 이스케이프나 파라미터 바인딩 없이 SQL 문자열에 직접
    #                연결한다. 공격자가 임의 SQL을 주입할 수 있다"
    #     high      "username이 이스케이프나 파라미터 바인딩 없이 SQL 문자열에 직접
    #                연결되어, 공격자가 임의 SQL을 주입할 수 있습니다"
    #
    #   **같은 근거에서 다른 등급이 나온다.** M6-PLAN §M6-0a 는 *"critical 판과 high 판이
    #   무엇을 다르게 봤는지가 그 문장이 된다"* 를 기대했는데 — **다르게 본 게 없다.**
    #
    #   📖 그리고 M6-PLAN 이 써둔 경고가 실측으로 확인됐다: *"⚠️ 안 닿는 곳: 책(인쇄 211)이
    #      말하는 '의견 차이'는 **서로 다른 심판 사이**의 불일치다. 우리 8:4 는 **같은
    #      프롬프트의 반복 샘플링**이라 통계적으로 다른 양이다."*
    #      → 책의 *"불일치가 루브릭을 사례집으로 키운다"* 가 **우리 데이터에선 재료를 안 준다.**
    #
    # ── 그럼 원인은 어디인가 ──────────────────────────────────────────
    #   아래 description 이 이 사례를 **안 가른다.** SQL 인젝션은
    #     "critical: 악용 가능한 취약점"  ← 맞다
    #     "high: 명백한 버그"             ← 이것도 맞다
    #   둘 다로 읽힌다. 모델이 헷갈리는 게 아니라 **우리가 안 정해줬다.**
    #
    # ── 후보 셋 ───────────────────────────────────────────────────────
    #   (a) **아무것도 안 한다** ← 잠정
    #       근거: 고치면 **모든 판이 바뀐다.** 이 description 은 곧 structured output
    #       스키마라 프롬프트의 일부다 — 방금 만든 새 베이스라인(2/3)이 또 무효가 된다.
    #       그리고 `expected.yaml` 이 이미 `severity_min: critical` 로 **자 쪽에서**
    #       기준을 정해뒀다. 두 곳에 적으면 반드시 갈라진다.
    #   (b) 경계 사례를 여기 적는다 — 예: "외부 입력이 검증 없이 실행 경로에 닿으면
    #       악용 가능성이 증명 안 돼도 critical 이다"
    #       ✅ 📖 인쇄 211 이 권하는 그것(경계 사례를 루브릭에 적기)
    #       ❌ 베이스라인 리셋 + **정책이 스키마로 샐 위험** (아래)
    #   (c) `PERSPECTIVES` 의 security 블록에 적는다 — 관점별로 다르게 가른다
    #       ❌ 넷이 같은 결함에 다른 등급을 매기게 된다. 애그리게이터가 그걸 또 골라야 한다
    #
    # ── ⚠️ 이게 정책인가 어휘인가 (`CLAUDE.md` 「하지 말 것」 3번) ────
    #   *"SQL 인젝션은 critical 이다"* 는 **도메인 판단**이지 게이트 정책이 아니다 —
    #   정책은 *"critical 이면 사람에게 보낸다"* 쪽이다. 그래서 (b) 가 금지된 건 아니다.
    #   다만 **경계가 얇다**: "악용 가능성이 증명 안 돼도" 같은 문장은 곧
    #   "무엇을 통과시키나"로 읽히기 시작한다.
    #
    # ── 틀리면 뭐가 깨지나 ────────────────────────────────────────────
    #   (a) 면: severity 흔들림이 **영구적이다.** `expected.yaml` 의 `severity_min: critical`
    #       때문에 15판 중 4판이 계속 탈락하고, 그건 프롬프트 개선으로 안 없어진다
    #   (b) 면: 베이스라인 리셋 + 이 파일이 프롬프트가 되기 시작한다
    #       (`prompts/review.py` 가 *"severity 기준을 여기 쓰지 말 것 — schema.py 가
    #       이미 담고 있다"* 고 적어둔 그 경계가 반대 방향으로 흔들린다)
    #
    # ⚠️ **잠정 = (a) 아무것도 안 한다.** 네가 뒤집을 자리다.
    #    되돌리는 조건: M6-3b 에서 **어떤 프롬프트 조합도 severity 흔들림을 못 줄이면**,
    #    그게 "프롬프트가 아니라 스키마가 병목"이라는 신호다 → 그때 (b) 로 간다.
    # ──────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────
# severity 의 **순서**. 값 자체는 위 Literal 이 정하고, 여기선 그걸 읽기만 한다.
#
# 왜 여기냐 (2026-08-28, M6-5) — 원래 `evals/grader.py` 에 있었다. 옮긴 이유는 하나다:
# **`backend/agents/aggregator.py` 도 이 순서가 필요한데, 의존 방향이
# `evals/` → `backend/` 한 방향이라 backend 가 evals 를 import 할 수 없다.**
# 복사하면 두 개가 되고, 두 개는 반드시 갈라진다.
#
# ⚠️ 손으로 다시 적지 않는다 — `get_args` 로 위 Literal 에서 **뽑는다.**
#    `severity` 에 값을 하나 더하면 이 표가 자동으로 따라온다.
#    grader.py 의 원래 주석이 그 이유를 이미 적어뒀다: *"같은 사실이 두 곳에 적히면
#    반드시 갈라진다."* 파일을 옮겨도 그 규칙은 그대로다.
#
# ⚠️ 이건 **정책이 아니라 어휘다.** "critical 이 high 보다 심각하다"는 도메인 사실이고,
#    "critical 이면 사람에게 보낸다"가 정책이다. 후자는 M8 `backend/gate/` 의 몫.
# ─────────────────────────────────────────────────────────────────────
SEVERITY_ORDER: tuple[str, ...] = get_args(Finding.model_fields["severity"].annotation)
SEVERITY_RANK: dict[str, int] = {s: i for i, s in enumerate(SEVERITY_ORDER)}


def normalize_category(raw: str) -> str:
    """표기 흔들림만 없앤다. 의미는 안 건드린다.

        "SQL-Injection" · "sql injection" · "sql_injection"  →  "sql-injection"

    📌 **이 함수는 `evals/grader.py` 에 살았다. 2026-08-29 에 여기로 옮겼다.**

    옮긴 이유 — `backend/gate/decision.py` 가 이걸 필요로 하게 됐다.
    게이트가 `category` 로 자동 게시 여부를 가르는데(`HUMAN_ONLY_CATEGORIES`),
    의존 방향이 **`evals/` → `backend/` 한 방향**이라 게이트가 grader 를 import 할 수 없다.
    남은 길은 둘이었고 하나는 틀렸다:
        (i)  게이트 안에 같은 로직을 다시 쓴다  ← **같은 사실이 두 곳에 살면 반드시 갈라진다**
        (ii) `category` 의 집(여기)으로 옮기고 grader 가 import 한다  ← 골랐다
    `SEVERITY_ORDER` 를 grader 가 복사 안 하고 import 하는 것과 **같은 규칙**이다.

    ⚠️ 그동안 안 옮긴 이유도 기록해둔다: `aggregator.py` TODO ① 이
       *"필요해지기 직전에 옮긴다(저스트-인-타임). 지금은 근거가 없다"* 라고 적어뒀고,
       실측이 그걸 뒷받침했다 — 자가 재는 셋(`sql-injection` 24/24 · `resource-leak` 17/17 ·
       `review-evasion-attempt` 10/10)은 표기가 하나도 안 흔들린다.
       **오늘 게이트가 그 근거의 전제를 바꿨다.** 흔들리면 곤란한 자리가 하나 늘었다.

    ⚠️ **부분 문자열 매칭은 열지 않는다.** 열면 `sql-injection` 이
       `missing-sql-injection-tests` 와 매칭되어 다른 결함 둘이 하나가 된다.
    ⚠️ **복수형 `s` 도 안 뗀다.** 그건 표기가 아니라 의미에 손대는 것이고,
       `access` · `status` · `credentials` 같은 이름이 category 에 들어올 수 있다.
       실측: 복수형이 갈린 건 61건 중 2건이고 둘 다 `not_graded`(채점 제외) 통이다.
    """
    # 구분자(하이픈·언더스코어·공백)를 전부 공백으로 눕힌 뒤 하이픈으로 다시 잇는다.
    # split() 이 연속 공백과 앞뒤 공백을 알아서 먹으므로 "sql  injection " 도 통과한다.
    return "-".join(raw.lower().replace("_", " ").replace("-", " ").split())


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


class MergedFinding(Finding):
    """애그리게이터(⑤)가 합친 뒤의 finding — **출처가 여럿일 수 있다.**

    ⚠️ **`agent_type`(단수)이 아니라 `sources`(복수)다.** 그게 이 타입이 따로 있는 이유다.

    `SourcedFinding` 은 "누가 찾았나"에 답이 하나였다. 합치고 나면 답이 여럿이 되고,
    **하나로 줄이면 반드시 거짓말이 된다** — D3 에서 한 필드가 두 질문에 답하려 할 때
    깨졌던 것과 같은 모양이다. 여기선 한 필드가 **여러 답**을 담아야 한다.

    ── ⚠️ `sources` 의 길이를 신뢰도로 쓰지 말 것 ──────────────────────
    실측 (2026-08-28, `fixtures/sample.diff`, 관점 넷 각 1판):

        security  [high]     sql-injection :17  conf=1.00
        quality   [critical] sql-injection :17  conf=0.99
        testing   [critical] sql-injection :15  conf=1.00
        docs      [critical] sql-injection :17  conf=1.00

    **넷이 다 잡았다.** 그런데 `docs` 프롬프트는 *"이 diff 를 처음 보는 사람이 답을 못 찾을
    질문이 남는가"* 이고 문서 얘기는 한 마디도 안 했다. 넷은 같은 모델·같은 diff·같은
    프롬프트 골격이라 **독립 증거가 아니다.**

    📖 책 인쇄 320 (10.5.3 동질적 수렴) — *"공통 모델과 스캐폴딩에서 비롯된 이런 공통 원인
       장애 때문에, **같은 모델이 비슷한 컨텍스트에서 생성한 여러 검토 의견을 자동으로
       독립 증거로 간주해서는 안 됩니다.**"*
    ⚠️ **안 닿는 곳**: 책의 사례는 에이전트 30개가 같은 브랜치 이름을 짓는 것처럼
       **행동이 겹치는** 경우다. 우리 것은 **판정이 겹치는** 경우라 결과가 더 그럴듯해 보인다 —
       겹침이 오히려 "합의"로 읽히므로 우리 쪽이 더 위험하다.

    → `len(sources)` 는 **"몇 관점이 이 줄을 건드렸나"**(커버리지 관측)이지
      **"얼마나 확실한가"**가 아니다. 게이트(M8)가 이걸 섞으면 이 시스템의 제1원칙이 깨진다.

    ── 왜 `agent_type` 을 상속에서 빼나 ──────────────────────────────
    `SourcedFinding` 이 아니라 `Finding` 을 상속한다. `SourcedFinding` 을 상속하면
    `agent_type`(단수)과 `sources`(복수)가 **둘 다** 존재하게 되고, 읽는 쪽이
    어느 게 진짜인지 물어야 한다. 같은 사실이 두 곳에 있으면 반드시 갈라진다
    (`grader.py` 가 `SEVERITY_ORDER` 를 복사 안 하고 import 하는 것과 같은 규칙).
    """

    sources: list[AgentType] = Field(
        min_length=1,
        description=(
            "이 지적을 낸 관점들. 코드가 붙인다(D3). "
            "⚠️ 개수는 커버리지 관측이지 신뢰도가 아니다 — 넷은 같은 모델이다(📖 인쇄 320)."
        ),
    )

    merged_from: int = Field(
        ge=1,
        description=(
            "합쳐지기 전 finding 의 개수. `len(sources)` 와 다를 수 있다 — "
            "한 관점이 같은 결함을 두 번 뱉는 일이 실제로 있었다(M0, PLAN.md G-M0-3)."
        ),
    )
