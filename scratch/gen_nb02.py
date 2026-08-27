"""Notebook 02 생성 — Pass@k vs Pass^k 와 불편추정량. (friction-notebook 스킬로 생성)"""
import json
from pathlib import Path

OUT = Path("/Users/imseungmin/work/llm_study/pr_agent_project/learning/notebooks/02-passk-unbiased.ipynb")
OUT.parent.mkdir(parents=True, exist_ok=True)

C = []
# ⚠️ source 는 **문자열 그대로** 넣는다. list 로 쪼갤 거면 원소마다 "\n" 이 붙어야 한다.
# ⚠️ nbformat_minor=5 는 셀마다 고유 id 를 요구한다 — 없으면 지금은 경고, 곧 하드 에러.
def md(s): C.append({"cell_type": "markdown", "id": f"cell-{len(C)}", "metadata": {},
                     "source": s.strip("\n")})
def code(s): C.append({"cell_type": "code", "id": f"cell-{len(C)}", "execution_count": None,
                       "metadata": {}, "outputs": [], "source": s.strip("\n")})

md(r"""
# 02 · 12판 중 8판 — 다음 PR 4건 연속으로 맞힐 확률은?
""")

md(r"""
## 지금 어디인가 — 전체에서 이 조각까지

```
PR 리뷰 멀티에이전트   ①웹훅 → ②큐 → ③워커 → ④에이전트 4 → ⑤애그리게이터 → ⑥게이트
 └─ M6 — ④⑤ 를 진짜 LLM 으로
     └─ 프롬프트를 고친다 — 프롬프트 엔지니어링 (M6-3)
         └─ 고치기 전에, "나아졌나"를 판정할 자(ruler)부터 세운다 (M6-1)
             └─ 자의 부품 ②: 몇 판 연속으로 되나 — 신뢰성    ← 지금 여기
```

프롬프트를 **만지는 손**과 결과를 **재는 자**는 다른 근육이다. 자가 없으면
"고쳐서 나아졌다"를 판정할 수 없어서 (M6-PLAN §0 — "눈으로 본다"가 성립 안 한다),
M6 는 자부터 만든다. 자(`backend/eval/stats.py`)의 부품은 셋 —
① 비율이 보증하는 범위 (노트북 01) · **② 이 노트북** · ③ 두 프롬프트 비교 (노트북 03).
""")

md(r"""
## 왜 이걸 하나

**① 지금 우리 코드에서 벌어진 일**

같은 diff 를 12판 돌렸다. SQL 인젝션을 **찾기는 12판 전부** 찾았는데,
`severity=critical` 까지 정확히 맞힌 건 **12판 중 8판**이다.
그런데 M6 완료 판정 ②("SQL 인젝션을 critical 로")는 **데모를 한 번 돌려 통과하면 ✅** 였다.

**② 왜 곤란한가**

한 번 성공은 "**할 수 있다**"다. 우리 제1원칙(선별 — *틀린 말을 안 하는 것*)이
요구하는 건 "**매번 된다**"다 — 열 번 중 한 번 헛소리하면 아무도 안 믿는다.

PR 이 4건 연속으로 들어온다면? `8/12 ≈ 0.667` 이니까
"네 번 연속은 `0.667⁴ ≈ 20%`" 라고 암산하고 싶다.
**그런데 이 암산은 체계적으로 낙관적이다.** 얼마나, 왜 낙관인지 말하지 못하면
완료 판정 ② 를 다시 쓸 수 없다 (M6-6).

**③ 그래서 뭘 하고 싶은가**

> 관측(`c/n`)에서 "**k판 연속 성공 확률**"을 **치우침 없이** 추정하고 싶다.

**④ 도구**

`Pass@k` / `Pass^k` (책 인쇄 200) — 그리고 책이 안 주는 것:
**p 를 모를 때** 그냥 거듭제곱하면 왜 위로 뜨는지(젠센 부등식),
대신 무엇을 쓰는지(비복원 추출 불편추정량 `C(c,k)/C(n,k)`).
""")

