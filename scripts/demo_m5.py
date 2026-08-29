"""M5 데모 — 완료 판정 셋을 명령 하나로 찍는다.

실행 (사용자가 직접):
    uv run python scripts/demo_m5.py

판정 (`03-build-plan.md` M5):
    ① 병렬     — 4개 노드가 직렬이 아니라 병렬로 돈다
    ② 재개     — 실행 중 워커를 kill -9 하고 재시작하면 처음부터가 아니라 이어서
    ③ 데드락 없음 — 한 노드가 무한 대기해도 타임아웃 후 나머지로 진행

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → ③ 워커 → **④ 여기** → ⑤ 애그리게이터 → ⑥ 게이트

새 기능이 없다 — M5-1~6 에서 만든 것을 조립해서 **증거를 남기는 스크립트**다.
scratch/recon_kill9_resume.py 가 일회성으로 증명한 것을 재현 가능하게 만든다.

⚠️ 함정 다섯 (learning/reference/kill9-and-resume.html 에서 실측·검증됨):
    ② 이미 끝난 프로세스에 kill() → 조용히 아무 일도 없음 → poll() 로 살아있음을 먼저 찍는다
    ④ 자식 시작에 ~0.5초 (langgraph import) → 자식이 READY 를 찍은 뒤에 시계를 잰다
    ⑤ mid-superstep 에 죽으면 get_state() 가 키를 안 준다 → TODO(human) ②
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())

# 데모 전용 체크포인트 파일. `checkpointer.py` 의 `build_checkpointer()` 를 안 쓰는 이유:
# 저건 워커의 실제 파일(checkpoints.sqlite)에 프로세스 수명으로 붙는 물건이고,
# 데모는 매 시나리오마다 파일을 지웠다 새로 만들어야 한다 — 워커의 진짜 상태를
# 건드리면 안 되므로 파일을 가른다. (*.sqlite 는 .gitignore 에 있다)
SQLITE = "demo_m5_checkpoints.sqlite"

# review_key 는 호출자가 repo·pr_number·head_sha 로 계산한다 (engine.py 결정 1).
# 데모에는 진짜 PR 이 없으므로 재료를 가짜로 채운다 — 모양만 계약과 맞춘다.
KEY_PARALLEL = "demo/pr-1@sha-parallel"
KEY_KILL9 = "demo/pr-2@sha-kill9"
KEY_HANG = "demo/pr-3@sha-hang"


# ⚠️ **이 데모는 넷을 전부 더미로 돌린다** (2026-08-28, M6-4 배선 후 추가).
#
# M6-4 에서 `_call_agent` 가 진짜 LLM 호출이 됐다. 그대로 두면 이 데모의 판정 셋이
# 통째로 성립을 안 한다:
#   ① 병렬 — 0.8초를 기대하는 판정식이 **15초**를 본다 (실측 지연 median 16.84)
#   ② kill -9 — 판마다 API 4번. 한도를 태우고, 재개 시간이 노드 지연에 묻힌다
#   ③ hang — 진짜 API 는 우리가 원할 때 멈춰주지 않는다
#
# **이 데모가 재는 건 오케스트레이션이지 LLM 이 아니다.** 배리어·재개·타임아웃은
# 노드 안에서 무슨 일이 일어나든 같아야 하고, 그게 이 층이 존재하는 이유다.
# 그래서 노드 내용을 상수로 고정한다 — 재는 것만 남기고 나머지를 없앤다.
#
# ⚠️ 진짜 호출까지 포함한 판정은 `demo_m6.py` 가 한다. 두 데모가 다른 층을 잰다.
os.environ.setdefault("M5_DUMMY_AGENTS", "all")


def _reset_db() -> None:
    """시나리오마다 백지에서 시작한다 — 이전 실행의 체크포인트가 남아 있으면
    run() 이 새 리뷰가 아니라 끝난 리뷰 위에 이어 붙는다.

    ⚠️ `-wal` 과 `-shm` 도 같이 지운다 (2026-08-28). sqlite 는 WAL 모드에서 파일을
       **셋** 만드는데 `.gitignore` 는 `*.sqlite` 만 적어뒀다 — 본체만 지우면
       나머지 둘이 레포에 남는다. 그리고 남은 `-wal` 에는 **아직 본체에 안 옮겨진
       체크포인트가 들어 있을 수 있다** — 그러면 "백지에서 시작한다"가 거짓말이 된다.
    """
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(SQLITE + suffix):
            os.remove(SQLITE + suffix)


def _diff() -> str:
    return Path("fixtures/sample.diff").read_text()


def _saver():
    """⚠️ `from_conn_string` 은 @contextmanager 다 (checkpointer.py 함정 ①).
    데모는 시나리오 단위로 열고 닫으면 되므로 `with` 로 쓴다."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver.from_conn_string(SQLITE)


