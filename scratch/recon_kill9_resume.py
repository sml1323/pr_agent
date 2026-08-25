# recon: kill -9 후 재개 — 데모에서 워커를 진짜로 죽이고 이어붙이려면 뭘 타이핑하나
# 실행: uv run python scratch/recon_kill9_resume.py
# 검증: 2026-08-21 · CPython 3.13.5 (stdlib subprocess/signal) · langgraph 1.2.11
#       langgraph-checkpoint-sqlite (프로젝트에 설치됨)
#
# 답하려는 질문:
#   ① Popen.kill() 이 정말 SIGKILL 인가 (셸의 kill -9 와 같은가)
#   ② 이미 끝난 프로세스를 kill() 하면 어떻게 되나 — 데모가 거짓말하지 않으려면
#   ③ SIGKILL 을 자식이 가로채서 "정리하고 죽을" 수 있나
#   ④ 부모의 sleep(0.5) 는 "그래프 0.5초 지점"인가
#   ⑤ 그래서 진짜 워커를 죽였다 살리면 M5 완료 판정 ②가 통과하나
#
# 출력(그대로) — 파일 맨 아래 주석 참조

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time

sys.path.insert(0, os.getcwd())

PY = sys.executable
SQLITE = "recon_checkpoints.sqlite"
KEY = "recon-pr-1"


def child() -> None:
    """자식 — 그래프를 끝까지 돌린다.

    ⚠️ `READY` 를 먼저 찍는다. 부모가 이걸 보고 나서 시계를 재야
       "그래프 시작 후 N초"가 성립한다 (함정 ④).
    """
    import logging

    logging.disable(logging.WARNING)
    from langgraph.checkpoint.sqlite import SqliteSaver

    from backend.orchestration.langgraph_engine import LangGraphEngine

    with SqliteSaver.from_conn_string(SQLITE) as saver:
        engine = LangGraphEngine(checkpointer=saver)
        print("READY", flush=True)  # ← import·조립이 끝난 시점
        engine.run(KEY, "diff")
        print("DONE", flush=True)  # kill 되면 이 줄이 안 나온다


def main() -> None:
    # ── ① Popen.kill() 은 SIGKILL 인가 ──────────────────────
    p = subprocess.Popen([PY, "-c", "import time; time.sleep(5)"])
    time.sleep(0.2)
    p.kill()
    rc = p.wait()  # ⚠️ wait() 를 안 부르면 좀비가 남는다
    print(f"① p.kill() → returncode={rc}  (-{int(signal.SIGKILL)} 이면 SIGKILL)")

    # ── ② 이미 끝난 프로세스를 kill() 하면 ─────────────────
    p = subprocess.Popen([PY, "-c", "pass"])
    p.wait()
    p.kill()  # 예외가 안 난다. 아무 일도 안 일어난다
    print(f"② 끝난 프로세스에 kill() → 예외 없음 · returncode={p.returncode}")

    # ── ③ SIGKILL 을 가로챌 수 있나 ────────────────────────
    src = (
        "import signal\n"
        "try:\n"
        "    signal.signal(signal.SIGKILL, lambda *a: None)\n"
        "    print('   child: 핸들러 등록됨')\n"
        "except OSError as e:\n"
        "    print(f'   child: {type(e).__name__}: {e}')\n"
    )
    print("③ SIGKILL 에 핸들러를 달아보면:")
    subprocess.run([PY, "-c", src], check=True)

    # ── ④ 자식 시작 오버헤드 ───────────────────────────────
    if os.path.exists(SQLITE):
        os.remove(SQLITE)
    spawn = time.perf_counter()
    worker = subprocess.Popen([PY, __file__, "--child"], stdout=subprocess.PIPE, text=True)
    assert worker.stdout is not None
    worker.stdout.readline()  # "READY" 를 기다린다
    overhead = time.perf_counter() - spawn
    print(f"④ 자식이 READY 까지 {overhead:.2f}초 — 그래프는 아직 0초다")

    # ── ⑤ 그래프 시작 후 0.5초에 죽인다 ────────────────────
    time.sleep(0.5)
    alive = worker.poll() is None  # ⚠️ 정말 살아 있을 때 죽였는지 확인 (함정 ②)
    worker.kill()
    rc = worker.wait()
    print(f"⑤ 그래프+0.50초에 kill · 살아있었나={alive} · returncode={rc}")

    from langgraph.checkpoint.sqlite import SqliteSaver

    from backend.orchestration.langgraph_engine import LangGraphEngine

    with SqliteSaver.from_conn_string(SQLITE) as saver:
        engine = LangGraphEngine(checkpointer=saver)
        before = engine.get_state(KEY)
        # ⚠️ `.get()` 이다 — mid-superstep 에 죽으면 findings 키가 **아예 없다** (함정 ⑤)
        print(
            f"   재시작 직후: status={before['status']}"
            f" · findings {len(before.get('findings', []))}개"
            f" · 남은 노드 {before['next_nodes']}"
        )
        t0 = time.perf_counter()
        engine.resume(KEY)
        after = engine.get_state(KEY)
        print(
            f"   resume() 후:  status={after['status']}"
            f" · findings {len(after['findings'])}개"
            f" · {time.perf_counter() - t0:.2f}초"
        )

    os.remove(SQLITE)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--child":
        child()
    else:
        main()


# 출력(그대로) — 2026-08-21:
#
#   ① p.kill() → returncode=-9  (-9 이면 SIGKILL)
#   ② 끝난 프로세스에 kill() → 예외 없음 · returncode=0
#   ③ SIGKILL 에 핸들러를 달아보면:
#      child: OSError: [Errno 22] Invalid argument
#   ④ 자식이 READY 까지 0.51초 — 그래프는 아직 0초다
#   ⑤ 그래프+0.50초에 kill · 살아있었나=True · returncode=-9
#      재시작 직후: status=running · findings 2개 · 남은 노드 ['security', 'testing']
#      resume() 후:  status=done · findings 4개 · 0.82초
#
# 📌 M5 완료 판정 ② 통과. quality(0.4s)·docs(0.3s)만 끝나 있었고 resume 이
#    security·testing 둘만 다시 불렀다 — LLM 호출 2회를 아꼈다.