md(r"""
## 이 노트북이 끝나면

| | |
|---|---|
| ① | `Pass@k` 와 `Pass^k` 가 **각각 무슨 질문에 답하는지** — 직접 구현해서 가른다 |
| ② | 관측 비율(`p̂ = c/n`)을 그냥 거듭제곱하면 **왜 위로 뜨는지** — 뜨는 양을 직접 계산한다 |
| ③ | 불편추정량 `C(c,k)/C(n,k)` 를 구현하고 **편향 0 을 시뮬레이션으로 스스로 확인**한다 |
| ④ | 완료 판정 ② 를 어떻게 다시 써야 하는지(**M6-6**) 근거를 댈 수 있다 |

**안 다루는 것** HumanEval `Pass@k` 추정량의 유도 · 신뢰구간(→ 노트북 01) · 두 프롬프트 비교(→ 노트북 03)
**분량** 코드 셀 8개 · 그중 **`TODO(human)` 4개** — 힌트만 있고 답은 없다

⚠️ **`scipy` 를 일부러 설치하지 않았다.** `scipy.stats.binom.pmf` 가 있으면 §2 가
한 줄로 끝나고, 그게 정확히 없애야 할 추상화다 ([Friction First](https://larsfaye.com)).
`math.comb` 로 직접 조립한다.
""")

md(r"""
## 기호와 말 — 낯설면 여기로 돌아온다

| 기호 | 읽기 | 뜻 |
|---|---|---|
| `p` | 피 | **진짜 성공률** — 우리는 영원히 못 본다 |
| `p̂` | 피 햇 | **관측한 비율** = c/n. 모자(^)는 "데이터로 만든 추정치"라는 표시 |
| `c` | 씨 | 성공한 판 수 (우리 실측: 8) |
| `n` | 엔 | 전체 판 수 (우리 실측: 12) |
| `k` | 케이 | "몇 판 **연속**?"의 그 몇 |
| `E[X]` · 기대값 | 이 엑스 | 무한히 반복했을 때의 평균 |
| `Var` · 분산 | 바르 | 흔들림의 크기 (노트북 01 §1 에서 뜯었다) |
| 추정량 | estimator | **데이터에서 값을 만들어내는 공식.** `p̂^k` 도 `C(c,k)/C(n,k)` 도 추정량이다 |
| 편향 / 불편 | bias / unbiased | 추정량이 평균적으로 참값에서 한쪽으로 **치우침** / 안 치우침 |
| `C(n, k)` | 엔 콤비 케이 | n개에서 k개를 고르는 가짓수 — 코드로는 `math.comb(n, k)` |
""")

md(r"""
---
## 0. 먼저 — 그 숫자를 직접 꺼낸다

위에 적은 `12/12` · `8/12` 를 **손으로 옮겨 적지 않는다.**
실제 실험 결과 파일에서 읽는다. 옮겨 적는 순간 오타가 사실이 된다.
""")

code(r"""
import json, math
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams

# 한글 폰트 (없으면 그냥 넘어간다 — 그래프 라벨만 깨진다)
_avail = {f.name for f in font_manager.fontManager.ttflist}
for _f in ["AppleGothic", "Apple SD Gothic Neo", "NanumGothic", "Malgun Gothic"]:
    if _f in _avail:
        rcParams["font.family"] = _f
        break
rcParams["axes.unicode_minus"] = False
rcParams["figure.dpi"] = 110

ROOT = Path.cwd()
while not (ROOT / "pyproject.toml").exists():
    ROOT = ROOT.parent

d = json.loads((ROOT / "scratch" / "prompt_2x2.json").read_text())
runs = [r for cell_runs in d["cells"].values() for r in cell_runs]

N_RUNS   = len(runs)
C_DETECT = sum(any(f["category"] == "sql-injection" for f in r["findings"]) for r in runs)
C_CRIT   = sum(any(f["category"] == "sql-injection" and f["severity"] == "critical"
                   for f in r["findings"]) for r in runs)
P_HAT    = C_CRIT / N_RUNS

print(f"판 수              n = {N_RUNS}")
print(f"탐지 (존재만)      c = {C_DETECT}/{N_RUNS}")
print(f"critical 정확      c = {C_CRIT}/{N_RUNS}   ← 이 노트북의 주인공")
print(f"                  p̂ = {P_HAT:.4f}")
""")