def _engine(saver):
    from backend.orchestration.langgraph_engine import LangGraphEngine

    return LangGraphEngine(checkpointer=saver)


# ─────────────────────────────────────────────────────────────
# 판정 ① — 병렬
# ─────────────────────────────────────────────────────────────
def scenario_parallel() -> bool:
    _reset_db()
    with _saver() as saver:
        engine = _engine(saver)
        t0 = time.perf_counter()
        engine.run(KEY_PARALLEL, _diff())
        elapsed = time.perf_counter() - t0
        s = engine.get_state(KEY_PARALLEL)

    from backend.orchestration.langgraph_engine import _DELAYS

    serial_total = sum(_DELAYS.values())  # 직렬이면 이만큼 걸린다 (2.1초)
    slowest = max(_DELAYS.values())  # 완전 병렬이면 이 근처다 (0.8초)
    print(f"①  {elapsed:.2f}초 · findings {len(s['findings'])}개"
          f" · failed {s['failed_agents']} · {s['status']}")
    print(f"    (직렬 합 {serial_total:.1f}초 · 가장 느린 노드 {slowest:.1f}초)")

    # ─────────────────────────────────────────────────────────
    # TODO(human) ① — "병렬이다"를 무엇으로 판정하나
    #
    # ── 왜 이게 판단인가 ─────────────────────────────────────
    # 이 데모는 앞으로 M6·M8 에서 배선을 고칠 때마다 회귀 감지기로 돈다.
    # 판정이 느슨하면 **직렬로 퇴화해도 ✅가 나온다** — 그러면 데모가 아니라 장식이다.
    # 반대로 너무 빡빡하면 머신이 느린 날 거짓 ❌가 나서 아무도 안 믿게 된다.
    #
    # ── 후보 ────────────────────────────────────────────────
    #   (A) elapsed < serial_total          — "직렬보다 빠르다". 넷 중 둘만 겹쳐도 통과
    #   (B) elapsed < slowest + 여유        — "가장 느린 노드가 층의 시간을 정했다"
    #                                         (Lesson 08 의 배리어 그 자체를 판정식으로)
    #   (C) 노드별 시작 시각을 로그로 찍어 비교 — build-plan 원문("시작 시각이 거의 동시").
    #       ⚠️ 지금 노드는 시작 시각을 안 찍는다 — langgraph_engine.py 수정이 필요하다
    #       📌 recon 실측(2026-08-21, langgraph 1.2.11): 스냅샷에서도 못 얻는다 —
    #          PregelTask 필드도 CheckpointMetadata 도 시간 정보가 없다 (찾아봤는데 없다).
    #          (C)를 고르면 계측은 온전히 우리 몫이다 (scratch/recon_get_state_after_kill.py ③)
    #
    # ── 기준 ────────────────────────────────────────────────
    # 이 판정이 잡아야 하는 사고는 뭔가 — "조금 덜 병렬"인가, "직렬로 퇴화"인가.
    # (B)를 고르면 여유를 몇 초로 두는지도 판단이다: 타이트하면 거짓 ❌,
    # 넉넉하면 (A)와 구분이 없어진다. 숫자의 근거를 주석으로 남길 것.
    #
    # 틀리면 뭐가 깨지나: 지금은 안 깨진다. M6 에서 배선을 만질 때
    # 직렬 회귀가 조용히 통과하는 것으로 나중에 깨진다.
    # ─────────────────────────────────────────────────────────
    # 결정 (2026-08-21): (B) — elapsed < 가장 느린 노드 + 0.3초.
    #   Lesson 08 의 배리어 성질("가장 느린 노드가 층의 시간을 정한다")을 그대로 판정식으로.
    #   여유 0.3초의 근거: 실측 오버헤드는 0.01초 수준(0.81 vs 0.8)이라 느린 머신을
    #   감안해도 0.3 이면 넉넉하고, 가장 값싼 2층 퇴화(0.4+0.8=1.2초)는 여전히 잡힌다.
    # ⚠️ 정직한 한계: 빠른 노드가 낀 부분 퇴화(예: docs 0.3 이 quality 0.4 뒤로 가면
    #   0.7초)는 배리어(0.8초) 아래 숨어서 **시간으로는 원리적으로 못 잡는다.**
    #   전부 잡으려면 후보 (C)(노드별 계측)가 필요한데, 스냅샷에 시각이 없어(위 recon)
    #   계측 코드가 통째로 우리 몫이다 — 더미가 사라지는 M6 전에는 값어치가 없다고 판단.
    parallel_ok = elapsed < slowest + 0.3

    return parallel_ok and s["status"] == "done" and len(s["findings"]) == 4


