"""리뷰 그래프가 굴리는 state.

LangGraph 의 노드는 값을 "리턴"하는 게 아니라 **이 dict 를 덧칠**한다.
노드가 `{"findings": [f1]}` 를 돌려주면 그게 통째로 반환값이 아니라,
"findings 키에 이걸 보태라" 는 **패치**다.

    run() 시작   {review_key, diff, findings: [], ...}
      ↓ retrieve
      ↓ security │ quality │ testing │ docs      ← 한 superstep. 넷이 동시에 덧칠
      ↓ aggregate
    END          {..., findings: [합쳐진 것]}

⚠️ 기본 규칙은 **"한 superstep 에 한 채널당 한 값"** 이다. 넷이 같은 키에 쓰면
   조용히 덮어쓰는 게 아니라 터진다 (실측):

       InvalidUpdateError: At key 'findings': Can receive only one value per step.

   그래서 **여러 노드가 함께 쓰는 키에만** 리듀서를 단다.
   리듀서는 `Annotated[타입, 합치는_함수]` 로 선언하고, `operator.add` 는
   리스트끼리 `+` 하라는 뜻이다 — 즉 이어붙이기.

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → ③ 워커 → **④ 여기** → ⑤ 애그리게이터 → ⑥ 게이트
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class ReviewState(TypedDict):
    """그래프 한 판이 굴리는 전부.

    ⚠️ 왜 Pydantic 이 아니라 TypedDict 인가: 이건 **검증할 입력**이 아니라
       노드끼리 주고받는 **작업 공간**이다. Finding 은 LLM 이 뱉는 것이라
       검증이 필요해서 Pydantic 이지만(INV-3), state 는 우리 코드만 쓴다.
       LangGraph 도 TypedDict 를 1급으로 다룬다.
    """

    # ── 확정된 결정 (2026-08-19) — 왜 이렇게 골랐나 ──────────────
    #
    # 셈의 규칙 하나로 전부 갈렸다: **한 superstep 안에서 몇 개 노드가 이 칸에 쓰나.**
    #   둘 이상 → 리듀서 필수(없으면 InvalidUpdateError)
    #   하나거나 없음 → 안 단다
    #
    # 결정 1 · 필드 넷. `context` 는 **뺐다**
    #   · retrieve 노드의 산출물인데 M7 RAG 전엔 아무도 안 채운다.
    #     지금 파두면 "있는데 항상 빈 칸"이 되고, 그건 읽는 사람에게 거짓말이다.
    #     필요해질 때 넣는다 — `04-book-reading-plan.md` 의 저스트-인-타임과 같은 근거.
    #   · aggregate 의 산출물 자리도 같은 이유로 안 팠다. M6 의 일이다.
    #
    # 결정 2 · 리듀서는 `findings` 와 `failed_agents` 에만
    #   · 이 둘만 노드 넷이 **함께** 쓴다. 나머지 둘은 아무도 안 쓰고 읽기만 한다.
    #   · ⚠️ `diff` 에 안 다는 것이 **능동적 결정**이다. 달아두면 M6 에서 누가
    #     실수로 `{"diff": ...}` 를 반환할 때 터지는 대신 **두 배가 된 채 조용히 흘러간다.**
    #     리듀서가 없다는 건 "여기 둘이 쓰면 잡아줘"라는 방어다.
    #
    # 결정 3 · `failed_agents` 는 **이름만** 담는다 (`list[str]`)
    #   · 004_truth.sql:94 의 `failed_agents TEXT[]` 가 착지점이고, 거기 이유가 딸려 갈
    #     자리가 없다. M8 게이트가 묻는 것은 "누가 못 봤나"이지 "왜 못 봤나"가 아니다 —
    #     이유가 무엇이든 **커버리지가 비었다는 사실은 같다.**
    #   · ⚠️ 실패 이유는 M3 `record_event` 가 받을 몫이다. 여기서 겸하지 않는다.
    #   · ⚠️ `Annotated[str, operator.add]` 로 두면 안 된다 — 문자열끼리 `+` 라
    #     `'docsqualitysecuritytesting'` 처럼 **붙어버려서 원소를 못 가른다.**
    #     타입 체커도 LangGraph 도 통과시킨다. 결과만 쓸모없어진다.
    # ─────────────────────────────────────────────────────────────
    review_key: str
    diff: str
    #
    # 결정 4 · `findings` 는 **dict** 다 — Pydantic 객체가 아니다 (2026-08-21, M5-6)
    #   · 노드는 `Finding` 을 만들고 **`.model_dump()` 로 눕혀서** 담는다.
    #     이유는 검증이 아니라 **저장**이다 — 체크포인터가 이 채널을 통째로 직렬화한다.
    #   · Pydantic 객체를 그대로 두면 저장 포맷이 우리 클래스에 묶인다:
    #     `Finding` 에 필드가 하나 늘면 **저장된 체크포인트를 못 읽는다.**
    #     그리고 M6 에서 `Finding` 은 **확실히 바뀐다**(더미 → 진짜 LLM 응답).
    #   · ⚠️ 검증이 사라지는 게 아니다. `Finding(...)` 생성자가 여전히 INV-3 을 강제하고,
    #     `.model_dump()` 는 **검증을 통과한 뒤에** 부른다. 검증은 입구에서, 저장은 눕혀서.
    #   · 004 `findings` 표에서 JSON 덩어리 대신 컬럼으로 눕힌 것과 같은 가족이다 —
    #     **저장된 것은 못 고치니까, 고칠 일이 생기는 모양으로 저장하지 않는다.**
    findings: Annotated[list[dict[str, Any]], operator.add]  # 넷이 함께 쌓는다
    failed_agents: Annotated[list[str], operator.add]  # 넷이 각자 자기 실패를 보고한다