md(r"""
---
## 1. 같은 질문이 두 개다 — 각 항을 뜯는다

$$Pass@k = 1 - (1-p)^k \qquad\qquad Pass^k = p^k$$

| | 답하는 질문 | 쓰는 곳 |
|---|---|---|
| **Pass@k** | k번 중 **하나라도** 성공 — "이 일을 **할 수 있는가**" | 능력의 상한 |
| **Pass^k** | k번 **전부** 성공 — "**안정적으로 신뢰할 수 있는가**" | 운영 신뢰성 |

조각별로 뜯는다.

### ① `p^k` — 징검다리

k칸 징검다리를 **한 칸도 안 빠지고** 건널 확률. 곱셈 규칙 — **판이 독립일 때만** 성립한다.
`p=0.9` 처럼 좋아 보여도 `k=10` 이면 `0.9¹⁰ ≈ 0.35` — **연속 성공은 지수적으로 어렵다.**

### ② `(1−p)^k` — 전부 실패

"하나라도 성공"은 직접 세기 어렵다 — 성공이 1번, 2번, … k번인 경우를 전부 더해야 한다.
**여사건**이 지름길이다: "하나라도 성공"의 반대는 "**전부 실패**" 딱 하나다.

### ③ `1 − …` — 여사건을 다시 뒤집어 원래 질문으로 돌아온다

📌 **잠깐 기억해 둘 것 — 이 공식들의 `p` 는 참값이다.**
우리 손에 있는 건 12판에서 잰 `p̂` 뿐이고, 12판을 다시 돌리면 다른 값이 나온다.
**흔들리는 수**를 이 공식에 넣어도 되는가 — 그게 §2 다.
""")

code(r"""
# ─────────────────────────────────────────────────────────────
# TODO(human) ① 두 공식 — 참 p 를 알 때
#
# pass_at_k(p, k):  k번 중 하나라도 성공할 확률
# pass_pow_k(p, k): k번 전부 성공할 확률
#
# 힌트: pass_pow_k 는 곱셈 규칙 한 줄.
#       pass_at_k 는 직접 더하지 말고 여사건("전부 실패")을 1에서 뺀다.
#
# 틀리면: 아래 출력에서 책(인쇄 200)의 예시 p=0.6, k=5 가
#         Pass@5 ≈ 0.990 / Pass^5 ≈ 0.078 로 안 나온다.
#
# 채우기 전: 이 셀은 TypeError 로 멈춘다 (None 을 숫자 포맷하려다) —
#           오류가 아니라 빈칸이 비어 있다는 신호다. 채우면 사라진다.
# ─────────────────────────────────────────────────────────────
def pass_at_k(p, k):
    ...


def pass_pow_k(p, k):
    ...


print(f"책 검산  p=0.6, k=5 →  Pass@5 {pass_at_k(0.6, 5):.3f} (≈0.990?)   "
      f"Pass^5 {pass_pow_k(0.6, 5):.3f} (≈0.078?)")

ks = np.arange(1, 13)
plt.figure(figsize=(6.5, 3.6))
plt.plot(ks, [pass_at_k(P_HAT, k) for k in ks], "o-", label="Pass@k — 하나라도")
plt.plot(ks, [pass_pow_k(P_HAT, k) for k in ks], "s-", label="Pass^k — 전부")
plt.axvline(4, ls=":", c="gray")
plt.title(f"같은 관측 비율 {P_HAT:.3f}, 정반대 곡선")
plt.xlabel("k"); plt.ylabel("확률"); plt.legend(); plt.grid(alpha=0.25)
plt.tight_layout(); plt.show()

print(f"우리 숫자  k=4 →  Pass@4 {pass_at_k(P_HAT, 4):.3f}   Pass^4 {pass_pow_k(P_HAT, 4):.3f}")
""")

md(r"""
**⬆︎ 그래프를 보고 답할 것** (실행한 뒤, 다음으로 넘어가기 전에):

- 두 곡선이 `k=1` 에서 만나는 **이유**를 식으로 말할 수 있나?
- 완료 판정 ② ("데모 한 번 돌려 통과하면 ✅")는 **어느 곡선**을 재고 있었나?
""")

