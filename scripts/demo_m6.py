#!/usr/bin/env python
"""M6 데모 — 진짜 LLM 넷이 돌고, 애그리게이터가 합친다.

실행 (사용자가 직접):
    uv run python scripts/demo_m6.py                    # fixtures/sample.diff
    uv run python scripts/demo_m6.py fixtures/sample_injected.diff

⚠️ **API 호출 4번이 나간다** (관점 넷). 한 판에 ~15초.

이 데모가 재는 것과 안 재는 것 (M6-PLAN §0 이 정한 분업)
--------------------------------------------------------
    잰다:   **배선이 살아있나 · 불변식이 안 깨졌나.**  한 판이면 답이 나온다
    안 잰다: **얼마나 자주 맞나.**  그건 Pass^k 의 질문이고 `scripts/eval_prompt.py` 가 답한다

M6-PLAN §0 이 순서를 바꾼 이유가 이 분업이다 — *"데모를 한 번 돌려 통과하면 그건 Pass@1 이다.
이 프로젝트의 제1원칙(틀린 말을 안 하는 것)은 Pass^k 쪽이다."*
그래서 여기서 **품질을 통과/실패로 판정하지 않는다.** 배선과 불변식만 본다.
📖 책 인쇄 217 — *"중요한 작업에는 '한 번도 실수하지 않는' 안정성에 초점을 맞춰 Pass^k 를 우선합니다."*

원래 완료 판정(`03-build-plan.md` M6)에서 **바뀐 것**
---------------------------------------------------
| | 원래 | 여기 | 왜 |
|---|---|---|---|
| ① | 하나의 통합 리뷰가 나옴 | 그대로 | |
| ② | SQL 인젝션을 **security 가** `critical` 로 | **둘로 갈랐다** — ②a 커버리지(판정) · ②b 등급(경고) | 아래 |
| ③ | 모든 Finding 에 confidence+rationale | **+ 상수가 아닌지** | M6-PLAN §M6-6 |
| ④ | 같은 줄은 하나로 합쳐짐 | **`merged_from ≥ 2` 가 있나** | `line` 이 못 쓰는 축이 됐다(아래) |
| ⑤ | `agent_events` 로 에이전트별 비용 | **M3 로 미룸** | 2026-08-25 결정 |

**②를 왜 가르나** — 실측 (2026-08-28, `sample.diff`, 관점 넷 각 1판):

    security  [high]     sql-injection   ← 자기 전문 영역인데 **혼자 high 다**
    quality   [critical] sql-injection
    testing   [critical] sql-injection
    docs      [critical] sql-injection

원문 그대로("security 가 critical 로")면 **이 판은 실패**다. 그런데 파이프라인은 멀쩡히 돌았고
critical 도 나왔다 — 실패한 건 *배선*이 아니라 *그날의 등급*이다. 한 판으로 등급을 판정하면
Pass@1 을 완료 판정으로 쓰는 것이고, M6-PLAN §0 이 그걸 금지한다.
→ **②a 는 판정**(누가라도 잡았나 = 배선), **②b 는 경고**(critical 인가 = 품질).
  ②b 의 진짜 판정은 `uv run python scripts/eval_prompt.py regrade` 가 K판으로 한다.

**④를 왜 바꾸나** — 원문은 *"같은 **줄**을 지적했으면"* 인데, `line` 이 관점마다 다르다:

    같은 resource-leak 을   quality :15 · testing :12 · docs :18
    같은 sql-injection 을   security :17 · quality :17 · testing :15 · docs :17
    (⚠️ 정답은 각각 :14 와 :16 이다 — @@ 헤더로 계산했다. **넷 다 틀렸다.**)

줄로 판정하면 합쳐질 리가 없다. dedup 키가 `(file, category)` 라서
판정도 **"실제로 합쳐진 항목이 있나"**(`merged_from ≥ 2`)로 묻는다.
근거는 `backend/agents/aggregator.py` 의 TODO ①.

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → ③ 워커 → **④ 스페셜리스트 4** → **⑤ 애그리게이터** → ⑥ 게이트
"""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.aggregator import aggregate  # noqa: E402
from backend.orchestration.langgraph_engine import AGENT_TYPES, LangGraphEngine  # noqa: E402

