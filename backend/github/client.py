"""GitHub API — diff 를 가져오고 리뷰를 되돌려 붙인다.

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → **③ 워커** → ④ 스페셜리스트 4 → ⑤ 애그리게이터 → ⑥ 게이트
                              │                                              │
                              └── 여기서 diff 를 읽고 ────────────────────────┘
                                                          여기서 코멘트를 쓴다

**왜 이 파일이 필요한가 — 웹훅 payload 에는 diff 가 없다.**
GitHub 이 보내는 것은 PR 메타데이터(번호·제목·head sha·레포)뿐이다.
diff 를 보려면 API 를 한 번 더 불러야 하고, 그래서 워커가 이 모듈을 안다.

경계
----
한다:   GitHub 과 HTTP 로 말하는 것 전부 (diff 읽기 · 코멘트 쓰기)
안 한다: **무엇을 게시할지 판단** — 그건 `backend/gate/` 의 몫이다.
        이 파일은 "써라"를 받으면 쓴다. 정책 상수(`0.6` 같은 것)가 여기 오면 안 된다.

⚠️ **트러스트 바운더리가 여기서도 걸린다.** `fetch_pr_diff()` 가 돌려주는 문자열은
   PR 을 연 누구나 내용을 정할 수 있는 **신뢰할 수 없는 입력**이다
   (`docs/02-architecture.md` · Lesson 02). 이 파일은 그걸 격리하지 않는다 —
   격리는 `backend/agents/base.py:build_user_message()` 가 한다.
   여기서 하면 격리가 두 곳에 살고, 두 곳에 사는 것은 반드시 갈라진다.
"""

from __future__ import annotations

import os
from fnmatch import fnmatch

import httpx
from dotenv import load_dotenv

load_dotenv()

API = "https://api.github.com"

# ⚠️ **없으면 부팅을 거부한다** — 이 레포가 세 번 한 선택과 같은 가족이다
#    (`webhook/security.py` secret 없으면 거부 · `base.py` 모델 거부 시 예외 ·
#     `review_diff` 출처 없이 부르면 TypeError).
#    토큰 없이 조용히 돌면 게시가 401 로 실패하는데, 그건 **리뷰를 다 하고 나서** 터진다.
#    LLM 호출 4번을 태우고 마지막에 죽는 것보다 시작 전에 죽는 게 싸다.
TOKEN_ENV = "GITHUB_TOKEN"

# 리뷰에 넣을 diff 의 상한 (문자 수).
#
# ⚠️ 왜 필요한가 — 실측: 이 레포 PR #2 의 diff 가 **8861줄**이다.
#    `fixtures/sample.diff` 는 13줄이므로 **680배**다. 그대로 넣으면:
#      · 컨텍스트가 터지거나 (모델 한도)
#      · 안 터져도 품질이 무너진다 (📖 책 인쇄 54 — 긴 컨텍스트의 중간이 묻힌다)
#      · 캐시 접두부(1792 토큰)의 이득이 상대적으로 사라진다
#
# 📖 `03-build-plan.md` M7 — *"원리적으로는 되지만 컨텍스트 창이 터지고 출력 품질이
#    무너짐. 그래서 답은 '더 큰 컨텍스트'가 아니라 **검색**."*
#    → **진짜 답은 M7 의 RAG 다.** 이 상수는 그때까지 버티는 임시 방편이고,
#      그 사실이 여기 적혀 있어야 한다.
#
# 20000자는 대략 코드 파일 대여섯 개 분량이다. 넘으면 `split_diff_by_file()` 로 쪼갠다.
#
# ⚠️ 8000 에서 올린 이유(2026-08-29 실측): 이 레포 PR #2 는 필터 후에도 16파일 100,291자다.
#    8000 이면 **16개 중 13개가 빠진다.** "83%를 안 봤습니다"가 적힌 코멘트는
#    정직하기는 해도 쓸모가 없다. 올려도 여전히 다 못 보지만 **볼 만큼은 본다.**
# ⚠️ 이건 품질과의 맞바꿈이다 — 📖 책 인쇄 54, 긴 컨텍스트는 중간이 묻힌다.
#    **진짜 답은 M7 의 RAG 이고, 그때 이 상수는 사라진다.**
MAX_DIFF_CHARS = 20000

