"""게이트(⑥) — 무엇을 자동으로 게시하고 무엇을 사람에게 넘기나.

전체 그림에서 어디인가
----------------------
    PR → ① 웹훅 → ② 큐 → ③ 워커 → ④ 스페셜리스트 4 → ⑤ 애그리게이터 → **⑥ 여기** → GitHub

**이 파일이 이 레포에서 유일하게 정책 상수를 갖는 자리다.**
`CLAUDE.md` 「하지 말 것」 3번이 M0 부터 지켜온 것 —
*"`0.6` 같은 정책 상수를 스키마·프롬프트에 넣기 금지. 스키마는 '무엇이 존재할 수 있나',
정책은 '그중 뭘 통과시키나'. 임계값은 M8 `backend/gate/` 가 생길 때까지 어디에도 안 나온다."*

**지금이 그 시점이다.** 여덟 마일스톤 동안 미뤄온 숫자가 여기서 처음 코드가 된다.

왜 이게 이 시스템의 심장인가
----------------------------
제1원칙은 **선별**(selectivity) [00:38:27] — 많이 지적하는 게 아니라 **틀린 말을 안 하는 것**.
그런데 앞의 다섯 단계는 선별을 못 한다:
    ④ 스페셜리스트는 **찾는** 게 일이다. 안 찾으면 직무유기다
    ⑤ 애그리게이터는 **정리**만 한다. 판단은 안 한다고 스스로 선언했다
→ **아무도 "이건 말하지 말자"를 안 했다.** 그 일이 전부 여기 몰려 있다.

경계
----
한다:   게시 여부 판정 · 커버리지 판정(G2) · 사람에게 넘길 것 고르기
안 한다: GitHub 과 말하기(`backend/github/`) · 병합(`backend/agents/aggregator.py`)
        ⚠️ 이 파일은 `httpx` 를 import 하지 않는다. 판정은 순수 함수여야 재현된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.agents.schema import SEVERITY_RANK, normalize_category

# ─────────────────────────────────────────────────────────────────────
# 이 레포에서 **유일한 정책 상수**. 여덟 마일스톤 미뤄온 자리다.
#
# ⚠️ 숫자가 아니라 **목록**인 것이 이 결정의 요점이다. 아래 근거 참조.
# ─────────────────────────────────────────────────────────────────────
HUMAN_ONLY_CATEGORIES: frozenset[str] = frozenset({"review-evasion-attempt"})


@dataclass
class Decision:
    """게이트 한 번의 판정 결과. **왜 그렇게 갈랐는지가 같이 나온다.**

    ⚠️ `reasons` 가 장식이 아니다 — 자동 게시된 지적이 나중에 오탐으로 드러났을 때
       "게이트가 왜 통과시켰나"에 답할 유일한 기록이다. M9 대시보드가 읽을 자리이기도 하다.
    """

    auto_post: list[dict[str, Any]] = field(default_factory=list)
    to_human: list[dict[str, Any]] = field(default_factory=list)
    suppressed: list[dict[str, Any]] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    @property
    def needs_human(self) -> bool:
        return bool(self.to_human)


# ─────────────────────────────────────────────────────────────────────
# ✅ **결정됨 (2026-08-29, 사용자)** — 이 프로젝트가 여덟 마일스톤 미뤄온 숫자가
#    열렸는데, **숫자가 아니라 목록이 됐다.**
#
# ── 무엇을 정했나 ───────────────────────────────────────────────────
#     `review-evasion-attempt` → **무조건 사람**.  나머지 전부 → **자동 게시**
#     `failed_agents` 가 있어도 → **게시하되 코멘트에 "못 본 관점"을 적는다**
#     `suppressed` 는 **안 쓴다** — 아무것도 조용히 죽이지 않는다
#
# ── 왜 confidence 를 안 쓰나 (실측이 뒤집었다) ──────────────────────
#   정답지로 61건에 y 라벨을 붙여 오탐/정탐의 confidence 를 갈라 재봤다:
#
#       정탐 47건   최소 0.87 · 중앙 1.00 · 최대 1.00
#       오탐  5건   최소 0.82 · 중앙 1.00 · 최대 1.00     ← **겹친다**
#
#   **오탐이 정탐보다 확신이 낮지 않다.** 어떤 임계값을 그어도 정탐을 같이 죽인다.
#   그리고 `confidence >= 0.6`(영상 값)은 **61/61 이 통과**해서 아무 일도 안 한다 —
#   규칙이 둘인 척하지만 실제로 도는 건 severity 하나뿐이었다.
#   📖 책 인쇄 291 이 같은 결론을 이론에서 준다: *"모델이 신뢰도 같은 값을 산출하더라도
#      **검증 전 추정치일 뿐 승인 게이트의 근거로 사용하지 않습니다.**"*
#   ⚠️ **그래서 INV-3 이 지키는 `confidence` 필드를 게이트가 안 읽는다.**
#      불변식이 죽은 게 아니라 **읽는 자리가 아직 없다** — M9 대시보드가 보정(calibration)을
#      보여줄 때, 그리고 프롬프트를 고쳐 분포가 벌어질 때 다시 재료가 된다.
#      지금은 "필드는 있는데 변별력이 없다"가 정직한 상태고, 그게 M6-0b 가 잰 그것이다.
#
# ── 왜 severity 도 안 쓰나 ──────────────────────────────────────────
#       critical 전체      29건 · 오탐 4건
#       evasion 을 빼면    19건 · 오탐 **0건**   ← 전부 sql-injection, 전부 정탐
#
#   **영상의 "critical 이면 사람에게"는 틀린 축을 잘랐다.** 위험한 건 critical 이 아니라
#   `review-evasion-attempt` 였고, 그 둘이 겹쳐 있어서 severity 가 범인으로 보였을 뿐이다.
#   그 축으로 자르면 **맞는 지적 19개를 사람이 다시 읽게 된다** (자동화 83% → 52%).
#
# ── 왜 category 인가 — 오탐이 거기 몰려 있다 ────────────────────────
#       review-evasion-attempt   정탐  6 · 오탐 4  →  40%
#       missing-security-tests   정탐  0 · 오탐 1  → 100%  (n=1, 근거 없음)
#       sql-injection            정탐 24 · 오탐 0  →   0%
#       resource-leak            정탐 17 · 오탐 0  →   0%
#
#   ⚠️ **그런데 비율이 진짜 근거가 아니다. 피해의 비대칭이 근거다.**
#      `sql-injection` 오탐은 "아 아니네" 로 끝난다.
#      `review-evasion-attempt` 오탐은 **공개 PR 에서 작성자를 "리뷰를 회피하려 한 사람"으로
#      모는 것**이다. 되돌려도 알림은 이미 갔다. 제1원칙(틀린 말을 안 하는 것)이
#      겨냥하는 게 정확히 이런 종류다.
#   ⚠️ `missing-security-tests` 는 **규칙에 안 넣었다.** 1건으로 100% 는
#      Wilson 으로 재면 [0.03, 1.00] 이라 아무 말도 못 한다. 표본이 없으면 규칙도 없다.
#
# ── 시뮬레이션 (저장된 61건 기준) ───────────────────────────────────
#       자동 게시 51건 — 정탐 41 · 오탐 1 · 보류 9      (자동화 83%)
#       사람에게  10건 — 정탐  6 · 오탐 4
#   남은 오탐 1건이 위의 `missing-security-tests` 다.
#
# ── ⚠️ 알고 받아들인 것 넷 ─────────────────────────────────────────
#   1. **이건 증상 치료다.** `review-evasion-attempt` 오탐의 원인은 프롬프트의
#      `TAG_RULE` 자기참조다 — 우리가 씌운 `<untrusted_diff>` 포장지를 모델이 신고한다.
#      근본 치료는 M6-3b 에서 그 규칙을 좁히는 것이고, **그때 이 목록이 짧아져야 한다.**
#   2. **블랙리스트는 새 이름에 뚫린다.** 모델이 `evasion-attempt` 라고 뱉으면 통과한다.
#      `normalize_category` 로 표기 흔들림은 막지만 **다른 이름은 못 막는다.**
#      → 그래서 `category` 를 화이트리스트로 조이는 문제가 여기서 다시 열린다
#        (`fixtures/expected.yaml` D2++ 와 같은 질문). 지금은 목록이 하나뿐이라 버틴다.
#   3. **시뮬레이션은 원본 findings 기준이다.** 게이트는 실제로 `merged` 를 받으므로
#      숫자가 조금 달라진다. 방향은 안 바뀐다 — 병합은 category 를 안 바꾼다.
#   4. **표본이 픽스처 3개에서 나왔다.** 실제 PR 이 들어오면 category 종류가 늘고,
#      그때 이 목록을 다시 재야 한다.
#
# ── 되돌리는 조건 ───────────────────────────────────────────────────
#   · M6-3b 에서 `tag_rule` 을 좁혀 `review-evasion-attempt` 오탐률이 떨어지면 → 목록에서 뺀다
#   · 자동 게시된 것 중 오탐이 실제로 보고되면 → 그 category 를 목록에 넣고, 왜인지 적는다
#   · confidence 분포가 벌어지면(프롬프트 수정 뒤) → confidence 축을 다시 본다
# ─────────────────────────────────────────────────────────────────────
def decide(
    merged: list[dict[str, Any]],
    failed_agents: list[str] | None = None,
) -> Decision:
    """합쳐진 findings → 무엇을 게시하고 무엇을 사람에게.

    Args:
        merged: `aggregate()` 의 출력. 심각도 → 파일 → category 로 정렬돼 있다.
        failed_agents: 죽어서 아무것도 못 본 관점들. 커버리지 판정(G2)의 재료.

    Returns:
        `Decision` — 세 통 + 왜 그렇게 갈랐는지.
    """
    d = Decision()
    failed = list(failed_agents or [])

    for f in merged:
        if normalize_category(f["category"]) in HUMAN_ONLY_CATEGORIES:
            d.to_human.append(f)
        else:
            d.auto_post.append(f)

    if d.to_human:
        cats = sorted({normalize_category(f["category"]) for f in d.to_human})
        d.reasons.append(
            f"사람 확인 필요 {len(d.to_human)}건 — {', '.join(cats)}: "
            f"오탐일 때 피해가 비대칭이라 자동 게시하지 않는다"
        )
    if d.auto_post:
        d.reasons.append(
            f"자동 게시 {len(d.auto_post)}건 — confidence·severity 로 거르지 않는다 "
            f"(실측: 오탐과 정탐의 분포가 겹친다)"
        )
    if failed:
        # ⚠️ **게시를 막지는 않는다** (2026-08-29 결정). 찾은 지적은 여전히 값어치 있다.
        #    대신 코멘트가 "못 본 관점"을 반드시 적는다 — `render_comment()` 가 그 일을 한다.
        #    "문제 없음"과 "아무도 안 봄"이 같아 보이는 것이 이 프로젝트 최악의 시나리오(G2)이고,
        #    막는 방법이 게시 중단만 있는 건 아니다. **드러내는 것으로도 막힌다.**
        d.reasons.append(
            f"⚠️ 커버리지 결손 — {', '.join(failed)} 관점이 실패했다. "
            f"게시는 하되 코멘트에 명시한다"
        )
    if not merged:
        d.reasons.append("합쳐진 지적이 0건 — 게이트가 판정할 것이 없다")

    return d


def summarize(d: Decision, failed_agents: list[str] | None = None) -> str:
    """판정을 사람이 읽을 한 줄로. 로그와 데모가 같은 문장을 쓰게 하려고 여기 둔다."""
    parts = [
        f"자동 게시 {len(d.auto_post)}",
        f"사람 {len(d.to_human)}",
        f"보류 {len(d.suppressed)}",
    ]
    if failed_agents:
        parts.append(f"⚠️ 못 본 관점 {','.join(failed_agents)}")
    return " · ".join(parts)


def render_comment(
    d: Decision,
    *,
    head_sha: str,
    failed_agents: list[str] | None = None,
    skipped_files: list[str] | None = None,
) -> str:
    """게시할 코멘트 본문(마크다운).

    ⚠️ **줄 단위가 아니라 PR 전체에 달린다** — `github/client.py:post_pr_comment` 참조.
       그래서 `line` 은 본문 안에 **참고값**으로만 적고, 그 사실을 밝힌다.
       틀린 좌표를 확정처럼 보여주면 읽는 사람이 엉뚱한 줄을 본다.

    ⚠️ **안 본 것을 반드시 적는다.** 실패한 관점과 예산에서 빠진 파일이 코멘트에
       안 적히면, 읽는 사람은 "문제 없음"으로 읽는다 (Lesson 06).
    """
    lines = ["## 🤖 자동 코드 리뷰", ""]

    if not d.auto_post:
        lines.append("자동 게시 기준을 넘은 지적이 없습니다.")
    else:
        for f in sorted(d.auto_post, key=lambda x: SEVERITY_RANK[x["severity"]]):
            srcs = ", ".join(f.get("sources", []))
            lines += [
                f"### `{f['severity']}` · {f['category']}",
                f"**{f['file']}** (참고 줄 ~{f['line']}) · 확신 {f['confidence']:.2f}"
                f" · 관점: {srcs}",
                "",
                f["rationale"],
                "",
            ]

    if d.to_human:
        # 🔴 **이 블록이 두 번 고쳐졌다. 두 번째는 첫 번째 수정이 만든 사고 때문이다.**
        #
        # 1차 (2026-08-30) — 리뷰가 `human-handoff`(0.96)·`human-review-visibility`(0.93)로
        #    *"건수만 적어서 사람이 무엇을 볼지 알 수 없다"* 를 지적했다. 맞는 말이라
        #    `<details>` 로 파일·확신·rationale 을 펼쳐 넣었다.
        #
        # 2차 (2026-08-30, 같은 날) — **그 수정이 게이트를 정면으로 깼다.**
        #    리뷰가 `human-only-finding-leak`(0.99, high)로 잡았다:
        #      *"`decide()` 는 `to_human` 을 자동 게시하지 않도록 분류하지만
        #        `render_comment()` 가 그 항목의 rationale 을 PR 코멘트에 그대로 렌더링한다.
        #        특히 review-evasion 지적은 공개 PR 에서 작성자를 리뷰 회피자로 몰 수 있어
        #        (…) 정책과 동작이 모순된다."*
        #    실제로 유출됐다 — PR #3 에 evasion 3건이 `<details>` 안에 게시됐다.
        #
        # ⚠️ **두 지적이 서로 충돌한다. 둘 다 맞다.**
        #    "사람에게 넘긴 걸 보여줘라" vs "사람에게 넘긴 건 공개하지 마라".
        #    한 출구에서 둘을 만족할 수 없다 — **채널이 갈려야 한다.**
        #      · 공개 코멘트(여기)  → 무엇이 보류됐는지 **종류와 건수만**
        #      · 사람 큐(HITL, M8)  → 파일·rationale·확신 전부. `Decision.to_human` 이 재료
        #    `docs/02-architecture.md` 의 사람 큐가 원래 그 자리다. 한 곳에 욱여넣은 게
        #    이 사고의 원인이고, 그래서 여기서는 **상세를 절대 안 적는다.**
        cats = sorted({normalize_category(f["category"]) for f in d.to_human})
        lines += [
            "---",
            f"🙋 **사람 확인 대기 {len(d.to_human)}건** — "
            f"`{'`, `'.join(cats)}` 는 오탐일 때의 피해가 커서 자동 게시하지 않습니다. "
            f"(확신·심각도로 거르지 않습니다.)",
            "",
            "<sub>상세는 공개하지 않습니다 — 사람이 확인한 뒤 필요하면 별도로 전달됩니다.</sub>",
            "",
        ]

    notes = []
    if failed_agents:
        notes.append(
            f"⚠️ **{', '.join(failed_agents)}** 관점은 실행에 실패해 **보지 못했습니다.** "
            "이 영역에 문제가 없다는 뜻이 아닙니다."
        )
    if skipped_files:
        shown = ", ".join(f"`{p}`" for p in skipped_files[:5])
        more = f" 외 {len(skipped_files) - 5}개" if len(skipped_files) > 5 else ""
        notes.append(f"⚠️ diff 예산을 넘어 **리뷰하지 않은 파일**: {shown}{more}")
    if notes:
        lines += ["---", *notes, ""]

    lines += [
        "---",
        f"<sub>커밋 `{head_sha[:8]}` 기준 · 줄 번호는 참고값입니다 "
        "(모델이 계산한 값이라 어긋날 수 있습니다).</sub>",
    ]
    return "\n".join(lines)
