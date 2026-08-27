"""K판 돌리고 표를 찍는다 — M6-1 의 마지막 조각.

왜 있나 ───────────────────────────────────────────────────────────────
2026-08-27 에 자를 두 번 고쳤다(화이트리스트 · 축 분리). 두 번 다 재채점을
채팅 안 즉석 스크립트로 돌렸고, 그건 git 에 없다. 다음에 또 필요하면 또 짠다.
그 사이 판정이 미묘하게 달라지면 `6/9 → 5/9` 가 **자가 바뀌어서인지
스크립트가 바뀌어서인지 알 수 없다.** 그래서 여기 고정한다.

모드가 둘인 이유 ──────────────────────────────────────────────────────
    --run      새로 K판 호출 → 원시 결과를 evals/runs/ 에 저장   (14~20초/판. 비싸다)
    --regrade  저장된 파일을 다시 채점                          (공짜. 무한 반복)

호출과 채점을 분리한 게 핵심이다. 자는 자주 바뀌고 호출은 비싸다 —
자를 고칠 때마다 다시 부르면 그날 못 고친다.

경계 ─────────────────────────────────────────────────────────────────
안 한다: 프롬프트 변형 비교(M6-3b — `review_diff()` 가 아직 SYSTEM_PROMPT 를
        하드코딩한다. 그 구멍은 M6-4 배선에서 뚫린다) · McNemar(같은 이유로 아직 이르다)
"""

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

# scripts/ 안에서 실행하면 sys.path[0] 이 scripts/ 라 evals·backend 가 안 보인다.
# demo_m0.py 와 같은 관례 — 레포 루트를 앞에 꽂는다.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agents.base import MODEL, review_diff  # noqa: E402
from evals.grader import RunGrade, grade_run, load_expected  # noqa: E402
from evals.stats import wilson_ci  # noqa: E402

RUNS_DIR = ROOT / "evals" / "runs"
FIXTURES_DIR = ROOT / "fixtures"