# 리뷰 대상이 아닌 파일들.
#
# ⚠️ **크기 문제의 절반은 대상 문제였다.** 실측: PR #2 의 509,615자 중
#    `uv.lock` 하나가 160,285자이고, 생성된 `learning/sims/*.html` 넷이 11만 자다.
#    필터 하나로 **509,615 → 100,291자 (80% 감소)**.
#
# 왜 이게 판단인가 — "무엇이 리뷰 대상인가"는 정책에 가깝다. 다만 관례가 강해서
# (lock 파일과 생성물을 사람이 리뷰하지 않는다) 기본값을 코드가 갖는다.
# ⚠️ 잘못 넣으면 **진짜 코드가 조용히 안 읽힌다.** 그래서 `pick_reviewable_slice()` 가
#    걸러낸 파일을 반환하고, 코멘트가 그걸 적는다 — 안 본 것은 반드시 드러나야 한다.
#
# ⚠️ `.md` 는 **일부러 안 넣었다.** docs 관점이 문서를 봐야 하기 때문이다.
#    문서가 예산을 다 먹으면 그때 다시 본다.
SKIP_PATTERNS: tuple[str, ...] = (
    "*.lock",  # 의존성 잠금 — 사람이 안 읽는다. PR #2 에서 160KB
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.pdf",
    "*.min.js",
    "*.min.css",
    "*.ipynb",  # 셀 출력이 diff 를 덮는다
    "learning/sims/*.html",  # 생성된 시뮬레이터 — PR #2 에서 11만 자
    "learning/lessons/*.html",
    "learning/reference/*.html",
    "*.snap",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
)


