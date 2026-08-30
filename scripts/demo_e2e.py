#!/usr/bin/env python
"""end-to-end 데모 — 진짜 PR 하나가 웹훅부터 코멘트까지 흐른다.

실행 (사용자가 직접):
    uv run python scripts/demo_e2e.py 2                    # dry-run. 게시 안 함
    uv run python scripts/demo_e2e.py 2 --post             # 진짜로 코멘트를 단다
    uv run python scripts/demo_e2e.py --calibrate          # API 0회. 게이트 재료만 본다

⚠️ **API 호출 4번이 나간다** (관점 넷). 한 판에 ~20초.
⚠️ `--post` 는 **공개 PR 에 진짜 코멘트를 답니다.** 되돌리려면 손으로 지워야 한다.

왜 이 파일이 `demo_m7.py` 가 아닌가
------------------------------------
M7 은 RAG 다. 우리는 그걸 건너뛰고 **M8 의 게이트 일부**를 먼저 붙였다.
마일스톤 번호를 붙이면 "M7 이 끝났다"로 읽히므로 붙이지 않는다 —
`03-build-plan.md` 의 M7 완료 판정은 여전히 하나도 통과 안 했다.

이 데모가 재는 것과 안 재는 것
-------------------------------
    잰다:   **배선이 이어졌나.** ①웹훅 → ②큐 → ③워커 → ④⑤ → ⑥게이트 → GitHub
    안 잰다: **리뷰가 좋은가.** 그건 `scripts/eval_prompt.py` 가 K판으로 답한다

⚠️ 웹훅(①)은 **HTTP 로 안 부른다.** payload 를 직접 만들어 큐에 넣는다.
   진짜 웹훅을 받으려면 공인 URL 이 필요한데(ngrok), 그건 배선이 아니라 네트워크 문제다.
   ①의 서명 검증은 `demo_m1_signature.py` 가 이미 12케이스로 잰다 — 여기서 겹치지 않는다.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.gate.decision import render_comment, summarize  # noqa: E402
from backend.github.client import (  # noqa: E402
    MAX_DIFF_CHARS,
    fetch_pr_meta,
    pick_reviewable_slice,
    split_diff_by_file,
)
from backend.orchestration.langgraph_engine import LangGraphEngine  # noqa: E402
from backend.queue.router import enqueue, queue_depth, reset  # noqa: E402
from backend.worker.runner import run_forever  # noqa: E402

OWNER = os.getenv("DEMO_OWNER", "sml1323")
REPO = os.getenv("DEMO_REPO", "pr_agent")
SQLITE = "demo_e2e_checkpoints.sqlite"


def _saver():
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver.from_conn_string(SQLITE)


def build_payload(number: int) -> dict:
    """진짜 PR 로부터 GitHub 웹훅과 **같은 모양**의 payload 를 만든다.

    ⚠️ 모양이 같아야 하는 이유: 워커의 `extract_coords()` 가 이 모양을 전제한다.
       데모용으로 납작한 dict 를 만들면 **데모만 도는 코드 경로**가 생기고,
       진짜 웹훅이 왔을 때 거기서 터진다.
    """
    meta = fetch_pr_meta(OWNER, REPO, number)
    return {
        "action": "opened",
        "number": number,
        "pull_request": {
            "number": meta["number"],
            "title": meta["title"],
            "head": {"sha": meta["head"]["sha"]},
        },
        "repository": {"owner": {"login": OWNER}, "name": REPO},
    }


def calibrate() -> int:
    """게이트 TODO 의 재료 — 저장된 판에서 confidence 분포를 본다. **API 0회.**

    왜 이게 필요한가: `0.6` 은 영상이 말한 값이지 우리 데이터로 검증한 값이 아니다.
    임계값을 고르기 전에 **그 값이 실제로 무언가를 가르는지** 봐야 한다.
    """
    runs = sorted((Path(__file__).resolve().parent.parent / "evals" / "runs").glob("*.json"))
    confs: list[float] = []
    by_sev: Counter[str] = Counter()
    for p in runs:
        for r in json.loads(p.read_text())["runs"]:
            for f in r.get("findings", []):
                confs.append(f["confidence"])
                by_sev[f["severity"]] += 1

    if not confs:
        print("evals/runs 가 비었다.")
        return 1

    confs.sort()
    n = len(confs)
    print(f"저장된 findings {n}건의 confidence 분포\n")
    for lo, hi in [(0.0, 0.5), (0.5, 0.6), (0.6, 0.8), (0.8, 0.9), (0.9, 0.99), (0.99, 1.01)]:
        c = sum(1 for x in confs if lo <= x < hi)
        bar = "█" * round(c / n * 50)
        print(f"  [{lo:.2f}, {hi:.2f})  {c:3d}건 {c/n*100:5.1f}%  {bar}")

    print(f"\n  최소 {confs[0]:.2f} · 중앙값 {confs[n//2]:.2f} · 최대 {confs[-1]:.2f}")
    print("\nseverity 분포")
    for s, c in by_sev.most_common():
        print(f"  {s:15s} {c:3d}건")

    over = sum(1 for x in confs if x >= 0.6)
    print(f"\n⚠️ `confidence >= 0.6` 을 쓰면 {over}/{n} 건({over/n*100:.0f}%)이 통과한다.")
    print("   이 값이 100% 에 가까우면 그 임계값은 **아무것도 안 거른다** —")
    print("   필드는 있는데 변별력이 없는 상태이고, 그게 M6-0b 가 잰 그것이다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("number", nargs="?", type=int, help="리뷰할 PR 번호")
    ap.add_argument("--post", action="store_true",
                    help="⚠️ 진짜로 코멘트를 단다 (기본은 dry-run)")
    ap.add_argument("--calibrate", action="store_true",
                    help="API 0회. 저장된 판으로 confidence 분포만 본다")
    ap.add_argument("--budget", type=int, default=MAX_DIFF_CHARS)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.calibrate:
        return calibrate()
    if args.number is None:
        ap.error("PR 번호가 필요하다 (또는 --calibrate)")

    print(f"═══ end-to-end · {OWNER}/{REPO}#{args.number} "
          f"{'· 진짜 게시' if args.post else '· dry-run'} ═══\n")

    # ① 웹훅이 받았을 payload 를 만든다
    payload = build_payload(args.number)
    sha = payload["pull_request"]["head"]["sha"]
    print(f"① payload   {payload['pull_request']['title'][:50]}")
    print(f"            head={sha[:8]} action={payload['action']}")

    # diff 가 얼마나 잘리는지 먼저 보여준다 — 안 본 것이 드러나야 한다
    from backend.github.client import fetch_pr_diff

    raw = fetch_pr_diff(OWNER, REPO, args.number)
    kept, skipped = pick_reviewable_slice(raw, budget=args.budget)
    print(f"\n   diff  전체 {len(raw):,}자 · {len(split_diff_by_file(raw))}파일")
    print(f"         리뷰 {len(kept):,}자 · {len(split_diff_by_file(kept))}파일 "
          f"· 안 봄 {len(skipped)}파일")

    # ② 큐
    reset()
    enqueue(payload)
    print(f"\n② 큐        depth={queue_depth()}")

    # ③④⑤⑥ 워커가 나머지 전부
    print("\n③ 워커      돌린다 (API 4회 · ~20초)...")
    with _saver() as saver:
        engine = LangGraphEngine(checkpointer=saver)
        results = run_forever(engine, max_jobs=1, dry_run=not args.post)

    r = results[0]
    print(f"            {r.elapsed:.1f}초 · review_key={r.review_key}")

    if r.error:
        print(f"\n❌ 실패: {r.error}")
        return 1
    if r.skipped:
        print(f"\n⏭  건너뜀: {r.skipped}")
        return 0

    d = r.decision
    if d is None:
        print("\n❌ 게이트가 판정을 안 돌려줬다 — `backend/gate/decision.py` 의 "
              "`decide()` 가 아직 `TODO(human)` 스텁이다.")
        print("   그 함수를 채우면 이 줄 아래가 나온다.")
        return 1

    print(f"\n⑥ 게이트    {summarize(d)}")
    for f in d.auto_post:
        print(f"   📢 {f['severity']:13s} {f['category']:24s} conf={f['confidence']:.2f}")
    for f in d.to_human:
        print(f"   🙋 {f['severity']:13s} {f['category']:24s} conf={f['confidence']:.2f}")
    for f in d.suppressed:
        print(f"   🔇 {f['severity']:13s} {f['category']:24s} conf={f['confidence']:.2f}")
    if d.reasons:
        print("\n   근거:")
        for why in d.reasons:
            print(f"     · {why}")

    body = render_comment(d, head_sha=sha, skipped_files=skipped)
    print("\n─── 게시할 코멘트 ───────────────────────────────")
    print(body)
    print("─────────────────────────────────────────────────")

    if r.comment_url:
        print(f"\n✅ 게시됨: {r.comment_url}")
    else:
        print("\n(dry-run — 게시 안 함. 진짜로 달려면 --post)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
