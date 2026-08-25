# recon: get_state after kill — StateSnapshot 의 values 는 언제 비고, 언제 다 차나
# 실행: uv run python scratch/recon_get_state_after_kill.py
# 검증: 2026-08-21 · langgraph==1.2.11 · langgraph-checkpoint-sqlite==3.1.1
#
# 답하려는 질문 (demo_m5.py TODO(human) ② 의 결정 재료):
#   ① 체크포인트가 하나도 없는 thread 의 snapshot 실물은? (소스의 `if not saved:` 분기)
#   ② mid-superstep kill 뒤의 snapshot 은 키가 빠지나, 반만 차나, 다 차나?
#   ③ (TODO ① 재료) snapshot 어딘가에 노드별 시작 시각이 있나?
#
# 출력(그대로) — 2026-08-21:
#
#   ① 체크포인트 없음 (run 을 안 부름):
#      raw:    values.keys=[]
#              created_at=None · next=()
#      engine: keys=['next_nodes', 'status'] · status=not_started
#      (그래프+0.50초 kill · 살아있었나=True)
#   ② mid-superstep kill 직후:
#      raw:    values.keys=['diff', 'failed_agents', 'findings', 'review_key']
#              created_at='2026-08-21T07:55:39.051258+00:00' · next=('security', 'testing')
#      engine: keys=['diff', 'failed_agents', 'findings', 'next_nodes', 'review_key',
#              'status'] · status=running
#   ③ PregelTask 필드: ['id', 'name', 'path', 'error', 'interrupts', 'state', 'result']
#      metadata 키:    ['parents', 'source', 'step']
#
# 📌 결론:
#   · 키가 빠지는 경우는 **딱 하나** — 체크포인트가 0개일 때 (`_prepare_state_snapshot` 의
#     `if not saved:` 분기, pregel/main.py). 그때 values={} · created_at=None → status=not_started.
#   · mid-superstep kill 은 키가 **다 차 있다** (첫 checkpoint 에 채널 4개가 이미 기록됨,
#     pending_writes 까지 적용됨). "반만 찬 dict"라는 세 번째 regime 은 없다.
#   · 따라서 "keys 2개" regime 은 관측상 **"run 을 한 번도 안 부름"과 구분 불가** —
#     invoke 직후 첫 put 전에 죽어도 not_started 로 보인다.
#   · 노드별 시작 시각은 스냅샷 어디에도 없다 (PregelTask 필드·metadata 키에 시간 없음.
#     찾아봤는데 없다) — demo TODO ① 의 후보 (C)는 직접 계측해야만 가능하다.
#
# 미검증 잔여: 첫 checkpoint put 이 invoke 후 몇 ms 지점인지(= kill 이 그 창을 맞출 확률)는
# 실측 안 함 — 데모의 0.5초 지점은 확실히 그 뒤다.

from __future__ import annotations

import os
import subprocess
import sys
import time

sys.path.insert(0, os.getcwd())

SQLITE = "recon_get_state.sqlite"
KEY = "recon-get-state-1"


def child() -> None:
    import logging

    logging.disable(logging.WARNING)
    from langgraph.checkpoint.sqlite import SqliteSaver

    from backend.orchestration.langgraph_engine import LangGraphEngine

    with SqliteSaver.from_conn_string(SQLITE) as saver:
        engine = LangGraphEngine(checkpointer=saver)
        print("READY", flush=True)
        engine.run(KEY, "diff")
        print("DONE", flush=True)


def _dump(tag: str, engine) -> None:
    """엔진의 dict 와 그 밑의 raw StateSnapshot 을 나란히 찍는다."""
    snap = engine._graph.get_state(engine._config(KEY))  # noqa: SLF001 — recon 전용
    public = engine.get_state(KEY)
    print(f"{tag}")
    print(f"   raw:    values.keys={sorted(snap.values.keys())}")
    print(f"           created_at={snap.created_at!r} · next={snap.next}")
    print(f"   engine: keys={sorted(public.keys())} · status={public['status']}")


def main() -> None:
    if os.path.exists(SQLITE):
        os.remove(SQLITE)

    from langgraph.checkpoint.sqlite import SqliteSaver

    from backend.orchestration.langgraph_engine import LangGraphEngine

    # ── ① run() 을 한 번도 안 부른 thread ──────────────────────
    # kill 이 필요 없다 — "체크포인트 없음"은 새 thread_id 로 결정적으로 만들 수 있다.
    with SqliteSaver.from_conn_string(SQLITE) as saver:
        engine = LangGraphEngine(checkpointer=saver)
        _dump("① 체크포인트 없음 (run 을 안 부름):", engine)

    # ── ② 그래프 0.5초 지점에서 kill ──────────────────────────
    worker = subprocess.Popen(
        [sys.executable, __file__, "--child"], stdout=subprocess.PIPE, text=True
    )
    assert worker.stdout is not None
    worker.stdout.readline()  # READY
    time.sleep(0.5)
    alive = worker.poll() is None
    worker.kill()
    worker.wait()
    print(f"   (그래프+0.50초 kill · 살아있었나={alive})")

    with SqliteSaver.from_conn_string(SQLITE) as saver:
        engine = LangGraphEngine(checkpointer=saver)
        _dump("② mid-superstep kill 직후:", engine)

        # ── ③ 노드 시작 시각이 스냅샷에 있나 ──────────────────
        snap = engine._graph.get_state(engine._config(KEY))  # noqa: SLF001
        t = snap.tasks[0] if snap.tasks else None
        print(f"③ PregelTask 필드: {list(t._fields) if t else '(tasks 없음)'}")
        print(f"   metadata 키:    {sorted((snap.metadata or {}).keys())}")

    os.remove(SQLITE)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child()
    else:
        main()
