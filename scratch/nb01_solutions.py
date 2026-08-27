# 노트북 01 TODO(human) 정답 구현 — 검수 전용. 노트북에는 안 들어간다.
# ⚠️ 기본 인자에 Z 를 쓰지 않는다 — 스텁 교체 시점에 Z 가 아직 없을 수 있다.
# ⚠️ np · rng 는 노트북이 먼저 정의한다. 여기서 import 하지 않는다.



def bernoulli_var(p):
    return p * (1 - p)


def wald_ci(x, n, z=1.96):
    ph = x / n
    se = (bernoulli_var(ph) / n) ** 0.5
    return (max(0.0, ph - z * se), min(1.0, ph + z * se))


def wilson_ci(x, n, z=1.96):
    ph = x / n
    a = 1 + z * z / n
    b = -(2 * ph + z * z / n)
    c = ph * ph
    r = sorted(float(v) for v in np.roots([a, b, c]).real)
    return (max(0.0, r[0]), min(1.0, r[1]))


def coverage(ci_fn, p, n, trials=4000):
    xs = rng.binomial(n, p, size=trials)  # noqa: F821 — 노트북이 먼저 정의한다
    hit = 0
    for x in xs:
        lo, hi = ci_fn(int(x), n)
        if lo <= p <= hi:
            hit += 1
    return hit / trials
