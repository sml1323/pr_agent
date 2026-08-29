"""`evals/stats.py` — 알려진 값과 대조한다.

왜 있나 ───────────────────────────────────────────────────────────────
2026-08-28 적대적 검증이 지적했다: *"새 함수 셋이 전부 미사용 · 자동 테스트 0 —
✅ 판정을 지탱하는 건 일회성 수동 재현뿐"*. 맞는 말이다.
그리고 같은 검증이 **주석의 숫자 하나가 틀린 것**을 잡았다(`19.3배`) —
손으로 한 번 돌려보고 넘어가면 그런 게 남는다.

⚠️ **`tests/test_webhook.py` 와 성격이 다르다.** 저건 *"구현한 쪽이 자기 시험지를 만들면
자기가 답할 수 있는 문제만 낸다"* 는 이유로 **사람이 쓰기로 미뤄둔 것**이고
(`CURRENT.md`), 여기는 **설계 판단이 아니라 수학**이다. `C(8,3)/C(12,3)` 의 답은
누가 쓰든 같고, 시험지를 만든 사람의 맹점이 들어갈 자리가 없다.
→ 그래서 이건 Claude 가 써도 되는 쪽이다. **판단이 있는 곳에만 TODO(human) 을 둔다.**

무엇을 안 재나 ───────────────────────────────────────────────────────
"이 값이 우리 결정에 쓸모 있나"는 안 잰다 — 그건 `evals/grader.py` 와
`scripts/eval_prompt.py` 의 일이고, 여기는 **공식이 공식대로 도나**만 본다.
"""

import math

import pytest

from evals.stats import mcnemar_exact, min_two_sided_p, pass_pow_k_hat, wilson_ci

# ══════════════════════════════════════════════════════════════════════
# wilson_ci — 비율의 신뢰구간
# ══════════════════════════════════════════════════════════════════════


def test_wilson_은_경계에서_폭이_0_이_아니다():
    """이 함수가 Wald 대신 존재하는 유일한 이유. 실패하면 Wald 로 퇴화한 것이다."""
    lo, hi = wilson_ci(0, 3)
    assert lo == 0.0
    assert hi > 0.5, f"0/3 의 상한이 {hi} — Wald 면 0.0 이다"

    lo, hi = wilson_ci(12, 12)
    assert lo < 0.8, f"12/12 의 하한이 {lo} — Wald 면 1.0 이다"
    assert hi == pytest.approx(1.0)


def test_wilson_은_M6_PLAN_표를_재현한다():
    """`docs/M6-PLAN.md` §M6-1 ①의 표. 여기가 어긋나면 그 문서가 거짓말이 된다."""
    assert wilson_ci(12, 12) == pytest.approx((0.757, 1.000), abs=0.002)
    assert wilson_ci(0, 3) == pytest.approx((0.000, 0.562), abs=0.002)
    assert wilson_ci(8, 12) == pytest.approx((0.391, 0.862), abs=0.002)


def test_wilson_은_구간을_벗어난_입력을_거부한다():
    """음수나 n 초과면 판별식이 음수가 되어 **복소근**이 나온다 —
    그걸 실수처럼 정렬하면 뒤집힌 구간이 조용히 표에 찍힌다."""
    with pytest.raises(ValueError):
        wilson_ci(13, 12)
    with pytest.raises(ValueError):
        wilson_ci(-1, 12)
    with pytest.raises(ValueError):
        wilson_ci(0, 0)


# ══════════════════════════════════════════════════════════════════════
# pass_pow_k_hat — k판 연속 성공의 불편추정량
# ══════════════════════════════════════════════════════════════════════


def test_passk_는_k1_에서_그냥_비율이다():
    """C(c,1)/C(n,1) = c/n. 여기가 틀리면 조합 계산이 뒤집힌 것이다."""
    assert pass_pow_k_hat(8, 12, 1) == pytest.approx(8 / 12)


def test_passk_는_성공_판보다_큰_k_에서_0_이다():
    """0 은 "불가능"이 아니라 **"근거 없음"** 이다 — 8판 성공에서 9연속을 본 적이 없다."""
    assert pass_pow_k_hat(8, 12, 9) == 0.0


def test_passk_는_M6_PLAN_표를_재현한다():
    """`docs/M6-PLAN.md` §M6-1 ②의 표 (c=8, n=12)."""
    assert pass_pow_k_hat(8, 12, 3) == pytest.approx(0.2545, abs=0.0002)
    assert pass_pow_k_hat(8, 12, 5) == pytest.approx(0.0707, abs=0.0002)
    assert pass_pow_k_hat(8, 12, 8) == pytest.approx(0.0020, abs=0.0002)


