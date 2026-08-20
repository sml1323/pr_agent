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


def _call_agent(agent_type: AgentType) -> Finding:
    """M6 에서 **진짜 LLM 호출**이 될 자리. 지금은 흉내만 낸다.

    ⚠️ 실패하면 예외를 **던진다.** 진짜 API 도 그렇게 실패한다 —
       타임아웃, rate limit, 네트워크 끊김은 전부 예외로 온다.
       이 예외를 어떻게 다룰지가 아래 `_run_specialist` 의 판단이다.
    """
    time.sleep(_DELAYS[agent_type])
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

    return {"findings": [finding]}


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
