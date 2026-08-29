"""`WorkflowEngine` 의 LangGraph 구현체.

**이 파일에만 LangGraph 가 나온다.** `engine.py` 와 `state.py` 에는 한 번도 안 나온다 —
그게 갈아탈 수 있게 만드는 경계다. Temporal 로 옮긴다면 이 파일 옆에
`temporal_engine.py` 를 하나 더 놓는 것으로 끝나야 한다.

조립 vs 실행
------------
    __init__()   노드 등록 → 엣지 연결 → compile()      ← 딱 한 번. "설계도"
    run()        조립된 그래프에 입력을 넣고 돌린다      ← 매 리뷰마다
    resume()     같은 그래프, 체크포인트부터
    get_state()  같은 그래프, 저장된 상태 조회

⚠️ superstep 은 설계도에 없다. `invoke()` 할 때 **실행이** 긋는다.

thread_id
---------
    config = {"configurable": {"thread_id": review_key}}

`engine.py` 가 정한 `review_key` 가 여기로 들어간다. 체크포인터는 이 열쇠로
상태를 저장하고 다시 찾는다 — 죽었다 살아난 워커가 **같은 열쇠를 계산해내야**
같은 체크포인트를 연다. (1차 출처: "Pass a `thread_id` in graph config")

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → ③ 워커 → **④ 여기** → ⑤ 애그리게이터 → ⑥ 게이트
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
import openai
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from backend.agents.aggregator import aggregate
from backend.agents.base import review_diff
from backend.agents.schema import AgentType, SourcedFinding
from backend.orchestration.engine import WorkflowEngine
from backend.orchestration.state import ReviewState

# ⚠️ `AgentType` 은 여기서 정의하지 않는다 (2026-08-28, M6-4 2차 조각).
# 집은 `backend/agents/schema.py` — 도메인 어휘라서. 여기 있던 복붙이 세 번째였다.
# `AGENT_TYPES` 는 여기 남는다: **팬아웃 순서**는 오케스트레이터의 관심사다.
AGENT_TYPES: tuple[AgentType, ...] = ("security", "quality", "testing", "docs")

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# 더미 노드 넷 — M5-4 에서 sleep 과 실패 모드를 붙인다.
# 지금은 배선이 맞는지만 보는 게 목적이라 가짜 Finding 하나씩 뱉는다.
#
# ⚠️ 노드는 state 를 **편집하지 않는다.** 자기 조각만 돌려주고
#    합치는 건 리듀서 몫이다. `state["findings"] + [내것]` 을 돌려주면
#    리듀서가 또 더해서 중복된다 (Lesson 07).
#
# 넷을 한 함수로 만들 수도 있지만(클로저 / functools.partial) 명시적으로 폈다.
# M6 에서 각자 다른 프롬프트를 갖게 되면 어차피 여기서 갈린다.
# ─────────────────────────────────────────────────────────────
def _dummy_finding(agent_type: AgentType) -> SourcedFinding:
    """M6 까지 쓸 자리표시자. 진짜 LLM 응답은 M6 에서 붙는다."""
    # 2026-08-28 M6-4: `Finding` 에 agent_type 이 없어졌다 → 출처가 붙은 쪽을 쓴다.
    return SourcedFinding(
        agent_type=agent_type,
        severity="low",
        category=f"dummy-{agent_type}",
        file="fake.py",
        line=1,
        confidence=0.5,
        rationale=f"{agent_type} 더미 — M6 에서 진짜로 바뀐다",
    )


# 노드마다 **다른** 지연을 준다. 같으면 병렬인지 직렬인지 구분이 안 된다 —
# 넷이 각 0.5초일 때 직렬이면 2.0초, 병렬이면 0.5초. 다르게 주면 배리어도 보인다
# (가장 느린 노드가 층 전체의 시간을 정한다 — Lesson 08).
_DELAYS: dict[AgentType, float] = {
    "security": 0.6,
    "quality": 0.4,
    "testing": 0.8,
    "docs": 0.3,
}


def _failing_agents() -> set[str]:
    """데모에서 실패를 주입하는 통로. `M5_FAIL_AGENTS=security,docs` 처럼 쓴다.

    환경변수인 이유: 데모 스크립트가 코드를 안 고치고 실패를 만들 수 있어야 한다.
    M6 에서 진짜 LLM 이 들어오면 이 함수는 사라진다.
    """
    return {x.strip() for x in os.getenv("M5_FAIL_AGENTS", "").split(",") if x.strip()}


def _hanging_agents() -> set[str]:
    """**안 끝나는** 에이전트를 주입하는 통로. `M5_HANG_AGENTS=security` 처럼 쓴다.

    `M5_FAIL_AGENTS` 와 **다른 실패다.** 저건 `raise` 하고 이건 아무것도 안 한다 —
    에러도 없고 로그도 없고 그냥 안 돌아온다. M5-4 의 `except` 가 못 잡는 종류이고,
    superstep 이 배리어라 **나머지 셋이 끝나도 그래프 전체가 멈춘다** (Lesson 08).
    """
    return {x.strip() for x in os.getenv("M5_HANG_AGENTS", "").split(",") if x.strip()}


def _dummy_agents() -> set[str]:
    """**더미로 돌릴** 에이전트. `M5_DUMMY_AGENTS=all` 또는 `=security,docs`.

    ⚠️ 스위치가 셋으로 갈린 이유 (2026-08-28, M6-4 배선 중 실제로 깨져서 알았다):
    처음엔 `M5_FAIL_AGENTS`/`M5_HANG_AGENTS` 에 이름이 있으면 더미로 새게 했다.
    그랬더니 **`demo_m5` 판정 ①(병렬)이 원리적으로 깨졌다** — 아무 변수도 안 세우는
    시나리오라 넷이 전부 **진짜 호출**로 가고, 0.8초를 기대하는 판정식이 15초를 본다.

    갈라야 할 두 질문이 하나에 묶여 있었던 것이다:
        "이 에이전트를 **가짜로** 돌리나"      ← `M5_DUMMY_AGENTS`  (더미냐 진짜냐)
        "그 가짜가 **어떻게 실패하나**"        ← `M5_FAIL_/HANG_`   (실패 방식)
    `D3`(출처 vs 분류)와 같은 모양이다 — **한 스위치가 두 질문에 답하려 하면 한쪽이 틀린다.**

    ⚠️ `FAIL`/`HANG` 은 **더미를 함의한다.** 진짜 API 에 "지금 멈춰라"를 주입할 방법이 없다.
       이름만 적고 `DUMMY` 를 안 세워도 동작하게 두는 편이 실수를 줄인다.
    """
    named = {x.strip() for x in os.getenv("M5_DUMMY_AGENTS", "").split(",") if x.strip()}
    if "all" in named:
        return set(AGENT_TYPES)
    return named | _failing_agents() | _hanging_agents()


# ─────────────────────────────────────────────────────────────
# TODO(human) ① — 타임아웃을 몇 초로, 어떤 모양으로 둘 것인가
#
# ── 왜 이게 판단인가 ─────────────────────────────────────────
# 짧으면 **멀쩡한 응답을 실패로 기록**한다. `failed_agents` 에 이름이 올라가고
# 게이트(M8)는 "저 관점은 아무도 안 봤다"로 읽는다 — 사실은 봤는데 우리가 끊은 것이다.
# 길면 없는 것과 같다. 참고: OpenAI SDK 기본값이 **600초(10분)** 다 — 기본값이 있다는 것과
# 그 기본값이 우리에게 맞다는 건 다른 얘기다.
#
# ── 고를 것: 모양 ────────────────────────────────────────────
#   (A) 상수 하나            AGENT_TIMEOUT_SECONDS = ...
#   (B) 에이전트별 dict      {"security": ..., "quality": ...} — _DELAYS 처럼
#   (C) 환경변수로 읽기      os.getenv("AGENT_TIMEOUT", ...)
#
#   기준: **넷의 지연이 서로 다른 것이 "성질"인가 "지금 우연"인가.**
#        지금 _DELAYS 가 다른 건 병렬인지 보려고 우리가 다르게 준 것이지,
#        security 가 원래 느려서가 아니다. M6 에서 진짜 호출이 들어오면 어떻게 될까.
#   ⚠️ (B)를 고르면 M6 에서 관측값이 나올 때 **고칠 자리가 넷**이 된다.
#      (C)를 고르면 코드에 근거가 안 남는다 — 왜 그 숫자인지 아무도 모른다.
#
# ── 고를 것: 값 ─────────────────────────────────────────────
#   지금 아는 숫자는 이것뿐이다: _DELAYS 의 최대가 0.8초.
#   ⚠️ 그런데 이건 **우리가 만든 숫자**지 관측한 게 아니다 (RESOURCES.md 의 Gaps).
#      그래서 지금 고르는 값은 **잠정치**다. 중요한 건 맞는 숫자를 찍는 게 아니라
#      **왜 그 숫자인지 주석에 남겨서 M6 에서 고칠 수 있게 하는 것.**
#
# ── 정책 상수가 아닌가? ─────────────────────────────────────
#   아니다. `0.6` 같은 게이트 임계값은 "무엇을 통과시키나"라서 M8 의 몫이지만,
#   타임아웃은 **호출이 성립하는 조건**이라 호출부에 있는 게 맞다.
# ─────────────────────────────────────────────────────────────
# 결정 (2026-08-21): **상수 하나 · 1.0초.**
#   · 모양 (A) — 넷의 지연이 다른 건 병렬을 눈으로 보려고 우리가 다르게 준 것이지
#     에이전트의 성질이 아니다. 성질이 아닌 것을 네 자리에 나눠 적으면 고칠 곳이 넷이 된다.
#   · 값 1.0 — **관측이 아니라 데모 가능성에서 나온 숫자다.** 두 조건만 만족시킨다:
#       ① _DELAYS 최대(0.8초)보다 크다 → 정상 노드를 거짓 실패로 만들지 않는다
#       ② 사람이 기다릴 만하다 → M5_HANG_AGENTS 데모가 1초에 끝난다
#     처음에 180초를 넣었다가 되돌렸다. 180 은 M6 의 진짜 호출을 염두에 둔 값인데,
#     _DELAYS 가 0.8초인 지금 세계에서는 **"타임아웃 없음"과 구분이 안 되고**
#     hang 데모가 매번 3분 걸려서 완료 판정을 돌릴 수 없다.
#
# ⚠️ **M6 에서 반드시 다시 연다.** 그때 이 값은 SDK 의 `OpenAI(timeout=...)` 로 옮겨가고,
#    근거도 바뀐다 — 관측한 지연 분포가 재료가 된다 (RESOURCES.md 의 Gaps).
#    그리고 SDK 는 타임아웃 뒤 **기본 2번 재시도한다** (`DEFAULT_MAX_RETRIES = 2`) —
#    실제 최대 대기는 이 값의 3배 + 백오프다. `max_retries=` 도 같이 정할 것.
# ─────────────────────────────────────────────────────────────
# TODO(human) ⑥ — 이 값을 **누가 소유하고**, 몇 초로 두나 (M6-4 에서 다시 연다고 예고했던 자리)
#
# ── 실측이 생겼다 (n=12) ────────────────────────────────────
#     min 10.09 · median 16.84 · max 41.40 초
#   지금 값 1.0 은 **10~41배 빗나간다.** 그대로 두면 모든 노드가 매번 타임아웃이고,
#   게이트는 "넷 다 아무도 안 봤다"로 읽는다 — 사실은 우리가 매번 끊은 것이다.
#   ⚠️ n=12 로 p95 를 못 잰다 (📖 인쇄 217). n=3 일 때 최대 24.35 였는데 n=12 에서
#      41.40 으로 뛰었다 — 꼬리를 아직 못 봤다. **지금 고르는 값도 잠정치다.**
#
# ── 고를 것 1: 누가 소유하나 ────────────────────────────────
#   (A) 여기 상수 + 위 sleep 루프가 잰다        — 지금 모양. 진짜 호출엔 안 먹는다
#   (B) `base.py` 의 `OpenAI(timeout=...)`      — SDK 가 소켓에서 끊는다
#   (C) 둘 다 — SDK 가 안쪽, 오케스트레이터가 바깥 마감
#
#   기준: **타임아웃이 "호출의 성질"인가 "오케스트레이션의 정책"인가.**
#        (B) 면 `review_diff` 를 부르는 누구나(= `eval_prompt.py` 도) 같은 마감을 받는다.
#        그게 맞나? 평가는 느려도 되고 워커는 빨라야 하는 것 아닌가?
#
# ── 고를 것 2: `max_retries` ────────────────────────────────
#   SDK 기본이 **2** 다 (`openai/_constants.py`). 그래서 실제 최대 대기는
#   **timeout × 3 + 백오프** 다. 40초로 잡으면 최악 2분이 넘는다.
#   ⚠️ 그리고 **재시도는 INV-2 를 다시 연다** — 타임아웃은 취소가 아니라서(Lesson 10)
#      저쪽은 첫 요청을 계속 처리 중일 수 있다. 같은 diff 를 두 번 리뷰하는 셈이다.
#      웹훅의 delivery ID 처럼 여기에도 멱등키가 필요한가? 아니면 리뷰는 읽기 전용이라
#      두 번 해도 되나?
#
# ── 남길 것 ────────────────────────────────────────────────
#   값보다 **왜 그 값인지**가 중요하다. n=12 라는 것과, 어느 분위수를 골랐는지,
#   그리고 언제 다시 재는지를 주석에 남길 것. 2026-08-21 의 `1.0` 이 그렇게 살아남았다.
#
# ⚠️ **잠정 = (B) + 이 상수는 더미 전용으로 남긴다.** 네가 뒤집을 자리다.
#
#   진짜 호출의 마감은 `backend/agents/base.py` 의 `OpenAI(timeout=, max_retries=)` 가 쥔다.
#   이 상수는 **아래 sleep 루프(더미)만** 잰다 — 그래서 `1.0` 을 그대로 둔다.
#   1.0 을 40 으로 올리면 `demo_m5` 판정 ③(hang → 타임아웃)이 매번 40초 걸려서
#   완료 판정을 못 돌린다. 2026-08-21 에 180 을 넣었다 되돌린 것과 같은 이유다.
#
#   **왜 (B) 인가** — 마감은 *"이 호출이 성립하는 조건"*이다. `review_diff()` 를 부르는
#   누구나 같은 마감을 받는 게 맞다. `eval_prompt.py` 는 오케스트레이터를 안 지나가고
#   그 함수를 직접 부르는데, 마감이 오케스트레이터에만 있으면 **평가는 마감 없이 돈다** —
#   그리고 우리가 재는 지연 분포가 워커의 것과 달라진다. 같은 걸 재야 값이 쓸모 있다.
#
#   ⚠️ **(B) 의 대가**: 평가와 워커가 같은 마감을 쓴다. "평가는 느려도 되고 워커는
#      빨라야 한다"가 맞다면 (C)(둘 다)로 가야 하고, 그때 이 상수가 **바깥 마감**이 된다.
#      지금 (C) 를 안 고른 이유는 바깥 마감을 재려면 스레드나 시그널이 필요한데
#      (`time.monotonic()` 루프는 호출이 블록되는 동안 못 돈다) 그 복잡도를
#      정당화할 관측이 아직 없다 — SDK 마감이 안 먹히는 걸 본 적이 없다.
# ─────────────────────────────────────────────────────────────
AGENT_TIMEOUT_SECONDS: float = 1.0


# 마감을 얼마나 자주 확인하나. 더미 전용이라 판단 자리가 아니다 —
# M6 에서 이 루프가 통째로 사라지고 SDK 의 `timeout=` 한 줄이 대신한다.
_TICK = 0.02


# ─────────────────────────────────────────────────────────────
# TODO(human) ⑤ — 더미 주입 경로(`M5_FAIL_AGENTS` / `M5_HANG_AGENTS`)를 어떻게 하나
#
# 아래 함수가 진짜 호출로 바뀌면 **`demo_m5.py` 의 판정 ②③ 이 성립을 안 한다.**
#   ② kill -9 재개 — 노드가 0.8초씩 걸려야 중간에 죽일 틈이 있다. 진짜 호출은 16초라
#      틈은 오히려 넉넉하지만, 데모 한 판에 API 호출 4번이 나간다 (한도 소모)
#   ③ hang → 타임아웃 — **일부러 멈추게 할 손잡이가 사라진다.** 진짜 API 는
#      우리가 원할 때 멈춰주지 않는다
#
# 후보 셋:
#   (a) 주입 경로를 지운다 — 더미는 M5 의 유물이니 역할이 끝났다고 본다
#   (b) 환경변수가 있을 때만 더미로 샌다 — 진짜 호출은 기본, 데모는 스위치로
#   (c) `_call_agent` 를 인자로 주입받게 한다 (`engine = LangGraphEngine(call=...)`)
#
# 고르는 기준 — 📖 책 인쇄 227: *"제거 실험 인프라는 나중에 덧붙이는 것이 아니라
#   처음부터 아키텍처에 설계해야 한다. **모든 주요 기능은 독립적으로 비활성화할 수
#   있어야 한다.**"* 우리가 이 문장을 이미 두 번 따랐다 — `prompts/review.py` 의
#   `tag_rule` 토글, `checkpointer.py` 의 주입식 saver.
#   그럼 "실패를 주입하는 능력"도 같은 대접을 받아야 하나, 아니면 그건 기능이 아닌가?
#
# ⚠️ 실패 주입은 **테스트 훅이면서 동시에 위험**이다. 환경변수 하나로 프로덕션 워커가
#    조용히 가짜 답을 내놓을 수 있으면, 그건 M8 게이트가 못 잡는 종류의 사고다.
#    (b)를 고른다면 그 위험을 어디서 막을지도 같이 정할 것.
#
# 틀리면: (a) 면 `demo_m5` 판정 ③ 을 영영 못 돌린다 — 회귀를 잡을 그물이 사라진다.
#        (b)(c) 면 그물은 남지만 코드에 분기가 하나 더 산다.
# ─────────────────────────────────────────────────────────────
def _call_agent(agent_type: AgentType, diff: str) -> list[SourcedFinding]:
    """진짜 LLM 호출. **반환이 하나가 아니라 리스트다** (M6-4).

    실측 (2026-08-28, `fixtures/sample.diff`): security 관점 1개 · quality 관점 2개.
    **0개일 수도 있다** — 그 관점에서 찾을 게 없으면. 그게 실패와 구별돼야 한다.

    ── 아래는 M5 의 더미 구현이다 ──────────────────────────────

    ⚠️ 실패하면 예외를 **던진다.** 진짜 API 도 그렇게 실패한다 —
       타임아웃, rate limit, 네트워크 끊김은 전부 예외로 온다.
       이 예외를 어떻게 다룰지가 아래 `_run_specialist` 의 판단이다.

    ── 왜 `time.sleep(delay)` 한 줄이 아니라 루프인가 ──────────
    타임아웃이 **이 함수 안에서** 나야 하기 때문이다. 밖에서 재면
    `_run_specialist` 의 `try` 를 비껴가고, 그러면 실패가 값이 아니라
    예외가 되어 그래프 전체가 죽는다 (Lesson 10).

    한 번에 다 자면 마감을 확인할 틈이 없다. 잘게 자면서 확인해야
    "기다리다 포기한다"가 성립한다 — 진짜 HTTP 클라이언트가 소켓에 하는 일과
    **같은 자리에서 같은 모양으로** 터지게 맞춘 것이다.

    ⚠️ 그래도 이건 **취소가 아니다.** 우리가 기다리기를 그만두는 것뿐이고,
       진짜 API 라면 저쪽 서버는 계속 답을 만들고 있다. 재시도를 붙일 때
       INV-2 가 여기 걸린다 — M6 에서 다시 열 자리.
    """
    # ── TODO(human) ⑤ 가 이 한 줄을 정한다 ─────────────────────
    # (a) 를 고르면 이 분기와 아래 더미 전체가 사라진다.
    # (b) 면 환경변수 하나, (c) 면 이 함수가 통째로 주입 대상이 된다.
    #
    # ⚠️ **잠정 = (b).** 네가 뒤집을 자리다.
    #   **주입 대상으로 이름이 불린 에이전트만** 더미로 샌다. 나머지는 진짜로 부른다 —
    #   그래서 `M5_HANG_AGENTS=security` 인 `demo_m5` 판정 ③ 은 security 만 더미고
    #   셋은 진짜 호출이 된다. ⚠️ 그건 데모 한 판에 API 3번이라는 뜻이다(아래 판정 ③ 참조).
    #
    #   **(a) 를 안 고른 이유**: `demo_m5` 판정 ③(hang → 타임아웃 → 나머지로 진행)을
    #   영영 못 돌리게 된다. 진짜 API 는 우리가 원할 때 멈춰주지 않으므로 그 회귀를
    #   잡을 그물이 통째로 사라진다. 📖 인쇄 227 — *"모든 주요 기능은 독립적으로
    #   비활성화할 수 있어야"* 를 우리가 이미 두 번 따랐다(`tag_rule` 토글 · 주입식 saver).
    #   ⚠️ **안 닿는 곳**: 227 은 **제거 실험**(성능 기여도 측정) 얘기고, 이건
    #      **실패 주입**(장애 재현)이다. 목적이 다르다 — 빌린 건 "끌 수 있게 두라"는
    #      형태뿐이고, "그래서 이것도 기능이다"까지 따라오지 않는다.
    #
    #   **(c) 를 안 고른 이유**: `LangGraphEngine(call=...)` 로 열면 계약이 하나 는다.
    #   `engine.py` 가 *"셋보다 많이 노출하면 추상이 새기 시작한다"* 고 못박았고,
    #   `_call_agent` 는 LangGraph 구현체의 내부다. 생성자에 올리면 Temporal 구현체도
    #   같은 인자를 받아야 한다 — 안 그러면 데모가 구현체마다 갈린다.
    #
    #   ⚠️ **위험과 그 막는 자리**: 환경변수 하나로 프로덕션 워커가 조용히 가짜 답을
    #      내놓을 수 있다. M8 게이트는 그걸 못 잡는다 — 더미도 `confidence` 와
    #      `rationale` 이 있어서 INV-3 을 통과한다. 그래서 **샐 때마다 시끄럽게 짖는다**
    #      (아래 `log.warning`). 조용한 게 위험한 것이지 새는 것 자체가 위험한 게 아니다.
    #      ⬜ 더 센 가드(부팅 시 거부 등)는 **M4 워커 배선**에서 다시 본다 —
    #         지금은 워커가 없어서 "프로덕션"이라는 것도 없다.
    #
    #   📌 **스위치가 셋으로 갈린 이유는 `_dummy_agents()` 독스트링에.** 요약하면
    #      "가짜냐 진짜냐"와 "가짜가 어떻게 실패하나"는 다른 질문이고, 하나로 묶었더니
    #      `demo_m5` 판정 ①이 깨졌다. 배선하다 실제로 깨져서 알았다.
    use_dummy = agent_type in _dummy_agents()

    if use_dummy:
        # ⚠️ 이 한 줄이 (b) 의 안전장치 전부다. 지우지 말 것.
        log.warning(
            "%s: 더미 경로로 샌다 (M5_DUMMY_AGENTS / M5_FAIL_AGENTS / M5_HANG_AGENTS)."
            " 진짜 리뷰가 아니다.",
            agent_type,
        )

    if not use_dummy:
        # 여기가 그림 ④ 의 안쪽이다. `usage` 는 아직 안 쓴다 —
        # M3 의 `record_event(cost, latency, tokens)` 가 받을 자리다.
        findings, _usage = review_diff(diff, agent_type)
        return findings

    # ── 아래부터 M5 더미 ────────────────────────────────────────
    hangs = agent_type in _hanging_agents()
    started = time.monotonic()

    while True:
        elapsed = time.monotonic() - started

        # 일이 끝났다 (hang 이면 영영 이 조건이 참이 안 된다)
        if not hangs and elapsed >= _DELAYS[agent_type]:
            break

        if elapsed >= AGENT_TIMEOUT_SECONDS:
            # ─────────────────────────────────────────────────
            # TODO(human) ② — 시간이 다 됐을 때 **무엇을 던지나**
            #
            # ── 왜 이게 판단인가 ────────────────────────────
            # 아래 `_run_specialist` 의 `except` 절이 **둘**이고, 어느 쪽이
            # 받느냐에 따라 **로그가 달라진다** (Lesson 09 에서 정한 것):
            #     except openai.OpenAIError  → log.warning   (바깥 탓, 한 줄)
            #     except Exception           → log.exception (내 탓, 스택트레이스)
            #
            # 타임아웃은 **바깥 탓**이다. 그런데 파이썬 내장 `TimeoutError` 를 던지면
            # `OpenAIError` 의 자손이 아니라서 **두 번째 절**이 잡는다 —
            # 우리 버그로 기록되고, 3주 뒤 로그에 스택트레이스가 잔뜩 쌓인다.
            #
            # ── 후보 ────────────────────────────────────────
            #   (A) raise TimeoutError(...)             — 파이썬 내장. OSError 계열
            #   (B) raise RuntimeError(...)             — 위 실패 주입과 같은 모양
            #   (C) raise openai.APITimeoutError(...)   — SDK 것. M6 에서 진짜로 올 것
            #
            # ── 고르는 기준 ─────────────────────────────────
            # **더미의 일은 가짜 결과를 주는 게 아니라, 진짜와 같은 실패 경로를 만드는 것.**
            # M6 에서 이 루프가 SDK 의 `timeout=` 으로 바뀔 때 어떤 예외가 오는가 —
            # 그리고 그때 `_run_specialist` 를 **안 고쳐도 되게** 하려면 지금 뭘 던져야 하나.
            #
            # ⚠️ (C)를 고른다면 `openai.APITimeoutError` 는 생성자에 `request=` 를 요구한다.
            #    `import httpx` 후 `httpx.Request("POST", "http://dummy")` 로 만들 수 있다.
            #    ⚠️ 그리고 이건 **더미가 SDK 에 묶인다**는 뜻이기도 하다 —
            #       그게 값어치가 있는지는 판단이다.
            #
            # 틀리면 뭐가 깨지나: 게이트는 어차피 이름만 보므로 **M8 은 안 깨진다.**
            # 깨지는 건 **우리가 로그를 읽을 때** — 예상한 실패와 우리 버그가 다시 뭉개진다.
            # ─────────────────────────────────────────────────
            # 결정 (2026-08-21): (C) SDK 의 `APITimeoutError`.
            # M6 에서 SDK 가 던질 바로 그 예외라서, 이 루프가 `OpenAI(timeout=...)` 로
            # 통째로 바뀌어도 `_run_specialist` 를 **안 고친다.**
            # `request=` 는 여기서만 우리가 만든다 — 진짜 호출에서는 SDK 가 채워 넣는다
            # (`openai/_base_client.py:1083`).
            raise openai.APITimeoutError(request=httpx.Request("POST", "http://dummy"))

        time.sleep(_TICK)

    if agent_type in _failing_agents():
        raise RuntimeError(f"{agent_type}: 모의 API 실패")
    # ⚠️ 리스트다 (M6-4). 더미는 항상 1개지만 진짜 호출은 0개일 수도 있다.
    return [_dummy_finding(agent_type)]


# ─────────────────────────────────────────────────────────────
# TODO(human) — 실패를 예외가 아니라 **값**으로 바꾼다
#
# ── 왜 이게 판단인가 ─────────────────────────────────────────
# 예외를 밖으로 내보내면 `run()` 전체가 터지고, **무엇이 살아남을지가
# 비결정적**이다 (실측: security 만 터뜨렸는데 정상인 quality 까지
# 재실행 대기에 들어갔고 findings 가 3개가 아니라 2개였다).
# 완료 판정 ③("한 노드가 죽어도 애그리게이터가 나머지로 진행")은
# 여기서 통과하거나 여기서 실패한다.
#
# ── 결정 1: 어떤 예외를 잡나 ────────────────────────────────
#   (A) except Exception          — 전부 잡는다
#   (B) except (RuntimeError, ...) — 예상한 것만 잡는다
#
#   기준: **"예상한 실패"와 "우리 버그"를 같이 삼키면 어떻게 되나.**
#        API 타임아웃과 `TypeError`(우리가 오타 낸 것)가 둘 다
#        "그냥 실패한 에이전트"로 보인다. 그러면 게이트는 커버리지가
#        비었다고만 알고, 우리는 버그가 있다는 걸 영영 모른다.
#   ⚠️ 반대로 너무 좁게 잡으면 예상 못 한 API 예외 하나에 그래프가 통째로 죽는다.
#      M6 에서 OpenAI SDK 가 어떤 예외를 던지는지 모르는 상태다.
#      **지금 아는 것만으로 고르고, 왜 그렇게 골랐는지 남길 것.**
#
# ── 결정 2: 실패했을 때 무엇을 돌려주나 ─────────────────────
#   `failed_agents` 에 이름을 넣는 건 정해져 있다 (`state.py` 결정 3).
#   갈리는 건 **`findings` 키를 같이 넣을 것인가**다.
#
#     (A) return {"failed_agents": [name]}
#     (B) return {"failed_agents": [name], "findings": []}
#
#   리듀서가 붙어 있어서 **둘의 결과는 똑같다** (빈 리스트를 더해도 안 변한다).
#   그럼 왜 판단인가 — 읽는 사람에게 주는 말이 다르다.
#   기준: 다음에 이 코드를 읽는 사람이 "findings 는 어떻게 되나"를
#        **여기서 알 수 있어야 하나, 리듀서를 찾아가 봐야 하나.**
#
# ── 결정 3: 성공했을 때 failed_agents 는 ────────────────────
#   같은 질문의 뒷면이다. 성공 경로에서 `"failed_agents": []` 를 명시할 것인가.
#
# 힌트: 두 경로(성공/실패)가 **같은 모양의 dict** 를 돌려주면
#       aggregate 와 게이트가 분기를 덜 갖는다. 그게 값어치가 있는지는 네 판단이다.
# ─────────────────────────────────────────────────────────────
def _run_specialist(agent_type: AgentType, state: ReviewState) -> dict[str, Any]:
    """스페셜리스트 하나를 돌린다. 노드 넷이 전부 이걸 부른다.

    ⚠️ 이 함수는 **절대 예외를 밖으로 내보내지 않아야 한다.**
    """
    try:
        findings = _call_agent(agent_type, state["diff"])

    except openai.OpenAIError as e:
        log.warning(e)
        return {"failed_agents": [agent_type]}
    except Exception as e:
        log.exception(e)
        return {"failed_agents": [agent_type]}

    # ⚠️ `finding` 이 아니라 `finding.model_dump()` 다 (2026-08-21, M5-6).
    #    체크포인터가 이 채널을 통째로 직렬화하는데, Pydantic 객체를 그대로 담으면
    #    저장 포맷이 `Finding` 클래스에 묶인다 — 필드가 하나 늘면 저장된 체크포인트를
    #    못 읽는다. 그리고 M6 에서 `Finding` 은 확실히 바뀐다 (근거는 `state.py` 결정 4).
    #    검증은 위 `Finding(...)` 생성자가 이미 했다. 여기서는 눕히기만 한다.
    # ⚠️ 하나가 아니라 리스트다 (M6-4). 그리고 **비어 있을 수 있다** —
    #    `{"findings": []}` 는 "살아서 돌았는데 찾은 게 없다"는 뜻이고,
    #    `failed_agents` 에 이름이 오르는 것과 **다른 사실**이다.
    #    M8 게이트의 G2 가 정확히 이 둘을 갈라야 한다
    #    (근거: learning/notebooks/04-agent-type-source.ipynb §2).
    #    ⬜ 이 구분을 state 에 더 남길 게 있는지는 **다음 조각에서** 본다.
    return {"findings": [f.model_dump() for f in findings]}


def security_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("security", state)


def quality_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("quality", state)


def testing_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("testing", state)


def docs_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("docs", state)


def _aggregate(state: ReviewState) -> dict[str, Any]:
    """애그리게이터(⑤) 노드. **로직은 여기 없다** — `backend/agents/aggregator.py` 다.

    이 함수가 하는 일은 셋뿐이다: 채널에서 꺼내고 · 순수 함수를 부르고 · 다른 채널에 넣는다.
    병합 규칙이 여기 살면 Temporal 로 갈아탈 때 복붙이 되고, 단위 테스트에
    langgraph 가 필요해진다 (그 파일의 구조 결정 카드 참조).

    ⚠️ `{"findings": [...]}` 를 돌려주면 리듀서가 **또 더한다** — 실측으로 확인했다.
       `operator.add` 채널에는 덮어쓰기라는 동작이 없다. 그래서 `merged` 라는
       **다른 채널**로 낸다 (`state.py` 결정 5).

    ⚠️ **실패한 에이전트가 있어도 그냥 돈다.** `failed_agents` 를 보고 멈추지 않는다 —
       M5 완료 판정 ③("한 노드가 죽어도 나머지로 진행")이 그걸 요구하고,
       "누가 못 봤나"는 게이트(M8 · G2)가 `failed_agents` 를 직접 읽어서 판정한다.
       여기서 겸하면 정리와 판단이 섞인다.

    ── 왜 여기엔 `try` 가 없나 (`_run_specialist` 에는 있는데) ──────────
    **필요 없다는 걸 실측으로 확인했다** (2026-08-28). 일부러 터뜨려 봤다:

        run() 이 터졌다: ValueError
          status=running · findings=4 · merged=0 · next=['aggregate']   ← 결과가 살아있다
        (고친 뒤) resume 후: status=done · merged=4 · **에이전트 재호출 0회**

    스페셜리스트 넷은 **앞선 superstep** 에서 이미 체크포인트에 기록됐다.
    `_aggregate` 가 터지면 그래프는 `next=['aggregate']` 인 채로 멈추고,
    **LLM 호출 4번은 날아가지 않는다.** 고친 뒤 `resume()` 하면 aggregate 만 다시 돈다.

    → `_run_specialist` 가 예외를 삼키는 이유와 **정반대**다. 거기서 삼키는 건
      *"한 관점이 죽어도 나머지 셋은 살려야"* 하기 때문이고(같은 층에 형제가 있다),
      여기는 **혼자 있는 층**이라 삼킬 이유가 없다. 삼키면 오히려 나쁘다 —
      빈 `merged` 가 게이트에 흘러가고, 그건 "지적이 하나도 없다"로 읽힌다(G2).
      **터지는 게 정직하고, 체크포인터가 비용을 막아준다.**
    """
    return {"merged": aggregate(state["findings"], order=AGENT_TYPES)}


class LangGraphEngine(WorkflowEngine):
    """LangGraph 로 리뷰 워크플로를 돌린다."""

    def __init__(self, checkpointer: BaseCheckpointSaver | None = None) -> None:
        """
        Args:
            checkpointer: 상태를 어디에 저장할지. **주입받는다** —
                무엇을 쓸지는 M5-6 의 결정이고, 이 클래스는 몰라도 된다.
                None 이면 저장이 없다 → `resume()` 이 성립하지 않는다.
        """
        self._checkpointer = checkpointer
        self._graph = self._build()

    # ── 확정된 결정 (2026-08-19) — 배선 ─────────────────────────
    #
    # 팬아웃 · 팬인 둘 다 평범한 `add_edge` 로 만들었다.
    #   · 팬아웃: START 에서 나가는 엣지 넷 → 넷이 **같은 superstep**
    #   · 팬인:  넷에서 aggregate 로 들어가는 엣지 넷 → 넷이 다 끝나야 시작
    #   `add_conditional_edges` 를 안 쓴 이유: 갈 곳이 실행 시점에 정해지지 않는다.
    #   넷은 **항상** 돈다. 조건이 없는데 조건부 엣지를 쓰면 "항상 같은 값을 반환하는
    #   라우터 함수"가 하나 생기고, 읽는 사람이 없는 분기를 찾게 된다.
    #
    # ⚠️ `START → aggregate` 를 그으면 안 된다. aggregate 가 스페셜리스트와
    #    **같은 층**에 서게 되어 findings 를 0개 본 채로 판정한다.
    #    최종 state 는 4개라서 결과만 보면 정상으로 보인다 (Lesson 08 · Sim 08 프리셋 ③).
    #
    # ⚠️ superstep 은 **배리어**다. 엣지는 "어느 층에 서나"를 정하지
    #    "누구를 기다리나"를 정하지 않는다. 그래서 한 노드가 안 끝나면
    #    그래프 전체가 멈춘다 → M5-5 타임아웃이 필수인 이유.
    #
    # `retrieve` 는 **뺐다** — `03-build-plan.md:289` 의 그래프에는 맨 앞에 있지만,
    #   그건 M7(RAG)의 노드다. 지금은 검색할 인덱스도, 결과를 담을 `context` 채널도 없다
    #   (`state.py` 에서 같은 이유로 `context` 를 뺐다 — state 와 그래프가 같은 말을 한다).
    #   M7 에서 `context` 채널과 함께 들어온다.
    #
    # `END` 는 없어도 돌아간다(실측). 그래도 긋는 이유는 "여기가 끝"을 명시해서
    #   엣지를 빼먹은 노드와 구분하기 위해서다. M8 에서 `aggregate → gate → END` 로 늘어난다.
    # ─────────────────────────────────────────────────────────
    def _build(self):
        """노드와 엣지를 등록하고 compile 한다. 딱 한 번 불린다."""
        graph = StateGraph(ReviewState)
        # ==== node 등록 ====
        graph.add_node("security", security_node)
        graph.add_node("quality", quality_node)
        graph.add_node("testing", testing_node)
        graph.add_node("docs", docs_node)
        graph.add_node("aggregate", _aggregate)
        # ==== 엣지 ====

        ## fan-out — START 에서 넷으로 퍼진다 (하나 → 여럿)
        graph.add_edge(START, "security")
        graph.add_edge(START, "quality")
        graph.add_edge(START, "testing")
        graph.add_edge(START, "docs")

        ## fan-in — 넷에서 aggregate 로 모인다 (여럿 → 하나)
        graph.add_edge("security", "aggregate")
        graph.add_edge("quality", "aggregate")
        graph.add_edge("testing", "aggregate")
        graph.add_edge("docs", "aggregate")

        graph.add_edge("aggregate", END)

        compiled_graph = graph.compile(checkpointer=self._checkpointer)

        return compiled_graph

    # ─────────────────────────────────────────────────────────
    # 아래 셋은 배관이다 — 이미 채워져 있다.
    # ─────────────────────────────────────────────────────────
    def _config(self, review_key: str) -> RunnableConfig:
        """체크포인터가 상태를 찾는 열쇠를 LangGraph 가 아는 모양으로 싼다."""
        return {"configurable": {"thread_id": review_key}}

    # ─────────────────────────────────────────────────────────
    # TODO(human) ⑦ — G11: `run()` 멱등 가드를 어디 두나
    #
    # ── 실측 (M5 독립 검증, 2026-08-25) ─────────────────────
    #   이미 `done` 인 review_key 에 `run()` 을 다시 부르면 리듀서가 **이어붙인다**:
    #       findings 4개 → 8개. 같은 PR 에 리뷰가 두 번 붙는 모양 = **INV-2 위반.**
    #   ⚠️ 크래시 후 `running` 재실행은 안전하다 (남은 노드만 돈다).
    #      뚫린 경로는 **수동 재배달**과 **완료 후 재시도** 둘이다.
    #   ⚠️ `demo_m5` 는 `_reset_db()` 때문에 이 상태를 **못 본다** — 데모가 안 잡는 종류다.
    #
    # ── 후보 셋 (`CURRENT.md` G11) ──────────────────────────
    #   (a) **엔진 입구에서 status 보고 no-op**   ← 잠정
    #   (b) 워커가 부르기 전에 확인               — 방어가 호출부마다 는다
    #   (c) 예외를 던진다                         — 호출부가 try 를 갖게 된다
    #
    # ── 잠정을 (a) 로 둔 근거 ───────────────────────────────
    #   **같은 방어는 한 곳에서.** M5-7 에서 `get_state()` 기본값을 구현에 깐 것과 같은
    #   논리다 — 호출부가 는다(데모 → 워커 → M9 대시보드). 하나가 빼먹으면 거기서 뚫린다.
    #   **no-op 이지 예외가 아닌 이유**: `review_key` 에 `head_sha` 가 들어 있다
    #   (`engine.py` 결정 1). 같은 열쇠 = **같은 코드**다. 이미 리뷰했으면 다시 할 게 없다.
    #   예외를 던지면 수동 재배달 한 번에 워커가 죽고, 그건 INV-2 를 지키려다
    #   가용성을 깨는 것이다.
    #
    # ── ⚠️ 대가 ────────────────────────────────────────────
    #   **프롬프트를 고친 뒤 같은 PR 을 다시 리뷰할 수 없다.** M6-3b 가 정확히 그걸 한다 —
    #   다만 3b 는 `eval_prompt.py` 로 도는데 그건 엔진을 안 지나가므로 지금은 안 막힌다.
    #   막히는 순간은 M8 에서 "이 PR 다시 리뷰해줘" 버튼이 생길 때다.
    #   그때 후보: `run(..., force=True)` 로 계약을 넓히거나, 열쇠에 시도 번호를 더하거나.
    #   ⚠️ 넓히는 건 호출부를 안 깨지만 좁히는 건 깬다 (`engine.py` 결정 2 와 같은 규칙).
    #
    # ── 틀리면 뭐가 깨지나 ──────────────────────────────────
    #   가드가 없으면: 같은 PR 에 코멘트가 두 번 달린다. 사용자에게 보이는 사고다
    #   가드가 너무 세면: 재리뷰가 영영 불가능한데 **아무 소리도 안 난다** (no-op 이라서)
    #   → 그래서 `log.warning` 을 같이 남긴다. 조용한 no-op 이 제일 나쁘다
    #
    # ── ⚠️ 이 가드가 **못 막는 것 둘** (2026-08-28, 적대적 검증에서 확인) ──
    #
    #   **1. check-then-act 이다.** `get_state()` 로 읽고 `invoke()` 로 쓰는 사이에 틈이 있다.
    #      워커 둘이 동시에 `run()` 하면 **둘 다 "not_started" 를 보고** 둘 다 돈다 —
    #      LLM 호출이 8번 나가고, 리듀서가 이어붙여 findings 가 두 배가 된다.
    #      지금 안 터지는 이유는 **워커가 한 대뿐**이라서지 가드가 막아서가 아니다.
    #      ⏭ M4(Redis 큐 + ARQ)에서 워커가 늘면 그때 진짜 잠금이 필요하다.
    #         후보: 큐 레벨 잠금(잡 하나당 워커 하나) · DB `reviews_unique_head` 를
    #         선점으로 쓰기 · 체크포인터의 원자적 put 에 기대기.
    #         ⚠️ **웹훅의 `_seen_deliveries` 와 같은 문제의 다른 층이다** —
    #            거기도 인메모리라 프로세스가 늘면 뚫린다 (INV-2 의 M4 항목).
    #
    #   **2. 실패한 관점이 있는 리뷰는 영구 동결된다.** 실측:
    #
    #        M5_FAIL_AGENTS=security 로 1회차 → status=done · failed=['security']
    #        (원인을 고친 뒤) run()    → 가드가 막는다 (done)
    #                        resume() → 조용한 no-op (이미 done)
    #        → **security 없이 영원히 그대로다.**
    #
    #      이게 버그인지 계약인지가 **판단이다.** 게이트(M8)는 `failed_agents` 를 보고
    #      사람에게 보내므로 "커버리지가 빈 채 끝났다"가 정직하게 남는 건 맞다.
    #      다만 **일시적 API 실패 하나가 그 PR 의 리뷰를 영구히 반쪽으로 만든다.**
    #      ⏭ 후보: 실패한 노드만 다시 돌리는 `retry_failed(review_key)` 를 계약에 더하거나,
    #         `failed_agents` 가 비지 않으면 `status` 를 `done` 이 아니라
    #         `partial` 로 두거나(그러면 이 가드가 자동으로 안 막는다).
    #         ⚠️ 후자는 `get_state()` 의 3-상태 계약을 4-상태로 넓히는 일이라
    #            M9 대시보드까지 같이 바뀐다. **M8 게이트를 짤 때 같이 정한다.**
    # ─────────────────────────────────────────────────────────
    def run(self, review_key: str, diff: str) -> None:
        # ⚠️ 체크포인터가 없으면 `get_state()` 자체가 못 돈다 (LangGraph 가 거부한다).
        #    그 경우는 저장이 없다는 뜻이고, 저장이 없으면 중복될 상태도 없다.
        #    ⚠️ 그래서 **체크포인터 없이 쓰면 G11 가드가 통째로 없다.** 지금은 그게 맞다 —
        #       저장이 없으면 `resume()` 도 성립 안 하고, 중복될 이전 상태 자체가 없다.
        if self._checkpointer is not None:
            status = self.get_state(review_key)["status"]

            # 🔴 **`done` 만 막던 것을 `running` 까지 넓혔다** (2026-08-28, 적대적 검증).
            #    `CURRENT.md` 의 G11 항목이 *"크래시 후 `running` 재실행은 안전하다"* 고 적었고
            #    그걸 그대로 믿었는데, **그 문장은 `resume()` 얘기였다.**
            #    `run()` 은 다르다 — 실측:
            #
            #        크래시 후:        status=running · findings=4
            #        run() 재호출 후:  status=done    · findings=8   ← 리듀서가 이어붙였다
            #
            #    `run()` 의 뜻은 *"새 리뷰를 시작한다"* 이고, 체크포인트가 있다는 건
            #    **이미 시작했다**는 뜻이다. 두 문장이 동시에 참일 수 없다.
            #    `engine.py` 가 이미 그렇게 적어뒀다 — *"복구 코드는 `get_state()` 의
            #    `status` 로 먼저 갈라야 한다."* 가드가 그 규칙을 **강제**하게 만든다.
            if status == "done":
                log.warning("%s: 이미 끝난 리뷰다 — run() 을 건너뛴다 (INV-2 · G11).", review_key)
                return
            if status == "running":
                log.warning(
                    "%s: 이미 시작된 리뷰다 — run() 을 건너뛴다. 이어서 돌리려면 resume()"
                    " 을 쓸 것 (INV-2 · G11).",
                    review_key,
                )
                return

        initial: ReviewState = {
            "review_key": review_key,
            "diff": diff,
            "findings": [],
            "failed_agents": [],
            # ⚠️ `merged` 도 초기화한다. LangGraph 는 없는 키를 알아서 만들지만,
            #    여기 안 적으면 "이 그래프가 굴리는 채널이 무엇인가"가 한눈에 안 보인다.
            "merged": [],
        }
        self._graph.invoke(initial, self._config(review_key))

    def resume(self, review_key: str) -> None:
        # 입력에 None 을 주면 "새로 시작하지 말고 이어서" 라는 뜻이다.
        # 이미 끝난 노드는 per-task writes 덕에 다시 안 돈다 → INV-2.
        self._graph.invoke(None, self._config(review_key))

    # ── 확정된 결정 (2026-08-19) — get_state 가 돌려주는 것 ─────
    #
    # `StateSnapshot` 을 그대로 돌려주지 않는다. 그걸 돌려주면 호출부가
    # LangGraph 객체를 만지기 시작하고, Temporal 로 갈아탈 때 호출부까지 고쳐야 한다.
    # `engine.py` 가 약속한 대로 평범한 dict 로 눕힌다.
    #
    # 담은 것 셋:
    #   · 채널 값 전부 — `**snapshot.values` 로 **펼친다.** 중첩({"values": {...}})하면
    #     호출부가 `s["values"]["findings"]` 처럼 한 겹 더 들어가야 한다.
    #     ⚠️ 그래서 아래 두 키는 `ReviewState` 필드와 이름이 겹치면 안 된다.
    #   · `next_nodes` — 다음 층에 설 노드들. 워커 복구가 "뭐가 남았나"를 읽는다.
    #     tuple 을 list 로 바꾼 건 JSON 으로 나갈 자리(M9 대시보드)를 미리 맞춘 것이다.
    #   · `status` — 어디쯤 왔나. **이게 없으면 호출부가 추측하게 된다.**
    #     findings 0개가 "지적 없음"인지 "아직 안 끝남"인지 구분이 안 되기 때문이다
    #     (Lesson 06 — 빈 것의 뜻이 여럿이다). 판정을 여기서 한 번만 한다.
    #
    #     ⚠️ **boolean 하나로는 안 된다.** `snapshot.next` 가 비는 경우가 **둘**이다:
    #         시작 전 → next=()  created_at=None
    #         완료 후 → next=()  created_at=있음
    #     `is_done` 으로 두면 아직 시작도 안 한 리뷰가 "끝났다"로 나온다(실측).
    #     004 의 `reviews.status` 를 8개로 나눈 것과 같은 이유다 —
    #     값이 셋인 것을 참/거짓에 욱여넣으면 두 경우가 뭉개진다.
    #
    # ⚠️ 아직 안 담은 것: 실패 이유·시작 시각·소요 시간. M3 `record_event` 의 몫이고,
    #    여기 넣으면 "지금 상태"와 "무슨 일이 있었나"가 한 dict 에 섞인다.
    # ─────────────────────────────────────────────────────────
    # ── 확정된 결정 (2026-08-21, M5-7) — 키 6개는 **여기서** 보장한다 ──
    #
    # CURRENT.md 의 "열린 결정"이었다: 체크포인트가 0개면 `snapshot.values` 가 빈 dict 라
    # 약속한 6개 키 중 2개만 나갔다 (실측: scratch/recon_get_state_after_kill.py —
    # 키가 빠지는 regime 은 **이 경우 딱 하나**다. mid-superstep kill 은 4채널이 다 차 있다).
    #
    # 호출부 방어(.get) 대신 여기서 기본값을 까는 이유: 호출부가 는다 —
    # demo_m5 → 워커 복구 → M9 대시보드. 방어를 호출부마다 반복하면
    # 하나가 .get 을 빼먹는 순간 거기서 다시 터진다. 같은 방어는 한 곳에서.
    #
    # ⚠️ "빈 findings" 가 두 뜻(지적 없음 / 스냅샷 없음)이 되는 문제는 `status` 가 가른다 —
    #    기본값이 나가는 건 status="not_started" 일 때뿐이다 (Lesson 06).
    # ⚠️ review_key 는 스냅샷이 아니라 **인자**에서 돌려준다 — 없던 리뷰를 물어봐도
    #    호출자가 준 열쇠 그대로가 맞다. diff 만 빈 문자열로 남는다.
    # ─────────────────────────────────────────────────────────
    def get_state(self, review_key: str) -> dict[str, Any]:
        snapshot = self._graph.get_state(self._config(review_key))
        defaults: dict[str, Any] = {
            "review_key": review_key,
            "diff": "",
            "findings": [],
            "failed_agents": [],
            # ⚠️ 2026-08-28 (M6-5): 채널이 하나 늘었으므로 여기도 늘린다.
            #    `state.py` 결정 5 가 이 줄을 요구한다 — 안 넣으면 체크포인트가 0개일 때
            #    호출부가 `s["merged"]` 에서 KeyError 를 본다. **약속한 키는 항상 나간다.**
            "merged": [],
        }
        return {
            **defaults,
            **snapshot.values,
            "next_nodes": list(snapshot.next),
            "status": (
                "not_started"
                if snapshot.created_at is None
                else "running"
                if snapshot.next
                else "done"
            ),
        }