md(r"""
---
## 2. 순진한 방법 — 흔들리는 수를 거듭제곱하면

방금 `k=4` 에서 `Pass^4 ≈ 0.198` 이라고 읽었다. 그런데 그 계산은
**`p` 자리에 `p̂` 를 꽂은 것**이다 — §1 에서 심어둔 그 문제.

무슨 일이 생기는지는 `k=2` 로 줄이면 **노트북 01 의 그 항등식**이 그대로 답한다:

$$E[\hat{p}^2] = (E[\hat{p}])^2 + Var(\hat{p}) = p^2 + Var(\hat{p})$$

**제곱의 평균은 평균의 제곱보다 분산만큼 크다.** `p̂` 자체는 불편(`E[p̂]=p`)인데,
`p̂²` 는 벌써 **분산만큼 위로 뜬다.** 일반화가 **젠센 부등식**이다 —
`x ↦ x^k` 곡선이 **아래로 볼록**(아래로 처진 모양)이라, 흔들리는 입력을 넣으면
출력의 평균이 위로 뜬다: `E[p̂^k] ≥ p^k`.
**거듭제곱은 신뢰성을 체계적으로 과대평가한다.**

말은 그렇다 치고 — **얼마나 뜨는지 직접 계산해 본다.**
성공 판 수 `c` 가 가질 수 있는 값은 `0..n` 의 n+1개뿐이라, 기대값을 **전부 더해서
정확히** 구할 수 있다.
""")

code(r"""
# ─────────────────────────────────────────────────────────────
# TODO(human) ② E[p̂^k] 를 정확히 — 순진한 추정량의 기대값
#
# 참 성공률 p, 판 수 n 일 때:
#     E[p̂^k] = Σ_c  P(성공이 c판) · (c/n)^k        (c = 0 … n)
#
# 접근 후보 둘 — 여기선 (a):
#   (a) 해석적 합 — P(성공이 c판) 을 math.comb 로 조립해 n+1 항을 더한다
#   (b) 몬테카를로 — 가짜 12판을 수천 번 만들어 평균
#   기준: 편향을 소수 4자리까지 봐야 하는데 (b)는 잡음이 섞인다.
#   (b)는 §4 에서 어차피 만든다 — 그때 (a)와 맞는지 대조하는 게 이 노트북의 재미다.
#
# 힌트: P(성공이 c판) = "n판 중 c판을 고르는 가짓수" × "그 배치 하나의 확률".
#       가짓수는 math.comb(n, c). 배치 하나의 확률은 성공 c번·실패 n−c번의 곱.
#
# 틀리면: 아래 첫 줄(확률의 합)이 1.000000 이 안 나온다.
#         둘째 줄(k=1)이 p 와 안 맞는다 — 평균 자체는 불편이어야 한다.
# ─────────────────────────────────────────────────────────────
def expected_naive(p, n, k):
    ...


P_TRUE = C_CRIT / N_RUNS   # 사고 실험: 참 p 가 정확히 우리 p̂ 값인 세상을 가정한다

# k=0 이면 (c/n)^0 = 1 이라, 이 합은 그냥 "확률의 총합"이 된다 — 공짜 검산
print(f"확률 합 검산   Σ P(c)  = {expected_naive(P_TRUE, N_RUNS, 0):.6f}   ← 1.000000 이어야 한다")
print(f"k=1 검산       E[p̂]   = {expected_naive(P_TRUE, N_RUNS, 1):.6f}   ← p={P_TRUE:.6f} 그대로여야 한다")
print()
for k in [2, 3, 5, 8]:
    truth = pass_pow_k(P_TRUE, k)
    naive_mean = expected_naive(P_TRUE, N_RUNS, k)
    print(f"k={k}:   참 p^k = {truth:.4f}    E[p̂^k] = {naive_mean:.4f}    위로 +{naive_mean - truth:.4f}")
""")