# ──────────────────────────────────────────────────────────────────────
# TODO(human) ① — 실패한 호출을 판으로 셀 것인가
#
# 왜 이게 판단인가 ─────────────────────────────────────────────────────
# `review_diff()` 는 두 가지로 실패할 수 있다:
#   (a) 모델이 **거부**한다 → `RuntimeError("모델이 응답을 거부했다: ...")`
#       ⚠️ 이건 버그가 아니라 **관측**이다. 특히 `sample_injected` 에서
#          인젝션에 반응해 거부하는 건 우리가 알고 싶은 바로 그 행동이다.
#   (b) 네트워크·타임아웃·프록시 죽음 → 그 밖의 예외
#       ⚠️ 이건 모델과 무관하다. 프록시는 재부팅을 못 넘긴다(CURRENT.md).
#
# 이 함수는 그 판을 **셋 중 하나로** 분류해야 한다:
#     "실패한 판"   → n 에 세고 x 에 안 센다  → 성공률이 내려간다
#     "무효한 판"   → n 에도 안 센다          → 없었던 일이 된다
#     "터뜨린다"    → 스크립트를 멈춘다        → 부분 결과를 잃는다
#
# 그리고 (a) 와 (b) 를 **같게 다룰 이유가 없다.**
#
# 왜 중요한가 — `wilson_ci(x, n)` 의 `n` 이 여기서 정해진다 ────────────
# 10판 중 2판이 타임아웃이면:
#     실패로 세면  → 8/10 = 0.80
#     무효로 빼면  → 8/8  = 1.00
# **같은 관측인데 결론이 다르다.** 그리고 우리 n 은 3~15 라 한두 판이 크게 흔든다
# (`evals/stats.py` 가 Wald 대신 Wilson 을 쓰는 이유와 같은 사정).
#
# 📖 책 인쇄 219 — 실험의 수용 기준: *"정식 결과에는 모든 모델 × 과제 × 반복 셀,
#    **API 오류 0건**, 독립적인 최종 테스트 … 가 포함되어야 한다."*
#    → 책은 **API 오류가 섞인 결과를 정식으로 인정하지 않는다.** 그건 (b) 를
#      "무효" 로 보는 쪽에 가깝다. ⚠️ 다만 책은 (a) **모델의 거부**를 다루지 않는다 —
#      우리 인젝션 픽스처에선 거부가 정상 동작일 수 있고, 그건 우리가 정하는 자리다.
#
# 틀리면 뭐가 깨지나 ───────────────────────────────────────────────────
#   전부 실패로 세면: 프록시가 불안정한 날 잰 값이 프롬프트가 나쁜 것처럼 보인다.
#   전부 무효로 빼면: 모델이 인젝션에 거부하는 **진짜 행동**이 기록에서 사라진다.
#   전부 터뜨리면:    14판째에 죽으면 앞의 13판 호출이 통째로 날아간다.
#
# ✅ 결정 (2026-08-27, 사용자) — 상태 셋. (a) 와 (b) 를 다르게 센다.
#
#     ok        분모에 센다
#     refused   **분모에 센다(실패로)** + 비율을 따로 찍는다
#     error     분모에서 뺀다                📖 인쇄 219 "API 오류 0건"
#
#   그리고 **터뜨리지 않는다** — 14판째에 죽으면 앞의 13판 호출이 통째로 날아간다.
#
#   **왜 거부가 실패인가** — 거부하면 findings 가 0개인데, 0개는 두 뜻이 될 수 있다:
#     "문제가 없다"(좋은 소식) vs **"확인을 못 했다"**(전혀 다른 소식).
#   거부는 후자다. 이건 `004_truth.sql` 이 `failed_agents` 를 따로 둔 이유(**G2**)와
#   같은 사고다 — *"critical 없음"과 "확인 안 됨"을 게이트가 구분 못 하는 것.*
#   그리고 `sample_injected` 의 정답지는 `review-evasion-attempt` 를 **보고하라**고 적었다.
#   거부하면 인젝션이 있었다는 사실조차 안 남는다. 우리가 만드는 건 *"위험하면 손 떼는
#   시스템"* 이 아니라 *"위험한 걸 찾아서 알려주는 시스템"* 이다 — **거부는 방어가 아니라 침묵이다.**
#
#   **왜 그래도 따로 찍나** — 거부율 자체가 봐야 할 숫자다. 프롬프트를 고쳤더니 거부가
#   늘었다면 중요한 신호인데, `8/9` 안에 섞이면 안 보인다.
#
#   ⚠️ 구현 메모: `refused` 는 `findings: []` 를 남긴다. 빈 리스트는 must_catch 를
#      하나도 못 맞추므로 grader 가 **자연스럽게 실패로 센다** — 분모 처리를 위해
#      채점 쪽에 예외를 만들 필요가 없다. `error` 만 `findings` 키가 없다.
# ──────────────────────────────────────────────────────────────────────
def run_once(diff_text: str) -> tuple[str, dict[str, Any]]:
    """한 판 호출한다. 실패를 어떻게 분류할지가 이 함수의 전부다."""
    started = time.monotonic()
    try:
        result, usage = review_diff(diff_text)
    except RuntimeError as e:
        # base.py 가 거부를 RuntimeError 로 감싸 던진다 (output_parsed is None).
        # findings 를 빈 리스트로 남겨야 분모에 들어간다 — 위 메모 참조.
        return "refused", {
            "elapsed": round(time.monotonic() - started, 2),
            "findings": [],
            "reason": str(e),
        }
    except Exception as e:  # noqa: BLE001 — 인프라 잡음은 종류를 안 가린다
        # ⚠️ findings 키를 **안 남긴다.** 그래야 채점에서 빠진다.
        #    대신 예외 타입을 남긴다 — 빈 dict 로 두면 파일만 보고 원인을 못 찾는다.
        return "error", {
            "elapsed": round(time.monotonic() - started, 2),
            "error_type": type(e).__name__,
            "reason": str(e),
        }

    # usage 를 같이 남긴다. 프록시 프롬프트 캐시 적중률이 여기서 공짜로 쌓인다 —
    # `docs/CURRENT.md` 의 미해결 항목("적중률은 안 쟀다")이 이 필드로 메워진다.
    return "ok", {
        "elapsed": round(time.monotonic() - started, 2),
        "usage": _usage_dict(usage),
        "findings": [f.model_dump() for f in result.findings],
    }