# ─────────────────────────────────────────────────────────────
# 판정 ② — kill -9 재개
# ─────────────────────────────────────────────────────────────
def scenario_kill9() -> bool:
    _reset_db()

    # 자식 = 진짜 워커 흉내. 이 파일을 --child 로 다시 실행한다.
    worker = subprocess.Popen(
        [sys.executable, __file__, "--child", KEY_KILL9],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert worker.stdout is not None
    worker.stdout.readline()  # "READY" — 이걸 읽은 뒤부터가 그래프 시간이다 (함정 ④)

    time.sleep(0.5)  # 그래프 0.5초 지점: quality(0.4)·docs(0.3)는 끝났고 둘은 도는 중
    alive = worker.poll() is None  # 정말 살아 있을 때 죽이는지 — 근거 없는 kill 은 거짓말 (함정 ②)
    worker.kill()
    rc = worker.wait()
    print(f"②  그래프+0.50초에 kill · 살아있었나={alive} · returncode={rc}"
          f" (-{int(signal.SIGKILL)} 이면 SIGKILL)")

    with _saver() as saver:
        engine = _engine(saver)
        before = engine.get_state(KEY_KILL9)

        # ─────────────────────────────────────────────────────
        # TODO(human) ② — get_state() 의 반환 계약, 여기서 정한다
        #
        # ── 왜 이게 판단인가 (CURRENT.md 의 "열린 결정") ─────
        # M5-3 에서 get_state() 가 "키 6개를 돌려준다"고 약속했다:
        #   review_key · diff · findings · failed_agents · next_nodes · status
        # 그런데 아주 이른 시점에 죽으면 snapshot.values 가 비어서
        # `before["findings"]` 가 **KeyError** 다 — 계약이 안 지켜진다.
        # 이 데모가 그 자리를 정면으로 만나는 첫 호출부다. 다음 호출부는
        # 워커 복구(③)와 M9 대시보드다.
        #
        # ── 후보 ────────────────────────────────────────────
        #   (A) 계약을 지키게 고친다 — langgraph_engine.py 의 get_state() 가
        #       빈 값일 때도 6개 키를 채워서 돌려준다 (findings=[] 등).
        #       ⚠️ 그러면 "빈 리스트"가 두 뜻이 된다 — "지적 없음"과
        #          "스냅샷이 아직 없음". status 가 그 둘을 갈라주는지 확인할 것
        #          (Lesson 06 — 빈 것의 뜻이 여럿이다).
        #   (B) 호출부가 방어한다 — 여기서 .get("findings", []) 로 읽고,
        #       계약 문서(M5-3 주석)를 "빠질 수 있다"로 고친다.
        #       ⚠️ 호출부가 늘 때마다 방어도 는다. M9 대시보드가 .get 을
        #          빼먹으면 거기서 다시 터진다.
        #
        # ── 기준 ────────────────────────────────────────────
        # 같은 방어를 **한 곳(구현)에서 하나, 모든 호출부에서 하나.**
        # 어느 쪽이든 아래 출력은 세 가지를 보여줘야 한다:
        #   status(running 인가) · 살아남은 findings 개수 · 남은 노드 목록
        # (A)를 고르면 langgraph_engine.py 도 같이 고치고, 왜인지 주석을 남길 것.
        #
        # ── recon 실측 (2026-08-21 · langgraph 1.2.11 · scratch/recon_get_state_after_kill.py) ──
        # 키가 빠지는 regime 은 **딱 하나** — 체크포인트가 0개일 때뿐이다:
        #   체크포인트 0개        → values={} · created_at=None → 키 2개 · not_started
        #   mid-superstep kill   → 채널 4개 다 있음 (pending_writes 적용) → 키 6개 · running
        # "반만 찬 dict"는 없다 (pregel/main.py `_prepare_state_snapshot` 의 `if not saved:`).
        # ⚠️ 그래서 이 데모의 0.5초 kill 은 사실 키 6개가 다 온다 — KeyError 가 나는 건
        #    invoke 직후 첫 put 전에 죽는 창뿐이고, 그 경우는 관측상 "시작 안 함"과 구분 불가.
        # → 판단이 이렇게 좁혀진다: "not_started 가 두 뜻(정말 시작 전 / 첫 저장 전에 죽음)인
        #    것을 (A)계약 보강으로 흡수하나, (B)호출부 방어 + 문서 정정으로 남기나."
        # ─────────────────────────────────────────────────────
        # 결정 (2026-08-21): (A) — 계약을 구현에서 지킨다. langgraph_engine.py 의
        #   get_state() 가 기본값을 깔아 항상 6개 키를 돌려준다 (근거는 그쪽 주석).
        #   그래서 이 출력은 .get 없이 6개 키를 믿고 읽는다 — 이 줄이 계약의 첫 소비자다.
        print(f"    재시작 직후: status={before['status']}"
              f" · findings {len(before['findings'])}개"
              f" · 남은 노드 {before['next_nodes']}")

        t0 = time.perf_counter()
        engine.resume(KEY_KILL9)
        resumed = time.perf_counter() - t0
        after = engine.get_state(KEY_KILL9)

    print(f"    resume() 후:  status={after['status']}"
          f" · findings {len(after['findings'])}개 · {resumed:.2f}초")

    # 재개가 "이어서"였다는 증거: 전체(0.8초+)가 아니라 남은 노드만큼만 걸렸다.
    # 이미 끝난 노드를 다시 안 불렀다 = INV-2 가 오케스트레이션 층에서 지켜졌다.
    #
    # `before["status"] == "running"` 항은 독립 검증(2026-08-25)이 뚫은 구멍을 막는다:
    # 판정이 도착점(done·4개)만 보면 **출발점이 이미 도착점이었던 경우**를 못 가른다 —
    # 자식이 다 끝난 뒤에 kill 이 떨어지면 resume 이 0.00초에 아무것도 안 하고도 ✅ 였다
    # (부모의 sleep(0.5) 는 바쁜 머신에서 길어질 수만 있어서 정확히 이 방향으로 흔들린다).
    # 판정식은 성공 "상태"가 아니라 그 성공에 이르는 **경로**를 검사해야 한다.
    return alive and rc == -int(signal.SIGKILL) \
        and before["status"] == "running" \
        and after["status"] == "done" and len(after["findings"]) == 4


# ─────────────────────────────────────────────────────────────
# 판정 ③ — 무한 대기 → 타임아웃 → 나머지로 진행
# ─────────────────────────────────────────────────────────────
def scenario_hang() -> bool:
    _reset_db()
    os.environ["M5_HANG_AGENTS"] = "security"
    try:
        with _saver() as saver:
            engine = _engine(saver)
            t0 = time.perf_counter()
            engine.run(KEY_HANG, _diff())  # security 는 영영 안 돌아온다 — 타임아웃이 끊는다
            elapsed = time.perf_counter() - t0
            s = engine.get_state(KEY_HANG)
    finally:
        os.environ.pop("M5_HANG_AGENTS", None)  # 다음 시나리오·다음 실행에 새면 안 된다

    print(f"③  {elapsed:.2f}초 · findings {len(s['findings'])}개"
          f" · failed {s['failed_agents']} · {s['status']}")
    # 위에 WARNING 한 줄(log.warning)이 떠야 정상이다 — 스택트레이스(log.exception)가
    # 떴다면 타임아웃이 "우리 버그" 경로로 샌 것이다 (Lesson 09).

    return s["status"] == "done" and s["failed_agents"] == ["security"] \
        and len(s["findings"]) == 3


# ─────────────────────────────────────────────────────────────
def child(review_key: str) -> None:
    """kill -9 당할 워커. READY 를 찍은 뒤 그래프를 돈다 (함정 ④)."""
    logging.disable(logging.WARNING)
    with _saver() as saver:
        engine = _engine(saver)
        print("READY", flush=True)  # import·조립 끝 — 부모는 이걸 보고 시계를 잰다
        engine.run(review_key, _diff())
        print("DONE", flush=True)  # kill 이 성공했다면 이 줄은 안 나온다


def main() -> None:
    # 판정 ③의 타임아웃 WARNING 이 눈에 보여야 한다 — 그게 증거의 일부다.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    results = {
        "① 병렬": scenario_parallel(),
        "② kill -9 재개": scenario_kill9(),
        "③ hang → 타임아웃 → 진행": scenario_hang(),
    }

    print("─" * 50)
    for name, ok in results.items():
        print(f"{'✅' if ok else '❌'}  {name}")

    _reset_db()
    sys.exit(0 if all(results.values()) else 1)


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--child":
        child(sys.argv[2])
    else:
        main()