md(r"""
**⬆︎ 위 표에서 무엇이 보이나?**

`p̂` 는 불편인데(둘째 줄), **거듭제곱하는 순간 전부 위로 뜬다.**
판을 아무리 다시 돌려도 사라지지 않는 **체계적 낙관**이다 — 평균을 내도 그대로다.
절대량은 작아 보여도, `k` 가 커지면 참값 자체가 지수적으로 작아져서
**비율로는 몇 배 규모**가 된다 (§5 에서 확인).

그럼 어떻게 해야 하나 → §3.
""")

md(r"""
---
## 3. 제대로 된 방법 — 비복원으로 뽑는다

발상의 전환: "다음 k판"을 미래에서 찾지 말고, **이미 가진 n판 안에서** 찾는다.

> n판 중 k판을 **비복원으로**(한 번 뽑은 판은 다시 안 뽑고) 뽑았을 때,
> **전부 성공일 확률**은 얼마인가?

전부 성공이려면 **성공했던 c판 안에서만** 골라야 한다:

$$\widehat{pass^k} = \frac{C(c, k)}{C(n, k)}$$

**이게 불편인 이유**: 판들이 교환가능(순서를 바꿔도 분포가 같음)하므로,
"아무 k판이 전부 성공"의 기대값은 "앞의 k판이 전부 성공"의 확률 — 정확히 `p^k` 다.
HumanEval 의 `Pass@k` 추정량 `1 − C(n−c,k)/C(n,k)` 와 같은 계열이다.

믿기지 않으면 좋다 — **§4 에서 직접 세어본다.**
""")

code(r"""
# ─────────────────────────────────────────────────────────────
# TODO(human) ③ 불편추정량
#
# n판 중 c판 성공을 관측했을 때, "k판 연속 성공 확률"의 불편추정량.
#
# 힌트: "n판에서 k판을 뽑는 전체 가짓수" 분의
#       "성공했던 c판 안에서만 k판을 뽑는 가짓수". math.comb 두 번이면 끝난다.
#       k > c 일 때 math.comb 가 알아서 0 을 돌려준다 — 그 0 이 무슨 뜻인지
#       한 줄로 말해볼 것 (§5 에서 다시 만난다).
#
# 틀리면: 다음 셀의 성질 검산 assert 가 터진다.
# ─────────────────────────────────────────────────────────────
def pass_pow_k_hat(c, n, k):
    ...


print(f"{'k':>3}  {'p̂^k (지름길)':>14}  {'C(c,k)/C(n,k)':>16}")
for k in [1, 2, 3, 4, 5, 8]:
    print(f"{k:>3}  {pass_pow_k(P_HAT, k):>14.4f}  {pass_pow_k_hat(C_CRIT, N_RUNS, k):>16.4f}")
""")

code(r"""
# ── 검산 — 답을 안 알려주고 성질만 확인한다 ────────────────────
EPS = 1e-9   # 부동소수점 허용오차 — 수학이 아니라 float 의 문제 (노트북 01 §3 참조)

c, n = C_CRIT, N_RUNS

# k=1 이면 그냥 관측 비율이어야 한다
assert abs(pass_pow_k_hat(c, n, 1) - c / n) < EPS,  "k=1 인데 c/n 이 아니다"

prev = 1.0
for k in range(1, n + 1):
    v = pass_pow_k_hat(c, n, k)
    assert -EPS <= v <= 1 + EPS,                     f"확률 범위 밖: k={k}, {v}"
    assert v <= pass_pow_k(c / n, k) + EPS,          f"지름길 p̂^k 보다 크다: k={k}"
    assert v <= prev + EPS,                          f"k 가 늘었는데 커졌다: k={k}"
    prev = v

# 경계: 전승이면 1, 관측한 성공 수를 넘는 연속은 보증하지 않는다
assert abs(pass_pow_k_hat(5, 5, 5) - 1.0) < EPS,    "전승인데 1 이 아니다"
assert pass_pow_k_hat(c, n, c + 1) < EPS,           "k > c 인데 0 이 아니다"

print("✅ 통과. 그런데 '불편'인지는 아직 아무도 확인 안 했다 — §4 가 진짜 시험이다.")
""")