# 데모 전용 체크포인트. `demo_m5` 와 같은 이유로 파일을 가른다 —
# 워커의 진짜 상태(checkpoints.sqlite)를 건드리면 안 된다.
SQLITE = "demo_m6_checkpoints.sqlite"


def _saver():
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver.from_conn_string(SQLITE)


def _clean_sqlite() -> None:
    """체크포인트 파일을 지운다. **`-wal` 과 `-shm` 도 같이** 지운다.

    ⚠️ sqlite 는 WAL 모드에서 파일을 **셋** 만든다 (`.sqlite` · `-wal` · `-shm`).
       본체만 지우면 나머지 둘이 레포에 남고, `.gitignore` 가 `*.sqlite` 만 적어뒀으면
       `git status` 에 쓰레기가 뜬다. 실제로 그렇게 됐다 (2026-08-28).
    """
    for suffix in ("", "-wal", "-shm"):
        path = SQLITE + suffix
        if os.path.exists(path):
            os.remove(path)


# ─────────────────────────────────────────────────────────────
# 판정 ⓪ — 애그리게이터 결정성 (API 0회)
#
# 왜 이게 맨 앞인가: **프록시가 죽어도 이 판정은 돈다.** 병합 로직은 순수 함수라
# 네트워크와 무관하고, M6-5 의 회귀는 대부분 여기서 잡힌다.
# 그리고 아래 ①~④ 가 전부 API 에 의존하므로, 그게 실패했을 때
# "병합이 깨진 건가 프록시가 죽은 건가"를 가르는 기준선이 필요하다.
#
# 입력은 **2026-08-28 실측 그대로**다. 지어낸 값이 아니라서, 이 판정이 깨지면
# "그때 실제로 일어난 일을 지금 코드가 다르게 처리한다"는 뜻이 된다.
# ─────────────────────────────────────────────────────────────
_MEASURED = [
    {"agent_type": "security", "severity": "high", "category": "sql-injection",
     "file": "api/users.py", "line": 17, "confidence": 1.00, "rationale": "실측 2026-08-28"},
    {"agent_type": "quality", "severity": "critical", "category": "sql-injection",
     "file": "api/users.py", "line": 17, "confidence": 0.99, "rationale": "실측 2026-08-28"},
    {"agent_type": "quality", "severity": "medium", "category": "resource-leak",
     "file": "api/users.py", "line": 15, "confidence": 0.97, "rationale": "실측 2026-08-28"},
    {"agent_type": "testing", "severity": "critical", "category": "sql-injection",
     "file": "api/users.py", "line": 15, "confidence": 1.00, "rationale": "실측 2026-08-28"},
    {"agent_type": "testing", "severity": "medium", "category": "resource-leak",
     "file": "api/users.py", "line": 12, "confidence": 0.95, "rationale": "실측 2026-08-28"},
    {"agent_type": "testing", "severity": "low", "category": "missing-test-coverage",
     "file": "api/users.py", "line": 16, "confidence": 0.98, "rationale": "실측 2026-08-28"},
    {"agent_type": "docs", "severity": "critical", "category": "sql-injection",
     "file": "api/users.py", "line": 17, "confidence": 1.00, "rationale": "실측 2026-08-28"},
    {"agent_type": "docs", "severity": "medium", "category": "resource-leak",
     "file": "api/users.py", "line": 18, "confidence": 0.98, "rationale": "실측 2026-08-28"},
]


def f_(rationale: str, line: int) -> dict[str, object]:
    """과합병 관측용 합성 finding. 같은 `(file, category)` 인데 **다른 결함**이다."""
    return {"agent_type": "security", "severity": "high", "category": "sql-injection",
            "file": "api/users.py", "line": line, "confidence": 0.9, "rationale": rationale}