def _usage_dict(usage: object) -> dict[str, Any]:
    """Responses API 의 usage 를 JSON 으로. 필드가 없는 백엔드도 있으므로 방어적으로."""
    out: dict[str, Any] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        if (v := getattr(usage, key, None)) is not None:
            out[key] = v
    details = getattr(usage, "input_tokens_details", None)
    if (cached := getattr(details, "cached_tokens", None)) is not None:
        out["cached_tokens"] = cached
    reasoning = getattr(getattr(usage, "output_tokens_details", None), "reasoning_tokens", None)
    if reasoning is not None:
        out["reasoning_tokens"] = reasoning
    return out


# ──────────────────────────────────────────────────────────────────────
# TODO(human) ② — 이 실행을 무엇이 식별하나
#
# 왜 이게 판단인가 ─────────────────────────────────────────────────────
# `evals/runs/` 에 파일이 쌓인다. M6-3b 에서 프롬프트 후보 3개를 돌리면 곧 여러 개가 된다.
# 그때 물어야 하는 건 **"이 두 파일을 비교해도 되나"** 이고,
# 그 답은 **파일이 자기 조건을 얼마나 적어뒀나**로만 나온다.
#
# 지금 아는 후보들 — 무엇이 다르면 "다른 실행"인가:
#     model            gpt-5.6-luna → 바뀌면 옛 결과는 비교 대상이 아니다
#     프롬프트          M6-3b 의 실험 축 그 자체. 근데 지금은 SYSTEM_PROMPT 하나뿐이다
#     tag_rule         D4 의 토글 (2x2 의 with_tag_rule / no_tag_rule)
#     fixture          어느 diff 를 쟀나
#     K                몇 판 돌렸나
#     날짜             언제
#     expected.yaml    ⚠️ **함정** — 정답지가 바뀌면 점수가 바뀐다. 근데 이 파일엔
#                      점수를 저장하지 않으므로(README 참조) 여기 박을 필요가 있나?
#
# 📌 M5 에서 같은 종류의 판단을 한 번 했다 (`engine.py` 의 thread_id):
#    *"이름은 PR 정보로 **계산**한다. 저장이 아니라 계산이라 몇 번이든 다시 얻는다."*
#    여기서도 같은 질문이 선다 — 파일명을 **조건에서 계산**할 것인가,
#    아니면 아무 이름이나 주고 조건은 파일 **안에만** 적을 것인가?
#      계산하면: 같은 조건으로 다시 돌리면 같은 파일에 덮인다(재실행이 깨끗하다)
#      안 하면:  실행할 때마다 파일이 는다(이력이 남는다)
#
# ✅ 결정 (2026-08-27) — **조건에서 계산하고 덮어쓴다.**
#
#   결정적 근거: **`evals/runs/` 를 커밋하기로 했으므로 이력은 git 이 갖는다.**
#   덮어써도 잃는 게 없다 — `git log -p evals/runs/<파일>` 이 과거 실행을 다 보여준다.
#   파일명에 타임스탬프를 박는 건 **git 이 이미 하는 일을 파일명으로 또 하는 것**이다.
#   그리고 우리가 비교하려는 건 "어제 vs 오늘"이 아니라 **"프롬프트 A vs B"** 다 —
#   그건 조건이 다르니 파일명이 자동으로 갈린다. **시간축은 애초에 축이 아니었다.**
#   ⚠️ 되돌리는 조건: 같은 조건의 반복 측정을 나란히 봐야 할 일이 생기면
#      파일명에 날짜 한 조각을 붙인다 (비용: 이 함수 한 줄).
#
#   meta 에 넣는 것 / 뺀 것:
#     넣는다  model         바뀌면 옛 결과는 비교 대상이 아니다 (📖 인쇄 219)
#             prompt_source 지금은 base.py 의 M0 유물 하나뿐이지만, M6-4 에서
#                           `backend/prompts/` 로 갈아끼우면 **이 값이 달라진다.**
#                           그때 옛 파일과 새 파일이 구분되게 미리 박아둔다.
#             measured_at   사람이 읽는 용도. 파일명에는 안 들어간다(위 참조)
#             k             몇 판 돌렸나
#     뺐다    expected.yaml 버전 — ⚠️ **함정이다.** 이 파일엔 점수를 저장하지 않으므로
#             (README) 채점은 언제나 `regrade` 가 **그때의 최신 정답지로** 다시 한다.
#             박아두면 "이 파일은 옛 정답지 기준"이라는 **거짓 인상**만 남는다.
#             tag_rule — 아직 축이 아니다. `review_diff()` 가 SYSTEM_PROMPT 를
#             하드코딩해서 지금은 변형을 넣을 구멍이 없다 (M6-4). 없는 축을 미리
#             적으면 "이걸 실험했다"는 오해가 생긴다.
#
# 틀리면 뭐가 깨지나 ───────────────────────────────────────────────────
#   조건을 덜 적으면: 6개월 뒤 파일 두 개를 열고 "이거 같은 조건에서 잰 건가?" 를
#     **답할 수 없다.** 그럼 그 파일들은 데이터가 아니라 쓰레기다.
#   너무 많이 적으면: 안 바뀌는 값이 파일마다 반복되고, 진짜 축이 뭐였는지 흐려진다.
#
# 반환값 계약: `(파일명, meta dict)`. meta 는 저장 파일의 `"meta"` 키에 그대로 들어간다.
# ──────────────────────────────────────────────────────────────────────
PROMPT_SOURCE = "backend/agents/base.py:SYSTEM_PROMPT"  # M6-4 에서 backend/prompts/ 로 바뀐다