md(r"""
---
## 4. 진짜 시험 — "불편"이라는 주장을 직접 센다

불편(unbiased)의 정의: **실험을 무한히 반복하면 추정값의 평균이 참값에 붙는다.**
정의를 그대로 실험으로 옮긴다:

> 참 `p` 를 **우리가 정해놓고**, 가짜 12판을 수천 번 만든다.
> 매번 두 추정량(지름길 `p̂^k` · 불편 `C(c,k)/C(n,k)`)을 계산해 평균낸다.
> 참 `p^k` 에서 얼마나 벗어났는지(**편향**)를 그린다.

그리고 §2 의 해석적 계산과 이 몬테카를로가 **서로 맞는지도 대조한다** —
독립적인 두 방법이 같은 답을 내면, 책도 Claude 도 아닌
**내 두 구현이 서로를 검증**한 것이다.
""")

code(r"""
rng = np.random.default_rng(20260825)  # 시드 고정 — 다시 돌려도 같은 그림

# ─────────────────────────────────────────────────────────────
# TODO(human) ④ 추정량의 평균을 시뮬레이션으로
#
# 참 성공률 p 로 n판짜리 실험을 trials 번 반복해,
# est_fn(c, n, k) 값들의 평균을 돌려준다.
#
# 힌트: rng.binomial(n, p, size=trials)  ← "성공 판 수" 배열이 한 번에 나온다
#       각 c 마다 est_fn(int(c), n, k) 를 구해 평균낸다 (np.mean)
#
# 틀리면: 아래 그래프에서 불편추정량(주황)의 편향이 0 근처에 안 붙거나,
#         지름길(파란 점)이 §2 해석적 곡선(점선)에서 벗어난다.
# ─────────────────────────────────────────────────────────────
def mc_mean(est_fn, p, n, k, trials=4000):
    ...


naive    = lambda c, n, k: pass_pow_k(c / n, k)   # 지름길: p̂ 를 그냥 꽂는다
unbiased = pass_pow_k_hat

ks = np.arange(1, 9)
bias_naive_mc = [mc_mean(naive,    P_TRUE, N_RUNS, k) - pass_pow_k(P_TRUE, k) for k in ks]
bias_unb_mc   = [mc_mean(unbiased, P_TRUE, N_RUNS, k) - pass_pow_k(P_TRUE, k) for k in ks]
bias_naive_an = [expected_naive(P_TRUE, N_RUNS, k)    - pass_pow_k(P_TRUE, k) for k in ks]

plt.figure(figsize=(7, 3.8))
plt.plot(ks, bias_naive_mc, "o",  label="지름길 (c/n)^k — 몬테카를로")
plt.plot(ks, bias_naive_an, "--", c="tab:blue",   label="지름길 (c/n)^k — §2 해석적 (대조)")
plt.plot(ks, bias_unb_mc,   "s-", c="tab:orange", label="불편추정량 — 몬테카를로")
plt.axhline(0, c="k", lw=1)
plt.title(f"편향 = 추정량의 평균 - 참 p^k   (참 p={P_TRUE:.3f}, n={N_RUNS})")
plt.xlabel("k"); plt.ylabel("편향"); plt.legend(); plt.grid(alpha=0.25)
plt.tight_layout(); plt.show()
""")

md(r"""
**⬆︎ 그래프를 읽을 것.** 예상 결과:

- **파란 점이 파란 점선 위에 얹힌다** — 몬테카를로(§4)와 해석적 합(§2)이 일치.
  서로 독립인 내 두 구현이 **서로를 검증**했다.
- **주황이 0 에 붙는다** — "불편"이라는 주장이 실험으로 확인됐다.
  정확히 0 이 아니라 0 주변에서 떠는 건 버그가 아니다 — 몬테카를로 잡음이고,
  `trials` 를 늘리면 줄어든다 (§4.5 에서 직접 확인).
""")