def _headers(accept: str) -> dict[str, str]:
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(
            f"{TOKEN_ENV} 가 없다. `gh auth token --user sml1323` 으로 뽑아 .env 에 넣을 것. "
            f"토큰 없이 시작하면 LLM 호출 4번을 태우고 게시에서 401 로 죽는다."
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_pr_diff(owner: str, repo: str, number: int, timeout: float = 30.0) -> str:
    """PR 의 통합 diff 를 문자열로.

    ⚠️ 반환값은 **신뢰할 수 없는 입력**이다. 격리는 호출자가 아니라
       `build_user_message()` 가 한다 (모듈 docstring 참조).

    ⚠️ `Accept: ...v3.diff` 가 핵심이다. 기본 JSON 을 받으면 파일 목록과 patch 조각이
       따로 오고, 그걸 다시 이어붙이면 `@@` 헤더 계산이 우리 손을 타게 된다.
       GitHub 이 만든 통합 diff 를 그대로 받는 쪽이 항상 정확하다.
    """
    r = httpx.get(
        f"{API}/repos/{owner}/{repo}/pulls/{number}",
        headers=_headers("application/vnd.github.v3.diff"),
        timeout=timeout,
        follow_redirects=True,
    )
    r.raise_for_status()
    return r.text


def fetch_pr_meta(owner: str, repo: str, number: int, timeout: float = 30.0) -> dict:
    """PR 메타데이터. `head.sha` 가 `review_key` 의 재료다.

    왜 sha 가 필요한가 — `review_key` 에 head sha 가 들어가야 **같은 열쇠 = 같은 코드**가
    성립한다 (`engine.py` 결정 1). PR 번호만 쓰면 커밋을 새로 밀어도 같은 열쇠가 되어
    멱등 가드(G11)가 "이미 리뷰했다"고 판단해 버린다.
    """
    r = httpx.get(
        f"{API}/repos/{owner}/{repo}/pulls/{number}",
        headers=_headers("application/vnd.github+json"),
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def post_pr_comment(
    owner: str, repo: str, number: int, body: str, timeout: float = 30.0
) -> str:
    """PR 에 코멘트 하나를 단다. 돌려주는 것은 그 코멘트의 URL.

    ⚠️ **줄 단위(review comment)가 아니라 PR 전체(issue comment)에 단다.**

    줄 단위로 달려면 `POST /pulls/{n}/comments` 에 `path` 와 `line` 을 줘야 하는데,
    **우리 `line` 이 틀린다.** 실측(2026-08-28, `sample.diff`):

        sql-injection  정답 :16   모델 넷이 :17 :17 :15 :17   → 넷 다 틀림
        resource-leak  정답 :14   :18 ×5 · :14 ×1            → 하나만 맞음, 그리고 버려짐

    틀린 줄에 코멘트를 달면 **엉뚱한 코드를 지적하는 것**이고, 그건 이 프로젝트의
    제1원칙(선별 — 틀린 말을 안 하는 것)을 정면으로 깬다.
    → 줄을 못 믿는 동안은 PR 전체에 단다. `line` 은 본문 안에 **참고값으로** 적는다.

    ⏭ 되돌리는 조건: `@@` 헤더 파서를 붙여 줄 번호를 **코드가** 계산하면
       (📖 인쇄 318 — 결정론적 검사) 그때 줄 단위로 옮긴다.
    """
    r = httpx.post(
        f"{API}/repos/{owner}/{repo}/issues/{number}/comments",
        headers=_headers("application/vnd.github+json"),
        json={"body": body},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["html_url"]


def split_diff_by_file(diff: str) -> list[tuple[str, str]]:
    """통합 diff 를 파일별로 쪼갠다. `[(파일경로, 그 파일의 diff), ...]`

    왜 파일 단위인가 — `Finding.file` 이 파일 경로이고 dedup 키가 `(file, category)` 라서,
    쪼개는 단위가 파일이면 **합치는 단위와 어긋나지 않는다.** 청크로 쪼개면 같은 파일이
    두 청크에 걸쳐 같은 결함을 두 번 보고할 수 있고, 그건 애그리게이터가 못 가른다.

    ⚠️ 이건 M7 RAG 의 **대체품이 아니다.** 검색이 아니라 그냥 자르는 것이라
       "이 함수의 호출부가 다른 파일에 있다" 같은 맥락은 여전히 없다.
    """
    if not diff.strip():
        return []

    chunks: list[tuple[str, str]] = []
    current_path: str | None = None
    current: list[str] = []

    for line in diff.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_path is not None:
                chunks.append((current_path, "".join(current)))
            # `diff --git a/경로 b/경로` 에서 b/ 쪽을 쓴다 — 새 파일 기준이 우리 기준이다
            parts = line.split()
            current_path = parts[3][2:] if len(parts) >= 4 else "<unknown>"
            current = [line]
        else:
            current.append(line)

    if current_path is not None:
        chunks.append((current_path, "".join(current)))
    return chunks


def is_reviewable(path: str) -> bool:
    """이 파일을 리뷰 대상으로 볼 것인가. `SKIP_PATTERNS` 참조."""
    return not any(fnmatch(path, pat) for pat in SKIP_PATTERNS)


def pick_reviewable_slice(
    diff: str, budget: int = MAX_DIFF_CHARS
) -> tuple[str, list[str]]:
    """예산 안에 들어가는 만큼만 고른다. `(리뷰할 diff, 안 본 파일 목록)`

    두 단계로 줄인다:
        1. **대상 필터** — lock 파일·생성물을 뺀다 (`SKIP_PATTERNS`)
        2. **예산** — 남은 것을 큰 순서가 아니라 **diff 순서대로** 채운다

    ⚠️ 2단계에서 정렬을 안 하는 게 결정이다. 작은 파일부터 채우면 개수는 늘지만
       **큰 파일이 항상 빠진다** — 그리고 큰 변경일수록 결함이 있을 확률이 높다.
       diff 순서(= GitHub 이 준 순서, 대략 알파벳순)면 편향이 없다.

    ⚠️ **빠진 파일을 돌려주는 게 계약의 절반이다.** 조용히 자르면 게이트가
       "이 PR 은 문제 없음"과 "이 PR 의 절반을 안 봤음"을 구별하지 못한다 —
       이 프로젝트 최악의 시나리오(G2)와 같은 모양이다.
       그래서 호출자가 이 목록을 **코멘트 본문에 적어야 한다.**

    ⚠️ 파일 하나가 예산보다 크면 그 파일은 통째로 뺀다. 잘라 넣지 않는다 —
       잘린 diff 는 `@@` 헤더와 본문이 어긋나서 줄 계산이 더 나빠진다.
    """
    files = split_diff_by_file(diff)
    if not files:
        # ⚠️ **리뷰에서 지적받아 고쳤다** (2026-08-30, PR #3 — `diff-budget-bypass`, conf 0.99):
        #    *"`diff --git` 헤더가 하나도 없으면 `diff[:budget]` 만 반환하면서
        #      `skipped_files` 는 빈 목록으로 반환한다. 예산을 초과한 내용이 잘렸는데도
        #      호출자는 **모든 파일을 리뷰한 것으로 오인**할 수 있다."*
        #    이 함수 docstring 이 *"빠진 파일을 돌려주는 게 계약의 절반"* 이라고 적어놓고
        #    이 분기에서만 그 계약을 안 지키고 있었다.
        if len(diff) > budget:
            return diff[:budget], ["<파일 헤더 없는 diff — 예산을 넘어 잘렸다>"]
        return diff, []

    kept: list[str] = []
    skipped: list[str] = []
    used = 0
    for path, chunk in files:
        if not is_reviewable(path):
            skipped.append(path)
            continue
        if used + len(chunk) <= budget:
            kept.append(chunk)
            used += len(chunk)
        else:
            skipped.append(path)
    return "".join(kept), skipped