def scenario_determinism() -> bool:
    """같은 입력 → 같은 출력. 순서를 섞어도."""
    import random

    base = aggregate(_MEASURED, order=AGENT_TYPES)
    shuffles_ok = True
    for seed in (1, 2, 3, 4, 5):
        shuffled = _MEASURED[:]
        random.Random(seed).shuffle(shuffled)
        if aggregate(shuffled, order=AGENT_TYPES) != base:
            shuffles_ok = False

    print(f"⓪  8개 → {len(base)}개 · 입력 순서 5회 셔플에 불변={shuffles_ok}")
    for m in base:
        print(f"    [{m['severity']:<9}] {m['category']:<22} conf={m['confidence']:.2f} "
              f"← {','.join(m['sources'])} ({m['merged_from']}개 합침)")

    # ⚠️ **셔플만으로는 부족하다** (2026-08-28 에 실제로 뚫렸다).
    #    측정 데이터에 **완전 동률**(같은 severity + 같은 confidence + 같은 관점)이 없어서
    #    셔플 검사가 통과했는데, 동률을 만들어 넣으면 입력 순서가 결과를 바꿨다.
    #    그런 입력은 상상이 아니다 — M0 에서 **한 관점이 같은 결함을 두 번 뱉었다**
    #    (`PLAN.md` G-M0-3). 그리고 리듀서가 쌓는 순서는 노드 완료 순서라 **비결정적**이다.
    #    → **판정이 통과한 범위가 판정문의 주장보다 좁았다.** 그래서 동률 케이스를 따로 넣는다.
    tie = [
        {"agent_type": "security", "severity": "high", "category": "sql-injection",
         "file": "a.py", "line": 10, "confidence": 0.9, "rationale": "A 쪽 설명"},
        {"agent_type": "security", "severity": "high", "category": "sql-injection",
         "file": "a.py", "line": 20, "confidence": 0.9, "rationale": "B 쪽 설명"},
    ]
    tie_ok = aggregate(tie, order=AGENT_TYPES) == aggregate(tie[::-1], order=AGENT_TYPES)
    print(f"    완전 동률(같은 관점·severity·confidence)에서도 불변={tie_ok}")

    # ── **과합병** — ④가 안 재는 반대 방향 (2026-08-28 지적) ──────
    #    ④는 *"합쳐졌나"* 만 묻는다. 그런데 **더 비싼 실수는 반대쪽**이다:
    #    `(file, category)` 가 같은 **진짜 다른 결함 둘**이 하나로 뭉개지고
    #    하나가 **아무 데도 안 남는다.** `aggregator.py` TODO ① 이 그걸
    #    *"잃는 것"* 으로 적어뒀는데, **재는 자리가 없었다.**
    #    ⚠️ 이건 **판정이 아니라 관측**이다 — 지금 dedup 키에서는 **일부러 그러는 것**이고,
    #       ❌ 로 찍으면 잠정값을 뒤집으라는 압박이 된다. TODO ① 을 뒤집으면 이 줄이 답이 바뀐다.
    over = aggregate(
        [
            f_(":17 쪽 진짜 결함", 17),
            f_(":42 쪽 **다른** 진짜 결함", 42),
        ],
        order=AGENT_TYPES,
    )
    lost = 2 - over[0]["merged_from"] if len(over) == 1 else 0
    print(f"    과합병 (관측): 다른 결함 2개 → {len(over)}개"
          f"{'  ⚠️ 하나가 사라졌다 (dedup 키 (file, category) 의 대가)' if len(over) == 1 else ''}"
          f"{f' · lost={lost}' if lost else ''}")

    # 합쳐진 게 하나도 없으면 이 판정은 아무것도 증명하지 않는다 —
    # 셔플에 불변인 건 "아무것도 안 하는 함수"도 마찬가지다.
    merged_any = any(m["merged_from"] >= 2 for m in base)
    return shuffles_ok and tie_ok and merged_any and len(base) < len(_MEASURED)