md(r"""
---
## 4.5 🎛 샌드박스 — 손잡이를 직접 돌린다

구현은 끝났다. 여기서 묻는 건 "만들 수 있나"가 아니라 **"감이 있나"** 다.
어느 파라미터가 편향을 키우고 죽이는지는 표로 읽어선 안 남는다 — 직접 돌려야 남는다.

🖐 **바꾸기 전에 예측할 것** — 답을 적고 나서 실행한다. 틀리는 경험이 저장 강도를 만든다.

1. `N_SB` 를 12 → 100 으로 올리면 지름길 `p̂^k` 의 편향은?
   (a) 그대로 (b) 거의 사라진다 (c) 더 커진다 · **왜 그렇게 생각했나 한 줄**
2. `P_SB` 를 2/3 → 0.95 로 올리면(모델이 아주 잘하는 세상) 편향은?
   (a) 커진다 (b) 작아진다 — 힌트: §2 에서 편향의 정체는 `p̂` 의 **분산**이었다.
   분산이 언제 큰지는 **노트북 01 §1 의 그래프**가 이미 답했다
3. `TRIALS_SB` 를 4000 → 200 으로 줄이면, 그래프에서 **무엇과 무엇이** 구분이 안 되나?
""")

code(r"""
# ═══ 손잡이 — 여기만 바꿔가며 다시 실행해 볼 것 ═══
P_SB      = 2 / 3   # 참 성공률.   후보: 0.5 / 2/3 / 0.9 / 0.95     # 원래: 2/3 (우리 p̂)
N_SB      = 12      # 판 수.       후보: 3 / 12 / 30 / 100          # 원래: 12 (우리 실측)
K_MAX_SB  = 8       # k 범위.      후보: 4 / 8 / 12                 # 원래: 8
TRIALS_SB = 4000    # 반복 횟수.   후보: 200 / 4000 / 50000         # 원래: 4000

# 손잡이마다 보이는 것:
#   P_SB      — 편향의 원료는 p̂ 의 분산. p 가 경계(0/1)로 가면 분산이 준다 (노트북 01 §1)
#   N_SB      — 지름길이 언제 괜찮아지나. 책이 p̂^k 를 그냥 주는 건 어느 세상 얘기인가
#   K_MAX_SB  — 편향의 "비율"이 k 에 따라 어떻게 커지나 (아래 두 번째 출력)
#   TRIALS_SB — 비용 대 정밀도. 줄이면 편향(신호)과 몬테카를로 잡음이 구분 안 된다

ks_sb  = np.arange(1, K_MAX_SB + 1)
b_shortcut = [mc_mean(naive,    P_SB, N_SB, k, TRIALS_SB) - pass_pow_k(P_SB, k) for k in ks_sb]
b_unbiased = [mc_mean(unbiased, P_SB, N_SB, k, TRIALS_SB) - pass_pow_k(P_SB, k) for k in ks_sb]

plt.figure(figsize=(7, 3.6))
plt.plot(ks_sb, b_shortcut, "o-", label="지름길 (c/n)^k")
plt.plot(ks_sb, b_unbiased, "s-", label="불편추정량")
plt.axhline(0, c="k", lw=1)
plt.title(f"편향   p={P_SB:.3f} · n={N_SB} · {TRIALS_SB}회")
plt.xlabel("k"); plt.ylabel("편향"); plt.legend(); plt.grid(alpha=0.25)
plt.tight_layout(); plt.show()

print("k별 과대 배율 —  E[지름길] / 참 p^k :")
for k in ks_sb:
    ratio = expected_naive(P_SB, N_SB, k) / pass_pow_k(P_SB, k)
    print(f"  k={k}:  {ratio:.2f}배")
""")

md(r"""
---
## 5. 그래서 우리 결정

우리 실측(`c=8, n=12`)으로 완료 판정을 다시 읽는다.
""")

