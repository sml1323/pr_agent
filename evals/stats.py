"""비율(proportion)의 신뢰구간.

노트북 01 (learning/notebooks/01-wilson-vs-wald.ipynb) 에서 만든 것을 옮긴다.

왜 Wilson 인가 — Wald 는 표준오차의 분모에 참값 p 대신 관측값 p̂ 를 넣는
지름길을 친다. p̂ 가 0 이나 1 이면 p̂(1−p̂)=0 → SE=0 → 구간의 폭이 0 이 된다.
"3판 중 0판이니 오탐률은 정확히 0%" 라고 말하게 되는 것이다.
우리 실측 n 은 3~12 이고 오탐률의 참값은 0 근처이므로, 그 사고가 자주 난다.
"""

import numpy as np

# 표준정규분포에서 가운데 95% 를 담는 폭.
# 정책 상수가 아니라 측정 관례다 — 게이트 임계값(M8)과 섞지 말 것.
Z95 = 1.96


def wilson_ci(x: int, n: int, z: float = Z95) -> tuple[float, float]:
    """x 번 성공 / n 번 시도 → (하한, 상한).

    두 근 사이가 구간이다:
        (1 + z²/n)·p²  −  (2p̂ + z²/n)·p  +  p̂²  ≤  0
    """

    if n <= 0:
        raise ValueError(f"{n} 값이 0 이하 입니다.")

    p_hat = x / n
    a = 1 + z**2 / n
    b = -(2 * p_hat + z**2 / n)
    c = p_hat**2
    roots = np.roots([a, b, c])
    lo, hi = sorted(roots)
    lo = max(0.0, float(lo))
    hi = min(1.0, float(hi))

    return lo, hi