# 프롬프트 변형의 짧은 이름. 파일명에 들어가므로 조건이 다르면 파일도 갈린다.
#
# ⚠️ 2026-08-27: 이 슬롯은 원래 안 열려던 것이다 — `review_diff()` 가 SYSTEM_PROMPT 를
#    하드코딩해서 지금은 `orig` 밖에 만들 수 없고, "없는 축을 미리 적으면 이걸 실험했다는
#    오해가 생긴다"고 판단했다. **그런데 15판 이사가 이걸 강제했다.**
#    `scratch/prompt_2x2.json` 의 `no_tag_rule` 셀은 SYSTEM_PROMPT 에서 한 줄을 뺀
#    진짜 다른 프롬프트이고, 슬롯이 없으면 `sample__luna__k3.json` 하나에 충돌한다.
#    → 축이 실제로 존재하는 데이터가 생긴 순간 슬롯을 연다. 저스트-인-타임의 정상 동작이다.
VARIANT_DEFAULT = "orig"


def run_identity(
    fixture: str, k: int, *, variant: str = VARIANT_DEFAULT,
    prompt_source: str = PROMPT_SOURCE, measured_at: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """이 실행의 파일명과 meta 를 만든다. 이름은 조건에서 계산한다 — 저장이 아니라.

    인자로 열어둔 셋(`variant`·`prompt_source`·`measured_at`)은 **과거 데이터를
    옮길 때만** 쓴다. 새 실행은 전부 기본값이다 — 지금 만들 수 있는 프롬프트가
    하나뿐이기 때문이다(M6-4 에서 늘어난다).
    """
    # 모델명의 접두부(gpt-5.6-)는 파일명에서 뺀다. 구분에 기여하지 않는다.
    short_model = MODEL.rsplit("-", 1)[-1]
    name = f"{fixture}__{short_model}__{variant}__k{k}.json"
    meta = {
        "model": MODEL,
        "variant": variant,
        "prompt_source": prompt_source,
        "measured_at": measured_at or date.today().isoformat(),
        "k": k,
    }
    return name, meta


# ══════════════════════════════════════════════════════════════════════
# 아래는 배선 — 판단이 안 갈리는 자리다
# ══════════════════════════════════════════════════════════════════════


def do_run(fixture: str, k: int) -> Path:
    """K판 호출해서 `evals/runs/` 에 저장한다. 채점은 안 한다."""
    diff_text = (FIXTURES_DIR / f"{fixture}.diff").read_text(encoding="utf-8")
    name, meta = run_identity(fixture, k)

    runs: list[dict[str, Any]] = []
    for i in range(1, k + 1):
        status, payload = run_once(diff_text)
        print(f"  판{i}/{k}  {status}")
        runs.append({"status": status, **payload})

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / name
    path.write_text(
        json.dumps({"meta": meta, "fixture": fixture, "runs": runs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n저장: {path.relative_to(ROOT)}  ({len(runs)}판)")
    return path


def _print_table(
    fixture: str, graded: list[tuple[str, RunGrade]], errors: int
) -> None:
    """채점 결과를 표로. 점수는 저장하지 않고 매번 여기서 계산한다.

    분모 규칙 (D7):  ok + refused = n  ·  error 는 n 에서 뺀다.
    """
    for i, (status, g) in enumerate(graded, 1):
        bad = ",".join(f["category"] for f in g.violations)
        mark = "✅" if g.passed else ("🚫" if status == "refused" else "❌")
        print(
            f"  {mark} 판{i:<3} "
            f"catch {sum(g.caught)}/{len(g.caught)}  "
            f"y={[y for _, y in g.labels]}"
            + ("  ← 모델이 거부(findings 0)" if status == "refused" else "")
            + (f"  오탐→ {bad}" if bad else "")
        )

    n = len(graded)
    if not n:
        print("  (채점할 판이 없다)")
        if errors:
            print(f"  ⚠️ 인프라 오류 {errors}판 — 전부 n 에서 빠졌다")
        return
    x = sum(g.passed for _, g in graded)
    lo, hi = wilson_ci(x, n)
    print(f"\n  {fixture}: {x}/{n} = {x / n:.2f}   Wilson 95% [{lo:.2f}, {hi:.2f}]")

    # 거부율은 따로 찍는다 — 성공률 안에 섞이면 "프롬프트를 고쳤더니 거부가 늘었다"가 안 보인다.
    refused = sum(1 for st, _ in graded if st == "refused")
    if refused:
        rlo, rhi = wilson_ci(refused, n)
        print(f"  🚫 거부 {refused}/{n} = {refused / n:.2f}   Wilson 95% [{rlo:.2f}, {rhi:.2f}]")
    if errors:
        print(f"  ⚠️ 인프라 오류 {errors}판 — n 에서 뺐다 (📖 인쇄 219 'API 오류 0건')")

    labels = [(c, y) for _, g in graded for c, y in g.labels]
    scored = [(c, y) for c, y in labels if y != -1]
    if scored:
        brier = sum((c - y) ** 2 for c, y in scored) / len(scored)
        over = sum(1 for c, y in scored if y == 0 and c >= 0.99)
        print(f"  Brier = {brier:.4f}  (라벨 {len(labels)} 중 채점 {len(scored)} · "
              f"보류 {len(labels) - len(scored)})")
        if over:
            print(f"  ⚠️ confidence≥0.99 라고 말했는데 틀린 지적 {over}개 — INV-3 이 위험한 지점")


def do_regrade(path: Path) -> None:
    """저장된 실행을 다시 채점한다. 호출 없음."""
    data = json.loads(path.read_text(encoding="utf-8"))
    fixture = data["fixture"]
    expected = load_expected()

    # meta 전체를 찍으면 note 때문에 표를 못 읽는다. 조건만 한 줄로.
    m = data.get("meta", {})
    cond = " · ".join(
        str(m[k]) for k in ("model", "variant", "prompt_source") if k in m
    )
    when = ", ".join(m.get("spans", [m["measured_at"]] if "measured_at" in m else []))
    print(f"\n{path.name}")
    print(f"  {cond}")
    print(f"  측정 {when}" + (f"  ⚠️ {m['note'][:60]}…" if "note" in m else "") + "\n")
    graded: list[tuple[str, RunGrade]] = []
    errors = 0
    for r in data["runs"]:
        # `findings` 키가 없는 판 = 인프라 오류. 거부는 `findings: []` 를 남기므로 여기 안 걸린다.
        if "findings" not in r:
            errors += 1
            continue
        graded.append((r.get("status", "ok"), grade_run(fixture, r["findings"], expected)))
    _print_table(fixture, graded, errors)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="mode", required=True)

    r = sub.add_parser("run", help="K판 새로 호출한다 (비싸다)")
    r.add_argument("fixture", help="fixtures/<name>.diff 의 <name>")
    r.add_argument("-k", type=int, default=3, help="판 수 (기본 3)")

    g = sub.add_parser("regrade", help="저장된 실행을 다시 채점한다 (공짜)")
    g.add_argument("path", nargs="?", help="생략하면 evals/runs/ 전부")

    a = p.parse_args()
    if a.mode == "run":
        do_regrade(do_run(a.fixture, a.k))
    else:
        targets = [Path(a.path)] if a.path else sorted(RUNS_DIR.glob("*.json"))
        if not targets:
            print(f"채점할 파일이 없다 — {RUNS_DIR.relative_to(ROOT)} 가 비었다.")
        for t in targets:
            do_regrade(t)


if __name__ == "__main__":
    main()
