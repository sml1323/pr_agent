# 노트북 02 TODO(human) 정답 구현 — 검수 전용. 노트북에는 안 들어간다.
# ⚠️ 기본 인자에 노트북 전역을 쓰지 않는다 — 스텁 교체 시점에 아직 없을 수 있다.
# ⚠️ math · np · rng 는 노트북이 먼저 정의한다. 여기서 import 하지 않는다.


def pass_at_k(p, k):
    return 1 - (1 - p) ** k


def pass_pow_k(p, k):
    return p ** k


def expected_naive(p, n, k):
    return sum(
        math.comb(n, c) * p**c * (1 - p) ** (n - c) * (c / n) ** k  # noqa: F821
        for c in range(n + 1)
    )


def pass_pow_k_hat(c, n, k):
    return math.comb(c, k) / math.comb(n, k)  # noqa: F821


def mc_mean(est_fn, p, n, k, trials=4000):
    cs = rng.binomial(n, p, size=trials)  # noqa: F821 — 노트북이 먼저 정의한다
    return float(np.mean([est_fn(int(c), n, k) for c in cs]))  # noqa: F821
