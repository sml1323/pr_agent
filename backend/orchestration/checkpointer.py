"""체크포인터를 **고르는** 자리. 엔진은 이 파일을 모른다.

왜 파일을 새로 파나
------------------
`LangGraphEngine` 은 `BaseCheckpointSaver` 라는 **모양**만 안다 —
그게 메모리인지 파일인지 Postgres 인지는 몰라도 되고, 알면 안 된다.
M5-1 에서 정한 "엔진은 DB 를 모른다"가 그 뜻이다.

    engine.py            계약  (LangGraph 라는 단어가 없다)
    langgraph_engine.py  구현  (LangGraph 는 알지만 저장소는 모른다)
    checkpointer.py      선택  ← **여기만 저장소를 안다**

⚠️ 이 함수를 `LangGraphEngine.__init__` 안으로 옮기고 싶어지면 멈출 것.
   옮기는 순간 엔진이 Postgres 를 알게 되고, Temporal 로 갈아탈 때
   저장소 선택까지 딸려 온다.

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → **③ 워커** → ④ 그래프 → ⑤ 애그리게이터 → ⑥ 게이트

③ 워커가 부팅할 때 이 함수를 한 번 불러 엔진에 꽂는다.

무엇을 사는 물건인가
--------------------
INV-2("같은 배달 두 번 = 한 번")가 지금은 **웹훅 입구에서만** 지켜진다
(`queue/router.py` 의 `_seen_deliveries`). 문 앞은 막지만 **안에서 일하는 층은
그냥 두 번 한다** — 워커가 죽으면 이미 끝난 에이전트를 다시 부른다.
이 파일은 그 불변식을 오케스트레이션 층까지 끌고 오는 일이다.

⚠️ 그래도 "정확히 한 번"은 아니다. 살아남는 건 "죽은 순간까지 **이미 끝나 있던**"
   노드뿐이고 그건 스케줄링이 정한다 (Lesson 07 에서 실측한 비결정성).
   재개가 파는 것은 **"덜 부른다"**다. 진짜 멱등성은 M6 에서 호출 자체에 붙인다.
"""

from __future__ import annotations

import os
from contextlib import ExitStack
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.sqlite import SqliteSaver

# 프로세스가 살아 있는 동안 열린 커넥션·파일 핸들을 붙잡아 둔다.
# 체크포인터 팩토리들이 컨텍스트 매니저라서 `with` 를 벗어나면 닫힌다 —
# 워커는 종료될 때까지 계속 써야 하므로 여기에 걸어둔다.
_STACK = ExitStack()