def test_passk_는_정말_불편이다():
    """**이 테스트가 이 함수의 존재 이유다.**

    참 p 를 알고 있다고 두고, n판짜리 실험의 **모든 결과에 확률을 곱해** 평균을 낸다.
    몬테카를로가 아니라 해석적 합이라 잡음이 0 이고, 편향을 소수 12자리까지 본다.

    ⚠️ 같은 계산이 **지름길(p̂^k)의 편향도** 드러낸다 — 그게 0 이 아님을 같이 확인한다.
    안 그러면 "둘 다 0 이라 통과"인지 "불편만 0 이라 통과"인지 구분이 안 된다.
    """
    n, k = 12, 3
    p = 8 / 12

    def prob(c: int) -> float:
        return math.comb(n, c) * p**c * (1 - p) ** (n - c)

    truth = p**k
    e_unbiased = sum(prob(c) * pass_pow_k_hat(c, n, k) for c in range(n + 1))
    e_shortcut = sum(prob(c) * (c / n) ** k for c in range(n + 1))

    assert e_unbiased == pytest.approx(truth, abs=1e-12), "불편추정량의 편향이 0이 아니다"
    assert e_shortcut > truth + 0.01, "지름길이 위로 안 뜬다 — 비교 대상이 안 된다"


def test_passk_는_말이_안_되는_입력을_거부한다():
    with pytest.raises(ValueError):
        pass_pow_k_hat(13, 12, 3)  # 성공이 판 수보다 많다
    with pytest.raises(ValueError):
        pass_pow_k_hat(8, 12, 13)  # 판 수보다 큰 k — 없는 관측을 묻는다
    with pytest.raises(ValueError):
        pass_pow_k_hat(8, 12, 0)


# ══════════════════════════════════════════════════════════════════════
# mcnemar_exact — 짝지은 비교
# ══════════════════════════════════════════════════════════════════════


def test_mcnemar_는_손으로_센_값과_같다():
    """n_d 개를 동전으로 두고 양측 꼬리를 직접 세면 나오는 값들."""
    assert mcnemar_exact(0, 6) == pytest.approx(2 * (1 / 64))  # 0.03125
    assert mcnemar_exact(6, 0) == pytest.approx(2 * (1 / 64))  # 대칭이어야 한다
    assert mcnemar_exact(1, 5) == pytest.approx(2 * (1 + 6) / 64)  # 0.21875
    assert mcnemar_exact(3, 3) == pytest.approx(1.0)  # 완전 무승부


def test_mcnemar_는_불일치가_없으면_1_이다():
    """두 설정이 모든 짝에서 같게 굴었다 = 다르다는 증거가 0."""
    assert mcnemar_exact(0, 0) == 1.0


def test_mcnemar_는_음수를_거부한다():
    """`b=-1, c=1` 이면 n_d=0 검사를 비껴가고 **p=0.0(최대 유의)** 이 조용히 나온다."""
    with pytest.raises(ValueError):
        mcnemar_exact(-1, 1)


def test_사전검사가_M6_PLAN_의_경계를_재현한다():
    """**이 표가 M6-3b 의 실행 여부를 정한다.**

    `docs/M6-PLAN.md` §M6-1 ③: *"n_d < 6 이면 검정을 돌리지 마라. 돌려도 답이 정해져 있다."*
    """
    assert min_two_sided_p(3) == pytest.approx(0.250)
    assert min_two_sided_p(5) == pytest.approx(0.0625)
    assert min_two_sided_p(6) == pytest.approx(0.03125)
    # 6 부터 α=0.05 를 넘길 수 있고 5 는 못 넘긴다 — 그게 경계다
    assert min_two_sided_p(5) > 0.05 >= min_two_sided_p(6)


def test_사전검사는_진짜_최솟값이다():
    """`min_two_sided_p(n_d)` 가 `mcnemar_exact(n_d, 0)` 인 게 **최솟값이라는 근거**.

    n_d 를 고정하고 (b, c) 를 전부 훑어 더 작은 p 가 없는지 확인한다.
    """
    for n_d in range(1, 13):
        floor = min_two_sided_p(n_d)
        for b in range(n_d + 1):
            assert mcnemar_exact(b, n_d - b) >= floor - 1e-12