def scenario_live(diff_path: Path) -> bool:
    """판정 ①②③④⑤ — 진짜 호출 넷을 그래프로 돌린다. **API 4회.**"""
    _clean_sqlite()

    diff = diff_path.read_text(encoding="utf-8")
    # review_key 는 호출자가 계산한다 (engine.py 결정 1). 데모엔 진짜 PR 이 없으므로
    # 재료를 파일 이름으로 채운다 — 모양만 계약과 맞춘다.
    key = f"demo/m6@{diff_path.stem}"

    with _saver() as saver:
        engine = LangGraphEngine(checkpointer=saver)

        # ⚠️ **호출 0회로 ✅ 가 뜨는 경로를 막는다** (2026-08-28 지적).
        #    `run()` 의 G11 가드는 이미 끝난 리뷰에 **조용히 return** 한다(경고 한 줄뿐).
        #    체크포인트가 남아 있으면 `get_state()` 가 **지난 실행의 결과**를 주고
        #    ①~⑥ 이 전부 초록이 된다 — **API 를 한 번도 안 부르고.**
        #    `_clean_sqlite()` 가 지우긴 하지만 그건 *"지웠을 것이다"* 라는 가정이고,
        #    판정은 가정이 아니라 **관측** 위에 서야 한다.
        #    (`demo_m5` 독립 검증의 교훈: *"판정식은 성공 상태가 아니라 그 성공에
        #     이르는 경로를 검사해야 한다"* — 여기선 **출발점**이 그 경로다.)
        before = engine.get_state(key)["status"]
        if before != "not_started":
            print(f"⛔ 출발점이 '{before}' 다 — 백지에서 시작하지 않았다.", file=sys.stderr)
            print(f"   {SQLITE} 를 지우고 다시 돌릴 것. 이 판정은 무효다.", file=sys.stderr)
            return False

        t0 = time.perf_counter()
        engine.run(key, diff)
        elapsed = time.perf_counter() - t0
        s = engine.get_state(key)

    raw, merged, failed = s["findings"], s["merged"], s["failed_agents"]

    print(f"\n{elapsed:.1f}초 · status={s['status']} · 원본 {len(raw)}개 → merged {len(merged)}개"
          f" · failed={failed or '[]'}")

    # ── 관점별로 무엇이 나왔나 — G2(커버리지)의 재료 ─────────────
    # "0개"와 "죽었다"를 눈으로 갈라야 한다. 이게 이 프로젝트 최악의 시나리오다.
    print("\n  관점별:")
    for at in AGENT_TYPES:
        mine = [f for f in raw if f.get("agent_type") == at]
        if at in failed:
            note = "💀 죽었다 (확인 안 됨)"
        elif not mine:
            note = "○ 0개 (봤는데 없다)"
        else:
            note = " · ".join(f"[{f['severity']}] {f['category']}" for f in mine)
        print(f"    {at:<9} {note}")

    print("\n  통합 리뷰 (⑥ 게이트가 받을 것):")
    for m in merged:
        print(f"    [{m['severity']:<9}] {m['category']:<22} {m['file']}:{m['line']} "
              f"conf={m['confidence']:.2f}  ← {','.join(m['sources'])}")
        print(f"        {m['rationale'][:90]}")

    print("\n" + "─" * 62)

    # ── ① 통합 리뷰 하나 ────────────────────────────────────────
    # "하나"의 뜻: 관점별 목록 넷이 아니라 **합쳐진 목록 하나**가 나온다.
    ok1 = bool(merged) and len(merged) <= len(raw)
    print(f"① 통합 리뷰      : {'PASS' if ok1 else 'FAIL'}  "
          f"({len(raw)}개 → {len(merged)}개)")

    # ── ②a 커버리지 (판정) / ②b 등급 (경고) ────────────────────
    sqli = [m for m in merged if m["category"] == "sql-injection"]
    ok2a = bool(sqli)
    print(f"②a sql-injection : {'PASS' if ok2a else 'FAIL — 심어둔 결함을 아무도 못 찾았다'}")
    if sqli:
        top = sqli[0]
        grade = "critical ✅" if top["severity"] == "critical" else f"{top['severity']} ⚠️"
        seen_by_security = "예" if "security" in top["sources"] else "아니오 ⚠️"
        print(f"②b 등급          : {grade} (한 판이라 **판정이 아니라 관측**이다)"
              f"  · security 가 봤나={seen_by_security}")
        print("   → 등급의 진짜 판정은 K판이 한다: uv run python scripts/eval_prompt.py regrade")

    # ── ③ INV-3 ─────────────────────────────────────────────────
    # 두 가지를 본다: 필드가 있나 · **값이 흔들리나.**
    # 후자가 없으면 필드는 있어도 불변식은 깨진 것이다 (invariants.md INV-3).
    # ⚠️ **`merged` 만 보면 안 된다** (2026-08-28, 적대적 검증). dedup 에 밀려 사라진
    #    finding 의 빈 rationale 은 merged 에 안 남는다 — INV-3 은 **모든 finding** 에
    #    걸린 불변식이지 "살아남은 것"에만 걸린 게 아니다.
    #    `invariants.md` 가 *"스키마가 거부하게 만드는 게 목표"* 라고 적었는데
    #    지금 `rationale` 에 `min_length` 가 없어서 **스키마도 안 거부한다** —
    #    두 겹이 다 비면 회귀가 조용히 지나간다.
    #    ⏭ 진짜 답은 `Finding.rationale` 에 `min_length=1` 을 다는 것이다.
    #       그건 스키마(= 프롬프트)를 바꾸는 일이라 베이스라인이 리셋된다 → M6-3b 와 같이.
    empty = [f["category"] for f in raw + merged
             if not str(f.get("rationale", "")).strip() or f.get("confidence") is None]
    confs = sorted({m["confidence"] for m in merged})
    # ⚠️ 표본이 1개면 "상수"인지 알 수 없다. 없는 판정을 PASS 로 찍지 않는다.
    if len(merged) < 2:
        conf_note = f"판정 불가 (merged {len(merged)}개)"
        ok3 = not empty
    else:
        ok3 = not empty and len(confs) > 1
        conf_note = "PASS" if len(confs) > 1 else "FAIL — 전부 같은 값"
    print(f"③ INV-3          : 빈 필드={'없음' if not empty else empty} · "
          f"confidence 분포={conf_note} {confs}")

    # ── ④ 합쳐졌나 ──────────────────────────────────────────────
    # ⚠️ `line` 이 아니라 `merged_from` 으로 묻는다. 이유는 이 파일 맨 위 표.
    dupes = [m for m in merged if m["merged_from"] >= 2]
    ok4 = bool(dupes)
    if dupes:
        detail = " · ".join(f"{m['category']}({m['merged_from']}개)" for m in dupes)
    else:
        detail = "합쳐진 항목이 없다 — 관점이 안 겹쳤거나 dedup 키가 안 맞는다"
    print(f"④ 중복 병합      : {'PASS' if ok4 else 'FAIL'}  {detail}")

    # ── ⑤ 커버리지 (신설 2026-08-28, 적대적 검증에서 구멍이 드러났다) ──
    #
    # 🔴 **①~④ 어디에도 `failed_agents` 를 보는 곳이 없었다.**
    #    관점 둘이 죽고 둘만 살아남아도 그 둘이 같은 결함을 잡으면
    #    ①(merged 있음) ②a(sql-injection 있음) ③(confidence 흔들림) ④(merged_from≥2)
    #    가 **전부 PASS** 다. 데모가 ✅ 를 찍는다.
    #
    #    그런데 이건 **이 프로젝트가 최악이라고 적어둔 시나리오(G2)** 그 자체다 —
    #    `CURRENT.md` 「알려진 리스크」: *"스페셜리스트 노드가 죽었을 때 'critical 없음'과
    #    '확인 안 됨'을 게이트가 구분 못 함. 이 프로젝트 최악의 시나리오인데 고치는 건 if문 몇 줄."*
    #    **데모가 그걸 안 재고 있었다.**
    #
    # ⚠️ "넷 다 findings 를 냈나"로 묻지 **않는다** — 0개는 정상일 수 있다
    #    (그 관점에서 찾을 게 없으면). 물어야 하는 건 **"넷 다 살아서 봤나"** 다.
    #    이 둘을 가르는 게 G2 의 전부다.
    ok5 = not failed
    print(f"⑤ 커버리지       : {'PASS' if ok5 else f'FAIL — {failed} 가 확인 안 됨 (G2)'}"
          f"  · 넷 다 살아서 봤나")

    # ── ⑥ 오탐 (관측 · 게이트 아님) ────────────────────────────────
    #
    # 🔴 **①~⑤ 어디에도 「틀린 말을 했나」를 보는 곳이 없었다** (2026-08-28 지적).
    #    이 프로젝트의 **제1원칙이 선별**인데 판정 세트에 한 번도 안 들어가 있었다.
    #    ①~⑤ 는 전부 *"찾았나 · 합쳤나 · 살아있나"* 이고, 전부 **놓침** 방향이다.
    #
    # ⚠️ **게이트로 안 두는 이유**: 오탐률은 한 판으로 판정할 수 없다.
    #    실측 `review-evasion-attempt` 오탐이 `sample` 에서 2/9 였다 —
    #    ✅/❌ 로 찍으면 **같은 코드가 날마다 다른 답을 준다.**
    #    그건 데모를 회귀 감지기가 아니라 동전던지기로 만든다.
    #    → **찍되 판정에는 안 넣는다.** 진짜 판정은 `eval_prompt.py regrade` 가 K판으로.
    #    (②b 등급을 「관측」으로 내린 것과 같은 규칙 — 이 파일 맨 위 표)
    try:
        from evals.grader import grade_run

        g = grade_run(diff_path.stem, merged)  # agent=None → merged 는 관점을 안 가린다
        bad = [v["category"] for v in g.violations]
        note = f"⚠️ {bad}" if bad else "없음"
        print(f"⑥ 오탐 (관측)    : {note}  · caught {sum(g.caught)}/{len(g.caught)}")
        if bad:
            print("   → 판정이 아니다. 한 판으로는 오탐률을 못 잰다 "
                  "(실측 2/9). K판은 eval_prompt.py 가 잰다")
    except KeyError:
        # 정답지에 없는 픽스처로 데모를 돌릴 수 있다 — 그건 오류가 아니다.
        print(f"⑥ 오탐 (관측)    : 판정 불가 — `expected.yaml` 에 '{diff_path.stem}' 이 없다")

    return ok1 and ok2a and ok3 and ok4 and ok5


