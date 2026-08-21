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
from typing import Any, Literal

import httpx
import openai
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from backend.agents.schema import Finding
from backend.orchestration.engine import WorkflowEngine
from backend.orchestration.state import ReviewState

AgentType = Literal["security", "quality", "testing", "docs"]
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
def _dummy_finding(agent_type: AgentType) -> Finding:
    """M6 까지 쓸 자리표시자. 진짜 LLM 응답은 M6 에서 붙는다."""
    return Finding(
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
AGENT_TIMEOUT_SECONDS: float = 1.0


# 마감을 얼마나 자주 확인하나. 더미 전용이라 판단 자리가 아니다 —
# M6 에서 이 루프가 통째로 사라지고 SDK 의 `timeout=` 한 줄이 대신한다.
_TICK = 0.02


def _call_agent(agent_type: AgentType) -> Finding:
    """M6 에서 **진짜 LLM 호출**이 될 자리. 지금은 흉내만 낸다.

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
    return _dummy_finding(agent_type)


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
        finding = _call_agent(agent_type)

    except openai.OpenAIError as e:
        log.warning(e)
        finding = {"failed_agents": [agent_type]}
        return finding
    except Exception as e:
        log.exception(e)
        finding = {"failed_agents": [agent_type]}
        return finding

    # ⚠️ `finding` 이 아니라 `finding.model_dump()` 다 (2026-08-21, M5-6).
    #    체크포인터가 이 채널을 통째로 직렬화하는데, Pydantic 객체를 그대로 담으면
    #    저장 포맷이 `Finding` 클래스에 묶인다 — 필드가 하나 늘면 저장된 체크포인트를
    #    못 읽는다. 그리고 M6 에서 `Finding` 은 확실히 바뀐다 (근거는 `state.py` 결정 4).
    #    검증은 위 `Finding(...)` 생성자가 이미 했다. 여기서는 눕히기만 한다.
    return {"findings": [finding.model_dump()]}


def security_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("security", state)


def quality_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("quality", state)


def testing_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("testing", state)


def docs_node(state: ReviewState) -> dict[str, Any]:
    return _run_specialist("docs", state)


def _aggregate(state: ReviewState) -> dict[str, Any]:
    """애그리게이터 자리. M6 의 일이라 지금은 아무것도 안 바꾼다.

    ⚠️ 여기서 `{"findings": [...]}` 를 돌려주면 리듀서가 **또 더한다.**
       중복 제거를 하려면 리듀서를 우회하거나 다른 채널로 내야 한다 —
       G6(애그리게이터 계약)이 M6 브리핑 직전에 정할 문제다.
    """
    return {}


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

    def run(self, review_key: str, diff: str) -> None:
        initial: ReviewState = {
            "review_key": review_key,
            "diff": diff,
            "findings": [],
            "failed_agents": [],
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
    def get_state(self, review_key: str) -> dict[str, Any]:
        snapshot = self._graph.get_state(self._config(review_key))
        return {
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