# ─────────────────────────────────────────────────────────────
# TODO(human) ① — 어디에 저장할 것인가
#
# ── 왜 이게 판단인가 ─────────────────────────────────────────
# M5 완료 판정 ②가 이 한 줄에 걸려 있다:
#   "워커를 kill -9 로 죽이고 다시 띄우면 이미 끝난 에이전트를 다시 안 부른다."
#
# 실측 (2026-08-21): `InMemorySaver` 로 프로세스 A 에서 `run()` → `done · findings 4`,
# **프로세스 B 에서 같은 thread_id 로 `get_state()` → `not_started · findings 0`.**
# 파이썬 `defaultdict` 하나라서 프로세스와 함께 죽는다 —
# **원리적으로 판정 ②를 못 넘는다.** 라이브러리도 그렇게 적어뒀다:
#   "Only use InMemorySaver for debugging or testing purposes."
#
# ── 후보 ────────────────────────────────────────────────────
#   (A) InMemorySaver()        — 이미 설치돼 있다. 판정 ②는 못 넘는다
#   (B) SqliteSaver            — 파일 하나.  uv add langgraph-checkpoint-sqlite
#   (C) PostgresSaver          — 004 의 그 DB.  uv add langgraph-checkpoint-postgres
#
#   ⚠️ (B)(C) 는 **둘 다 지금 설치돼 있지 않다.** 확인함:
#      `No module named 'langgraph.checkpoint.sqlite'`. 공짜인 선택지는 (A) 뿐이고
#      그건 완료 판정을 못 넘는 것이다.
#
# ── 갈리는 기준 셋 ──────────────────────────────────────────
#   1. **워커가 몇 대인가** — 파일은 한 대만 본다. 두 대가 같은 sqlite 를 열면
#      잠금 다툼이 난다. 지금은 한 대지만 M4(Redis 큐) 뒤에는?
#   2. **004 의 DB 와 한 곳에 섞이나** — (C)를 고르면 LangGraph 가 자기 테이블
#      (`checkpoints`, `checkpoint_writes` …)을 우리 `reviews`·`findings` 옆에 만든다.
#      ⚠️ 그 DB 는 지금 **`docker compose up -d` 를 해야 뜬다**(재부팅을 못 넘김).
#         체크포인터가 거기 붙으면 **DB 가 안 떠 있을 때 워커가 부팅을 못 한다.**
#   3. **되돌리기 비용** — 저장된 체크포인트는 갈아탈 때 안 따라온다.
#      지금 고른 걸 M8 에서 바꾸면 그 시점의 진행 중 리뷰는 전부 처음부터다.
#
# ── 힌트 ────────────────────────────────────────────────────
# 003·004 에서 로컬 Docker Postgres 를 고른 근거가 ADR 0003 에 있다("포폴 재현성").
# 같은 근거가 여기에도 적용되나, 아니면 여긴 다른 물건인가 —
# **체크포인트는 004 와 달리 영구 보관물이 아니다**(리뷰가 끝나면 쓸모가 없다).
# INV-4(append-only)가 걸린 표와 같은 DB 에 둘 이유가 있나?
#
# ── 틀리면 뭐가 깨지나 ──────────────────────────────────────
# (A)를 고르면 코드는 돌지만 **완료 판정 ②에서 막힌다.** 조용히 통과하지 않는다 —
# 데모에서 프로세스를 나눠 돌리면 바로 드러난다.
#
# ── 골격 — 고르는 건 너, 타이핑은 안 막히게 ─────────────────
# ⚠️ 아래 세 개는 **검증된 시그니처**다 (GitHub 원본 소스에서 직접 확인, 2026-08-21).
#    공식 문서 예제는 틀렸다 — 아래 "함정" 참조.
#
#   (A) 인메모리 ─────────────────────────────
#       from langgraph.checkpoint.memory import InMemorySaver
#       return InMemorySaver()
#
#   (B) Sqlite ───────────────────────────────
#       uv add langgraph-checkpoint-sqlite
#
#       from langgraph.checkpoint.sqlite import SqliteSaver
#       saver = _STACK.enter_context(SqliteSaver.from_conn_string("checkpoints.sqlite"))
#       return saver                       # setup() 을 부르지 않는다 — 아래 함정 ②
#
#   (C) Postgres ─────────────────────────────
#       uv add langgraph-checkpoint-postgres
#
#       from langgraph.checkpoint.postgres import PostgresSaver
#       saver = _STACK.enter_context(PostgresSaver.from_conn_string(_db_url()))
#       saver.setup()                      # 이쪽은 **반드시** 부른다 — 아래 함정 ②
#       return saver
#
# ── 함정 셋 (전부 원본 소스로 확인) ─────────────────────────
#   ① **`from_conn_string` 은 `@contextmanager` 다.** 둘 다.
#      공식 문서에 `checkpointer = PostgresSaver.from_conn_string(...)` 이라고 적혀 있는데
#      **그대로 쓰면 saver 가 아니라 `_GeneratorContextManager` 객체를 받는다.**
#      그래서 이 파일 위에 `_STACK = ExitStack()` 이 있다 — `with` 블록을 벗어나면
#      커넥션이 닫히는데 워커는 종료될 때까지 써야 하므로, 스택에 걸어 수명을 늘린다.
#      📌 **문서보다 설치된 코드가 정확하다** — 이 프로젝트가 이미 여러 번 겪은 것
#         (프록시의 `chat.completions` · GitHub 재시도 · `TRUNCATE` 트리거).
#
#   ② **`setup()` 규칙이 둘이 반대다.** 독스트링 원문:
#        Postgres — "It MUST be called directly by the user"
#        Sqlite   — "called automatically when needed and **should not be called directly**"
#      같은 이름의 메서드인데 계약이 반대다. 한쪽 습관으로 다른 쪽을 쓰면 틀린다.
#
#   ③ **`from_conn_string` 은 `serde=` 를 못 넘긴다.** 안에서 `cls(conn)` 만 부른다.
#      → TODO ② 에서 (A)(직렬화기 교체)를 고르면 **이 골격을 못 쓴다.**
#        커넥션을 직접 만들어 생성자로 넘겨야 한다:
#            SqliteSaver(sqlite3.connect("checkpoints.sqlite", check_same_thread=False),
#                        serde=build_serde())
#      ⚠️ 두 TODO 가 여기서 얽힌다. ②를 먼저 정하면 ①의 모양이 정해진다.
# ─────────────────────────────────────────────────────────────
def build_checkpointer() -> BaseCheckpointSaver[Any]:
    """워커가 부팅할 때 한 번 부른다. 고른 저장소를 열어서 돌려준다.

    Returns:
        `LangGraphEngine(checkpointer=...)` 에 그대로 꽂을 수 있는 saver.
    """
    saver = _STACK.enter_context(SqliteSaver.from_conn_string("checkpoints.sqlite"))
    return saver


