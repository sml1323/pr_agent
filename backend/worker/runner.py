"""워커(③) — 큐에서 잡을 꺼내 리뷰 한 판을 끝까지 돌린다.

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → **③ 여기** → ④ 스페셜리스트 4 → ⑤ 애그리게이터 → ⑥ 게이트 → GitHub

**이 파일이 그동안 비어 있던 자리다.** ①②는 M1 에 만들었고 ④⑤는 M6 에 만들었는데,
그 사이를 잇는 코드가 없었다 — `queue/router.py` 가 스스로 적어둔 한계 그대로다:
*"워커가 없다. 넣기만 하고 아무도 꺼내지 않는다."*

왜 웹훅이 이걸 직접 못 하나
---------------------------
GitHub 은 ack 를 ~10초 안에 기대하는데 리뷰 한 판이 20~90초다.
그리고 **실패한 배달을 자동 재시도하지 않는다** (2026-07-29 1차 출처 확인) —
늦으면 이벤트가 **영구 유실**된다. 그래서 큐가 있고, 그래서 이 파일이 따로 있다.

이 파일이 하는 일 다섯
----------------------
    1. payload 에서 PR 좌표를 뽑는다        (owner · repo · number · head_sha)
    2. GitHub 에서 diff 를 가져온다          — 웹훅 payload 에는 diff 가 없다
    3. 예산 안에 들어가게 자른다             — 실측: 이 레포 PR #2 가 8861줄
    4. 엔진을 돌리고 state 를 읽는다          (④⑤)
    5. 게이트에 물어보고 게시한다             (⑥)

⚠️ **이 파일에 정책이 없다.** 임계값·분기 조건은 전부 `backend/gate/` 에 있다.
   여기 하나라도 새어 들어오면 정책이 두 곳에 갈라져 산다.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from backend.gate.decision import Decision, decide, render_comment, summarize
from backend.github.client import (
    MAX_DIFF_CHARS,
    fetch_pr_diff,
    pick_reviewable_slice,
    post_pr_comment,
)
from backend.orchestration.engine import WorkflowEngine
from backend.queue.router import dequeue

log = logging.getLogger(__name__)

# 리뷰를 돌릴 만한 action 들.
#
# `pull_request` 이벤트는 action 이 20종이 넘는다 — `labeled`, `assigned`,
# `closed`, `review_requested` … 대부분은 **코드가 안 바뀐다.** 코드가 안 바뀌었는데
# 리뷰를 돌리면 LLM 호출 4번을 태우고 같은 답을 얻는다.
#
# ⚠️ `synchronize` 가 "새 커밋이 push 됐다"이다. 이게 빠지면 PR 을 고쳐도 다시 안 본다.
# ⚠️ 웹훅(①)이 아니라 여기서 거르는 이유: ①은 **10초 안에 답하는 것**이 일이고,
#    무엇을 리뷰할지는 판단이라 처리하는 쪽이 갖는 게 맞다. ①이 거르면 큐에 안 들어가서
#    "왜 리뷰가 안 됐나"를 나중에 못 본다.
REVIEWABLE_ACTIONS = frozenset({"opened", "reopened", "synchronize"})


@dataclass
class WorkResult:
    """잡 하나의 결말. **왜 안 했는지도 결말이다.**

    ⚠️ `skipped` 가 실패가 아니다 — `labeled` 이벤트를 안 돌린 건 정상 동작이다.
       실패(`error`)와 같은 통에 넣으면 알림이 시끄러워지고, 시끄러운 알림은 안 읽힌다.
    """

    review_key: str | None = None
    decision: Decision | None = None
    comment_url: str | None = None
    skipped: str | None = None
    error: str | None = None
    elapsed: float = 0.0


def build_review_key(owner: str, repo: str, number: int, head_sha: str) -> str:
    """`engine.py` 결정 1 의 재료 셋을 열쇠 하나로.

    ⚠️ **`head_sha` 가 꼭 들어간다.** 빠지면 같은 PR 의 새 커밋이 이전 체크포인트를
       물려받아 "이미 끝났다"로 판정되고, **새 코드를 아무도 안 보는 채로 통과한다.**

    ⚠️ 계산이지 저장이 아니다. `kill -9` 뒤에 재개하는 워커가 같은 재료로 다시 계산해
       같은 열쇠를 얻어야 `resume()` 이 성립한다.
    """
    return f"{owner}/{repo}#{number}@{head_sha}"


def extract_coords(payload: dict[str, Any]) -> tuple[str, str, int, str]:
    """웹훅 payload 에서 PR 좌표 넷을 뽑는다.

    ⚠️ **payload 는 신뢰할 수 없는 입력이다** — 서명은 "GitHub 이 보냈다"를 증명하지
       "내용이 옳다"를 증명하지 않는다. 그래서 `KeyError` 를 잡아 `error` 로 바꾸는 게
       호출자의 몫이고, 여기서는 조용한 기본값을 만들지 않는다.
       `.get(...)` 으로 빈 문자열을 채우면 `owner=""` 로 API 를 부르게 되고,
       그건 404 가 되어 **원인이 payload 인지 네트워크인지 알 수 없어진다.**
    """
    pr = payload["pull_request"]
    repo = payload["repository"]
    return (
        repo["owner"]["login"],
        repo["name"],
        int(pr["number"]),
        pr["head"]["sha"],
    )


def process_one(
    payload: dict[str, Any],
    engine: WorkflowEngine,
    *,
    dry_run: bool = False,
    budget: int = MAX_DIFF_CHARS,
) -> WorkResult:
    """잡 하나를 처음부터 끝까지. **예외를 밖으로 내보내지 않는다.**

    `_run_specialist` 가 예외를 삼키는 것과 같은 이유다 — 잡 하나가 터졌다고
    워커 루프가 죽으면 큐에 쌓인 나머지가 전부 멈춘다.

    Args:
        dry_run: True 면 **게시만 건너뛴다.** LLM 호출과 게이트 판정은 그대로 돈다 —
            "무엇을 게시할 뻔했나"를 보는 것이 이 플래그의 목적이라서.
            ⚠️ 게시 직전에 멈추는 것이지 리뷰를 안 하는 게 아니다. API 비용은 그대로 든다.
    """
    t0 = time.monotonic()

    action = payload.get("action")
    if action not in REVIEWABLE_ACTIONS:
        return WorkResult(skipped=f"action={action}", elapsed=time.monotonic() - t0)

    try:
        owner, repo, number, head_sha = extract_coords(payload)
    except (KeyError, TypeError, ValueError) as e:
        return WorkResult(error=f"payload 에서 PR 좌표를 못 뽑았다: {e!r}",
                          elapsed=time.monotonic() - t0)

    review_key = build_review_key(owner, repo, number, head_sha)

    try:
        raw = fetch_pr_diff(owner, repo, number)
        diff, skipped_files = pick_reviewable_slice(raw, budget=budget)
        if not diff.strip():
            return WorkResult(review_key=review_key,
                              skipped="diff 가 비었다 (문서만 바뀐 PR 이거나 예산이 너무 작다)",
                              elapsed=time.monotonic() - t0)

        # ④⑤ — 엔진이 넷을 병렬로 돌리고 애그리게이터가 합친다.
        # ⚠️ run() 은 아무것도 안 돌려준다 (engine.py 결정 2). 결과는 state 에서 읽는다 —
        #    kill -9 뒤 재개하는 워커도 같은 경로로 읽어야 하기 때문이다.
        engine.run(review_key, diff)
        state = engine.get_state(review_key)

        merged = state.get("merged") or []
        failed = state.get("failed_agents") or []

        # ⑥ — 판정. **이 줄이 이 파일에서 정책에 가장 가까이 가는 지점이고,
        #      그래서 판단 자체는 저쪽 함수 안에 있다.**
        d = decide(merged, failed)

        comment_url = None
        if not dry_run and (d.auto_post or failed or skipped_files):
            body = render_comment(
                d, head_sha=head_sha, failed_agents=failed, skipped_files=skipped_files
            )
            comment_url = post_pr_comment(owner, repo, number, body)

        log.info("%s — %s", review_key, summarize(d, failed))
        return WorkResult(review_key=review_key, decision=d, comment_url=comment_url,
                          elapsed=time.monotonic() - t0)

    except Exception as e:  # noqa: BLE001 — 루프를 살리는 것이 이 except 의 존재 이유
        log.exception("잡 처리 실패: %s", review_key)
        return WorkResult(review_key=review_key, error=f"{type(e).__name__}: {e}",
                          elapsed=time.monotonic() - t0)


def run_forever(
    engine: WorkflowEngine,
    *,
    poll_seconds: float = 1.0,
    max_jobs: int | None = None,
    dry_run: bool = False,
) -> list[WorkResult]:
    """큐가 빌 때까지(또는 영원히) 꺼내서 처리한다.

    ⚠️ **폴링이다.** 진짜 브로커라면 블로킹 pop 을 쓴다 — 인메모리 리스트엔 그게 없다.
       M4 에서 Redis 로 갈리면 이 루프가 `BRPOP` 하나로 바뀐다.

    Args:
        max_jobs: 이 개수만큼 처리하고 멈춘다. `None` 이면 큐가 빌 때까지.
            데모가 이걸 쓴다 — 무한 루프는 스크립트로 못 보여준다.
    """
    results: list[WorkResult] = []
    while max_jobs is None or len(results) < max_jobs:
        job = dequeue()
        if job is None:
            if max_jobs is None:
                break  # 큐가 비었고 목표도 없으면 끝
            time.sleep(poll_seconds)
            continue
        results.append(process_one(job, engine, dry_run=dry_run))
    return results