def main() -> int:
    # ⚠️ WARNING 이 보여야 한다 — 더미로 새면 그 줄이 뜬다. 그게 이 데모의 전제 검사다.
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    diff_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("fixtures/sample.diff")
    if not diff_path.is_file():
        print(f"파일이 없다: {diff_path}", file=sys.stderr)
        return 2

    # ⚠️ 더미로 새고 있으면 이 데모는 아무것도 증명하지 않는다. 먼저 막는다.
    #    (`demo_m5.py` 가 같은 셸에서 `M5_DUMMY_AGENTS` 를 남겼을 수 있다)
    leaked = [v for v in ("M5_DUMMY_AGENTS", "M5_FAIL_AGENTS", "M5_HANG_AGENTS") if os.getenv(v)]
    if leaked:
        print(f"⛔ {', '.join(leaked)} 가 세워져 있다 — 진짜 호출이 아니라 더미가 돈다.",
              file=sys.stderr)
        print("   이 데모는 진짜 LLM 을 재는 물건이다. 변수를 지우고 다시 돌릴 것.",
              file=sys.stderr)
        return 2

    print(f"M6 데모 — {diff_path}   (API 호출 4회, ~15초)\n")
    results = {"⓪ 애그리게이터 결정성 (API 0회)": scenario_determinism()}
    results[f"①②③④⑤ 실호출 ({diff_path.name})"] = scenario_live(diff_path)

    print("─" * 62)
    for name, ok in results.items():
        print(f"{'✅' if ok else '❌'}  {name}")

    _clean_sqlite()
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