# ─────────────────────────────────────────────────────────────
# 확정된 결정 (2026-08-21) — 채널에 무엇을 담나: **dict 로 눕힌다**
#
# 원래 여기 `build_serde()` 가 있었다. 지웠다. 왜 지웠는지가 결정이다.
#
# ── 무엇이 문제였나 ─────────────────────────────────────────
# 노드가 `{"findings": [Finding(...)]}` 를 돌려주면 돌릴 때마다 경고가 떴다:
#   Deserializing unregistered type backend.agents.schema.Finding from checkpoint.
#   This will be blocked in a future version.
#
# ⚠️ **정리 잔소리가 아니라 보안 경계다.** 1차 출처(`serde/_msgpack.py` 모듈 독스트링):
#   "Without this, any Python callable stored in checkpoint data will be
#    **imported and executed on load**."
# 체크포인트를 읽는다는 건 거기 적힌 타입을 import 한다는 뜻이다.
#
# ── 후보 둘과 고른 이유 ─────────────────────────────────────
#   (A) 허용 목록에 Finding 을 등록한다 (JsonPlusSerializer(allowed_msgpack_modules=...))
#   (B) 노드가 `.model_dump()` 로 눕혀서 담는다                      ← **골랐다**
#
# 질문을 하나로 줄이면: **`Finding` 이 언제 바뀌나.**
# 바뀌면 (A)는 그 시점에 진행 중이던 리뷰의 체크포인트를 **못 읽는다.**
# 그리고 이 프로젝트에서 그건 가설이 아니라 일정표다 —
# **M6 이 더미 `Finding` 을 진짜 LLM 응답에 맞춰 바꾼다.**
#
# ⚠️ 게다가 (A)는 `serde=` 를 saver 생성자로 넘겨야 하는데
#    `from_conn_string` 이 그걸 안 받는다 → **위 `build_checkpointer()` 까지
#    커넥션을 직접 만드는 모양으로 되돌려야 했다.** "지금 편한 쪽"이 (A)로 보였지만 아니었다.
#
# ── 대가 — 공짜가 아니다 ────────────────────────────────────
# 읽는 쪽이 `f.severity` 가 아니라 `f["severity"]` 가 된다. M6 애그리게이터가 그 비용을 낸다.
# **검증이 사라지는 건 아니다** — `Finding(...)` 생성자가 여전히 INV-3 을 강제하고,
# `.model_dump()` 는 검증을 통과한 뒤에 부른다. **검증은 입구에서, 저장은 눕혀서.**
#
# ── 어디가 같이 바뀌었나 (세 곳이 같은 말을 해야 한다) ──────
#   · `langgraph_engine.py` `_run_specialist` → `[finding.model_dump()]`
#   · `state.py` `findings` 채널 타입        → `list[dict[str, Any]]`
#   · 여기                                    → `build_serde()` 삭제
# ─────────────────────────────────────────────────────────────


def _db_url() -> str:
    """`.env` 의 `DATABASE_URL`. Postgres 를 고른 경우에만 쓴다.

    ⚠️ 004 와 **같은 DB** 다. 없으면 부팅을 거부한다 —
       `security.py` 가 `WEBHOOK_SECRET` 에 하는 것과 같은 이유(INV-1 의 사고방식):
       설정이 빠진 채로 돌기 시작하면 조용히 잘못된 상태가 된다.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL 이 없다. .env 를 확인할 것 (docker compose up -d).")
    return url