code(r"""
print(f"실측  c={C_CRIT}, n={N_RUNS}  (critical 정확 기준)\n")
print(f"{'k':>3}  {'p̂^k (책의 지름길)':>18}  {'불편추정량':>10}  {'과대':>8}")
for k in [3, 5, 8]:
    shortcut = pass_pow_k(P_HAT, k)
    unb      = pass_pow_k_hat(C_CRIT, N_RUNS, k)
    print(f"{k:>3}  {shortcut:>18.4f}  {unb:>10.4f}  {shortcut / unb:>7.1f}배")

print()
print(f"완료 판정 ② 가 재던 것:   Pass@1  = {pass_at_k(P_HAT, 1):.3f}")
print(f"제1원칙이 묻는 것:        pass^4  = {pass_pow_k_hat(C_CRIT, N_RUNS, 4):.3f}")

# c 를 무엇으로 세느냐에 따라 이야기가 통째로 달라진다 — D1 이 먼저인 이유
print()
print(f"c 를 탐지(존재만)로 세면:   pass^4 = {pass_pow_k_hat(C_DETECT, N_RUNS, 4):.3f}")
print(f"c 를 critical 정확으로:     pass^4 = {pass_pow_k_hat(C_CRIT,   N_RUNS, 4):.3f}")
""")

md(r"""
### 판정

| | 책의 지름길로 읽으면 | 불편추정량으로 읽으면 |
|---|---|---|
| "PR 8건 연속으로 정확" | 3.9% | **0.2% — 19배 낙관이었다** |

완료 판정 ② ("SQL 인젝션을 critical 로", 데모 1회)는 **Pass@1 을 재고 있었다.**
제1원칙("틀린 말을 안 하는 것")이 묻는 건 **Pass^k** 다 — M6-6 에서 판정을 다시 쓸 때
이 노트북의 추정량이 자가 된다 (`backend/eval/stats.py`, M6-1).

⚠️ **함정 둘** — 방향이 반대라서 더 위험하다:

1. **여러 픽스처를 합칠 때** 합산 `p̄` 를 거듭제곱하면 이번엔 **과소**평가다
   (픽스처마다 p 가 다르면 같은 젠센이 반대로 작동).
   → **픽스처별로 먼저 계산하고 평균낸다. 절대 반대로 하지 않는다.**
2. **"판(trial)"의 경계가 아직 정의 안 됐다** — 실측 12판은 에이전트 1회 호출의
   반복이고, 완료 판정 대상은 ④⑤ 파이프라인 전체다. k 를 보고할 땐 어느 쪽인지
   명시한다 (책 인쇄 200 도 같은 걸 요구한다).

그리고 위 마지막 출력 — **c 를 무엇으로 세느냐로 `pass^4` 가 몇 배 달라졌다.**
완료 판정의 단위를 정하는 **D1** 이 통계보다 먼저인 이유다.
""")

md(r"""
---
## 6. 자가 점검

읽고 넘어가지 말고 **실제로 답해볼 것.** 못 하는 항목이 이 노트북에서 안 배워진 부분이다.

- [ ] `Pass@k` 와 `Pass^k` 가 각각 **무슨 질문**에 답하는지 한 문장씩 말할 수 있나
- [ ] `p̂^k` 가 위로 뜨는 이유를 **분산/볼록성**으로 설명할 수 있나 (`k=2` 항등식부터)
- [ ] `C(c,k)/C(n,k)` 가 왜 불편인지 — **비복원**과 **교환가능**이 어디에 쓰였는지 말할 수 있나
- [ ] `k > c` 에서 추정량이 0 이 되는 게 **무슨 뜻**인지 말할 수 있나
- [ ] 픽스처 여러 개를 합칠 때의 순서(개별 먼저 vs 합산 먼저)와 **이유**를 말할 수 있나
- [ ] 이 노트북을 **Claude 없이 다시 만들 수 있나**

### 다음

1. `learning/NOTEBOOK.md` 에 **내 말로 3줄** — 이 노트북을 다시 열지 말고
2. `backend/eval/stats.py` 에 `pass_pow_k_hat` 을 옮긴다 (**M6-1**)
3. 노트북 03 — McNemar 와 다중 비교 (아무것도 안 고쳐도 이기는 게 나온다)

> 📖 근거 문서: [`docs/M6-PLAN.md`](../../docs/M6-PLAN.md) §M6-1 ② ·
> [`learning/reference/eval-statistics.html`](../reference/eval-statistics.html) ②
""")

nb = {"cells": C, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
      "name": "python3"}, "language_info": {"name": "python", "version": "3.13"}},
      "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1))
print(f"→ {OUT}  ({len(C)} cells)")
