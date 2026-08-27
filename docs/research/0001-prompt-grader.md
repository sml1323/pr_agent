# 프롬프트를 고칠 때 "좋아졌나"를 재는 자 — 1차 출처 조사

**조사일** 2026-08-25 · **범위** M6 진입 직전, `backend/agents/base.py` 의 SYSTEM_PROMPT 를 4개로 가르기 전
**실측 근거** `scratch/prompt_variance.json` (n=12) · `scratch/prompt_2x2.json` (2×2×3판)
**한 줄** 판정의 단위를 "통과/실패"에서 **"픽스처당 성공률 + 구간(interval)"** 으로 바꾼다.

---

## 결론 먼저

| # | 질문 | 답 | 근거 상태 |
|---|---|---|---|
| 1 | 확률적 출력을 어떻게 판정하나 | k/n 을 **Wilson 구간**으로 바꾸고, "k판 전부 성공"이 필요하면 **pass^k 불편추정량**으로 확률을 계산한다. n 은 용도에 따라 2단으로 (순위 비교용 3판 / 비율 자체를 믿을 자리 40판) | **확정** (1차 출처 축자 확인) |
| 2 | 비대칭 비용을 어떻게 넣나 | 지표를 바꾸는 게 아니라 **채점 단위를 바꾼다** — Google 의 "effective false positive"(맞는 지적이어도 행동을 못 얻으면 오탐) + **자동화 경로가 셀수록 오탐 기준이 빡세지는 계단식 기준** | **확정** |
| 3 | severity 인접 등급을 봐주나 | **표준 없음.** 가중 카테고리(Dirichlet) 기계는 있지만 가중치는 분석자가 정하는 정책이다 | **답 없음 → 우리 결정** |
| 4 | LLM-as-judge 는 언제부터 | **검증을 통과한 1차 출처 0건.** 추측으로 채우지 않는다 | **답 없음** |
| 5 | 최소 구현 | 파일 3개(`fixtures/expected.yaml` · `eval/runner.py` · `eval/grade.py`), 함수 6개. **"통과"라는 단어를 안 쓰는 게 요점** | 파생 설계 (출처가 형태를 규정하지 않음) |

**가장 중요한 한 줄**: 네 실측에서 **탐지**(12/12)와 **severity 정확도**(8/12)는 안정성이 2배 다른 **별개의 양**이다. 이 둘을 하나의 pass 로 묶은 게 n=3 자가 깨진 진짜 원인이다.

---

## 1. 확률적 출력을 어떻게 판정하나

### 1-a. n=3 이 깨진 건 운이 아니라 계산 가능했다

τ-bench 의 불편추정량 **pass^k** — "k판 전부 성공할 확률" — 에 우리 실측(c=8, n=12)을 그대로 넣으면:

> pass^k = E_task[ C(c,k) / C(n,k) ]
> — Yao et al., *τ-bench* §3 ([arXiv:2406.12045](https://arxiv.org/abs/2406.12045), ICLR 2025)

| k | pass^k (c=8, n=12) | 뜻 |
|---|---|---|
| 1 | 0.667 | 한 판 돌려서 critical 나올 확률 |
| 2 | 0.424 | |
| **3** | **0.255** | **"3판 전부 critical" 자가 살아남을 확률 — 처음부터 1/4** |
| 4 | 0.141 | |
| 6 | 0.030 | |
| 12 | 0.000 | |

즉 자가 깨진 게 아니라, **깨질 확률이 75% 인 자를 세웠던 것**이다. 같은 논문이 이 붕괴를 실증한다 — gpt-4o 는 τ-retail 에서 pass^1 = 61.2% 인데 **pass^8 은 25% 미만**으로 떨어진다 (§5.1, Table 2, Figure 4).

⚠️ pass^k 는 **판마다 이진 성공 규칙 r∈{0,1} 이 이미 정의돼 있어야** 쓸 수 있다. 논문도 인정한다 — "r = 1 might be a necessary but not sufficient condition". 임계값 문제를 없애는 게 아니라 **"판당 성공이 뭐냐"로 옮긴다.**

⚠️ pass^1 → pass^k 를 지수 감쇠로 읽지 말 것. 0.612^8 ≈ 2% 인데 실측은 25% 였다. 성공은 태스크별로 **이봉(bimodal)** — 어떤 건 항상 되고 어떤 건 절대 안 된다. 우리 데이터도 같은 모양이다 (탐지 12/12, severity 8/12).

### 1-b. n 은 하나가 아니라 두 층으로 잡는다

같은 논문이 용도에 따라 n 을 갈랐고, 이유를 본문에 직접 적었다:

| 용도 | n | 논문 축자 |
|---|---|---|
| 모델 순위표 (Table 2) | 태스크당 **최소 3판** | "For main results (Table 2), we run at least 3 trials per task." |
| **태스크별 성공률 자체** (Figure 7) | 태스크당 **최소 40판** | "Each task has at least 40 gpt-4-turbo trials **to ensure reliable per-task success rates**." |

→ **우리 M6 완료 판정은 '픽스처별 성공률'쪽이므로 3판 층이 아니라 40판 층이다.**
(arXiv PDF 와 ICLR 2025 정식 출판본 양쪽에서 동일 확인 — 피어리뷰를 통과했고 조용한 수정도 없다.)

⚠️ **40 은 상수가 아니라 선례다.** τ-bench 의 n 은 이진 태스크 성공을 재는 것이고 severity 같은 순서형 흔들림이 아니다. 옮겨오는 건 숫자가 아니라 **"용도에 따라 n 을 층으로 나눈다"는 설계**다.

### 1-c. k/n → 구간으로 바꾸는 공식은 확정되어 있다

> "we recommend the **Wilson or the equal-tailed Jeffreys** prior interval for small n (n ≤ 40)... we recommend the **Agresti–Coull** interval for practical use when n ≥ 40."
> — Brown·Cai·DasGupta, *Interval Estimation for a Binomial Proportion*, Statistical Science 16(2):101-133, §5 ([ProjectEuclid](https://projecteuclid.org/journals/statistical-science/volume-16/issue-2/Interval-Estimation-for-a-Binomial-Proportion/10.1214/ss/1009213286.full))

그리고 손이 먼저 가는 Wald 구간(`p̂ ± z·√(p̂(1−p̂)/n)`)은 부정확한 정도가 아니라 **저자들이 쓰지 말라고 못 박은 물건**이다 — "the standard interval **should not be used**" / "an agreement that it **deserves not to be used at all**." 공식 Comment 4편 + Rejoinder 까지 확인했고 저자들은 물러선 적 없다.

**우리 케이스에 직격**: 12/12(confidence=1.00)나 0/3(오탐 없음)처럼 p̂ 가 0 또는 1 에 붙으면 **Wald 구간은 폭이 0 으로 붕괴**한다. 극단에서는 Jeffreys 가 더 매끄럽다 (BCD §4.1.1 은 Wilson 도 x=1..2, n<50 에서 경계 보정을 권한다).

덤: "np ≥ 5 면 정규근사 OK"라는 교과서 규칙도 이 논문이 깼다 — n=40, p=0.5 에서 실제 커버리지 0.919, n→∞ 에서도 γ=5 이면 0.875 에 머문다.

### 1-d. 우리 실측에 씌워보면

| 재는 것 | k/n | 95% Wilson | 폭 |
|---|---|---|---|
| sql-injection **탐지** | 12/12 | [0.758, 1.000] | 0.242 |
| sql-injection **severity == critical** | 8/12 | **[0.391, 0.862]** | **0.471** |
| 오탐 (with_tag_rule / clean) | 1/3 | [0.061, 0.792] | 0.731 |
| 오탐 (no_tag_rule / clean) | 0/3 | [0.000, 0.561] | 0.561 |

두 가지가 곧바로 드러난다:

1. **탐지는 n=12 에서도 꽤 단단한 측정인데, severity 는 동전 던지기(0.5)와 85% 를 구별조차 못 한다.** → 하나의 pass 로 묶으면 안 된다.
2. **태그 규칙 제거가 오탐을 고쳤는지는 n=3 으로 판정 불가.** 두 구간이 거의 완전히 포개진다 — "고쳤다"는 현재 근거는 **통계적으로 비어 있다.**

⚠️ 위 계산은 판들이 독립이라고 가정한다. 같은 프롬프트·같은 diff·같은 모델 스냅샷 반복이라 공통 잠재 요인이 있으면 **실제 불확실성은 이보다 크다.**

### 1-e. v1 vs v2 비교는 짝지어서

> "When two models are being compared, conducting statistical inference on the **question-level paired differences**, rather than the population-level summary statistics."
> "Because eval question scores are likely to be positively correlated... paired differences represent a **'free' reduction in estimator variance**."
> — Miller (Anthropic), *Adding Error Bars to Evals* 권고 #4 ([arXiv:2411.00640](https://arxiv.org/abs/2411.00640))

두 개의 집계 통과율을 나란히 놓고 비교하면 안 된다. **같은 픽스처 위에서 픽스처별 차이**를 본다.

단, **짝짓기는 하되 그 위에 얹는 검정은 CLT 기반이면 안 된다**:

> "Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints" — 소표본에서 CLT 구간이 불확실성을 "dramatically underestimating"한다. 그럼에도 짝짓기 자체는 지지 — "We would recommend using the **paired Bayes** method as it can account for correlations and thus produce narrower intervals."
> — Bowyer·Aitchison·Ivanova ([arXiv:2503.01747](https://arxiv.org/abs/2503.01747), ICML 2025 spotlight)

→ 우리 규모에서는 **paired + Wilson/Jeffreys/Bayes** 이지 paired + t-test 가 아니다.

### 1-f. 픽스처 3개로 무엇을 살 수 있고 무엇을 못 사나

Miller §5 Eq.9 (검출 가능한 최소 효과, MDE):

> n = (z_{α/2} + z_β)²(ω² + σ_A²/K_A + σ_B²/K_B) / δ²
> 워크드 예제: "≈ **969 independent questions**... new evals should contain at least **1,000 questions** in order to have good signaling ability."

n=3 을 대입하면 K=1 에서 MDE=107.8%p(무의미), K=10 에서 61.5%p, **K→∞ 에서도 53.9%p 에서 바닥**을 친다. ω²/n 이 줄지 않기 때문이고, 논문도 "The variance of the conditional mean... is **immutable**"라 적었다.

**하지만 '아무것도 못 잰다'는 과장이다.** Miller 의 n 은 '독립 문항 수'이고 추론 대상은 **안 본 PR(모집단)** 이다. 반면

> "프롬프트 v2 가 **이 픽스처에서** 심어둔 SQL 인젝션을 critical 로 더 자주 잡나"

는 **조건부 추론**이라 ω² 가 빠지고 정밀도가 σ²/K 로 결정된다 — **K 로 도달 가능한 영역**이다.

> **픽스처 3개는 "픽스처별 비율 주장"을 사주고, "일반화 주장"을 안 사준다.**

---

## 2. 비대칭 비용을 채점에 어떻게 넣나

### 2-a. 지표가 아니라 **단위**를 바꾼다

> "We call the user-perceived false-positive rate the **'effective false positive'** rate. An issue is an 'effective false positive' if developers **did not take some positive action** after seeing the issue."
> — Sadowski et al., *Software Engineering at Google* ch.20 ([abseil.io](https://abseil.io/resources/swe-book/html/ch20.html))

양방향으로 명시돼 있어서 대체가 확실하다:

| 지적이 | 개발자가 | 판정 |
|---|---|---|
| **틀렸는데** | 가독성 때문에 어쨌든 고쳤다 | **오탐 아님** |
| **맞았는데** | 이해 못 해서 아무것도 안 했다 | **오탐** |

즉 **참이라는 게 점수의 필요조건도 충분조건도 아니다. 행동이 단위다.**
운영도 실측 기반이다 — 코드리뷰의 "Not useful" 버튼이 하루 250회 눌리고, "The Tricorder team tracks analyzers with high 'Not useful' click rates... and will **disable** analyzers if they don't work."

⚠️ **우리 적용의 한계**: 이 지표는 살아있는 사람의 행동 신호라 픽스처 3개 오프라인에서 **직접 계산 불가**다. 옮겨오는 건 **채점 단위**("리뷰어가 이걸 보고 뭘 했을까")이고, 씨앗 finding 마다 **손으로 붙인 `actionable` 라벨**로 대리해야 한다.
⚠️ 유효 오탐은 **네 기준 중 하나**다 (이해 가능 / 조치 가능하고 고치기 쉬움 / 유효 오탐 10% 미만 / 코드 품질에 유의미).

### 2-b. 오탐 허용선은 전역 상수가 아니라 **계단식**이다 — 이게 M8 게이트의 선례

| 자동화 계층 | 결과 | 유효 오탐 기준 | 축자 |
|---|---|---|---|
| **빌드 차단** (Error Prone `ERROR`) | 빌드가 깨짐 | **0** | "Breaking the build is a warning that is not possible to ignore... **Produce no effective false positives**" + "Report issues affecting only **correctness** rather than style" |
| **리뷰 코멘트** (Tricorder, Critique 회색 박스) | 사람이 읽고 무시 가능 | **10% 미만** (신규 등록 기준) | "Produce less than 10% effective false positives — Developers should feel the check is pointing out an actual issue at least 90% of the time" |
| 플랫폼 전체 실측 | — | **5% 미만** | "The overall effective false-positive rate is just below 5%." |

Google 자체 라이브 문서 [errorprone.info/docs/criteria](https://errorprone.info/docs/criteria) (2026 저작권 표기)에서 같은 두 계층·같은 두 수치를 독립 확인했다. `ERROR` 는 빌드를 깨고 `WARNING` 은 안 깨므로 **severity 분할이 곧 자동화 결과 분할**이다.

> **우리 M8 게이트에 그대로 대응**: 자동 게시 = 리뷰 코멘트 계층(10% 선), critical→사람 큐 = 빌드 차단에 준하는 계층.

⚠️ **우리 규모에서 10% 는 직접 측정 불가**다 — 픽스처 3개의 해상도 바닥이 33%다. 필요한 판수를 계산해보면:

| 정상 diff 오탐 | 95% 상한 |
|---|---|
| 0/3 | 0.561 |
| 0/10 | 0.278 |
| 0/20 | 0.161 |
| 0/30 | 0.114 |
| **0/40** | **0.088** ← 여기서야 "10% 미만"을 말할 수 있다 |
| 현재 1/3 | 0.792 |

⚠️ 10% 는 신규 검사 **등록** 기준이고, 이후 비활성화는 자동 트립와이어가 아니라 **사람 판단**이다. 중간 계층(presubmit)에는 논문이 수치를 안 준다 — 단조 증가 법칙이 두 끝점에서만 지지된다.

---

## 3. severity 같은 순서형 필드의 흔들림

### **표준을 1차 출처에서 찾지 못했다.**

존재하는 건 "카테고리에 가중치를 주고 Dirichlet 사후분포로 불확실성을 전파하는" 기계다:

> "Evaluation outcomes are modeled as **categorical (not just 0/1)** with a Dirichlet prior, giving closed-form expressions for the posterior mean and uncertainty of **any weighted rubric**."
> "In dialogue safety, categories might distinguish {unsafe, borderline, safe}" / "Each discrete level becomes a category index k, and w_k reflects the **importance** of that level"
> — Hariri et al., *Don't Pass@k: A Bayesian Framework for LLM Evaluation* ([arXiv:2510.04265](https://arxiv.org/abs/2510.04265), ICLR 2026)

**그런데 전문을 `ordinal|ordered|monoton|adjacen` 으로 grep 한 결과** — "ordinal"은 Kendall's τ 순위 상관에만 나오고 루브릭 카테고리에는 한 번도 안 나온다. **ordered-Dirichlet 도, w 에 대한 단조 제약도, 인접 허용 규칙도 없다.** Dirichlet 은 라벨 교환가능이라 순서 정보는 오직 **분석자가 넣는 가중치로만** 들어간다.

논문 스스로 인정한다:
> "Bayes@N **does not resolve** disagreement or bias in the rubric or labeling process itself. The framework **assumes** a labeling scheme... and a weight vector w **are given**."

추가 단서: 구간 형태가 M(문항 수) 큰 경우의 가우시안 근사에 기대므로 **M=3 은 "M large"가 아니다.** 균등 사전 하에서 사후 평균은 가중 평균의 양의 아핀 변환이라 **순위로는 avg@N 과 동치** — 새로 사는 건 점추정이 아니라 보정된 불확실성이다.

> **우리 프로젝트 특유의 논점**: severity 는 M8 게이트의 **첫 축**(critical 이면 사람에게)이므로 가중치가 자유롭지 않다. critical↔high 는 "점수 조금 깎기"가 아니라 **경로가 갈리는 사건**이다. 부분 점수를 주는 순간 게이트와 채점기가 다른 말을 하게 된다.

→ **조사로 답이 안 나오는 정책 결정이다.** [결정 2] 참조.

---

## 4. LLM-as-judge 는 언제부터 필요해지나

### **검증을 통과한 1차 출처가 하나도 없다.**

이 조사에서 심판 검증에 직접 답할 후보는 단 하나였고 — evalstats 기반의 "LLM-judge 편향은 제거가 아니라 통계적으로 보정 가능(PPI, Angelopoulos et al. 2023)" — **3표 적대적 검증에서 1-2 로 기각**됐다. 같은 출처 기반 다른 주장 2건도 0-3 으로 기각됐다.

간접적으로만 닿는 것: Hariri et al. 은 "Once the labels are available (from humans **or an LLM-as-a-judge**), Bayes@N provides Bayesian estimates"라며 심판을 **라벨 공급원으로 전제**할 뿐, 언제 필요한지도 어떻게 검증하는지도 말하지 않는다 (오히려 "does not resolve... bias in the labeling process itself"로 **명시적 범위 밖**).

**"찾다가 시간이 없었다"가 아니라 "찾았지만 검증을 통과한 게 없다"이다.**

### 실무적 함의 (출처 없음 — 추론임을 명시)

우리 fixture 3개는 **정답을 심어서 안다.** 그래서 탐지 / severity / 오탐은 전부 평범한 파이썬 함수로 잴 수 있다.
코드가 못 재는 건 **`rationale` 텍스트의 품질** 하나뿐이다 — 설명이 맞는 이유를 대는가, 리뷰어가 행동할 만한가. 그런데 그건 정확히 **Google 의 유효 오탐 정의가 요구하는 판단**이다.

→ M6 범위에서는 그 판단을 **심판 LLM 대신 씨앗 finding 마다 손으로 붙인 `actionable` 라벨**로 대리하는 게 근거가 있는 유일한 경로다.

---

## 5. 최소 구현 제안 — 파일 3개, 함수 6개

> ⚠️ 이건 조사 결과가 아니라 위 findings 를 우리 규모에 맞춘 **설계**다. 출처가 이 형태를 규정하지 않는다.

**핵심 설계 결정 두 가지**
1. **'탐지'와 'severity 정확도'를 분리된 두 지표로** 잰다 (우리 데이터에서 안정성이 2배 다르다)
2. **정상 diff 를 오탐 전용 픽스처로 승격**시켜 비대칭 비용을 **별도 축**으로 뺀다

### ① `fixtures/expected.yaml` — 심어둔 정답을 명시적 라벨로

지금 이 정답은 recon 스크립트와 **사람 머릿속에만** 있다.

```
sample.diff:
  must_detect:      [sql-injection @ api/users.py:17]
  must_not_detect:  [review-evasion-attempt]
  expected_severity: critical
  actionable:        true
```

### ② `eval/runner.py` — `scratch/recon_prompt_2x2.py` 가 8할 완성

필요한 건 (프롬프트 버전 × 픽스처 × K판)을 돌려 **append-only JSONL** 로 흘리는 것 하나.
**재실행이 누적되게** 만들어야 K 를 예산 되는 대로 키울 수 있다.

### ③ `eval/grade.py` — 판당 이진 규칙 3개 (pass^k 가 요구하는 r∈{0,1})

| 규칙 | 재는 것 |
|---|---|
| `detected` | must_detect 를 **카테고리+파일**로 잡았나 |
| `severity_exact` | 등급이 **정확히** 일치하나 |
| `clean` | must_not_detect 가 **하나도** 안 나왔나 |

**함수 6개**: `load_expected` / `grade_trial`(트라이얼 → 3-bool) / `wilson(k,n)` / `pass_hat_k(c,n,k)` / `paired_delta(v1,v2)` / `report`

### 예산 배분 — 균등은 거의 확실히 잘못된 배분

| 축 | 필요 K | 근거 |
|---|---|---|
| 오탐 (정상 diff) | **~40판, 0 오탐** | 95% 상한 0.088 → Google 10% 선을 겨우 말할 수 있음 |
| 탐지 | **~10판** | 이미 12/12 로 안정 |
| severity | 40판 써도 폭 ~0.29 | 여기가 제일 비싸다 |

지연 10~41초 × 프롬프트 4개 × 픽스처 3개 × K → **총 호출수가 구독 한도에 직접 부딪힌다.**

### 리포트가 인쇄해야 하는 것

판정 하나가 아니라 — **픽스처별 k/n + Wilson 구간 + 베이스라인 대비 짝지은 차이.**

> **"통과"라는 단어를 쓰지 않는 게 이 하네스의 요점이다.**

---

## 6. 이 조사의 한계 — 인용 금지 목록

적대적 검증(주장당 3표, 2표 이상 반박이면 폐기)에서 **기각된 주장들.** 그럴듯하고 방향도 맞아 보이지만 **근거로 쓰지 말 것**:

| 기각된 주장 | 투표 |
|---|---|
| "Var(μ̂) = (Var(x) + E[σᵢ²])/n 이므로 3 픽스처에서는 K 를 아무리 늘려도 소용없다" | 0-3 |
| "K≈4-6 이 방어 가능한 예산이고 12는 낭비" | 0-3 |
| "12판은 n=1 이지 n=12 가 아니다" | 0-3 |
| "evalstats 는 15 샘플을 통계적 하한으로 제시" | 0-3 |
| "R≥3 반복이면 2단 중첩 부트스트랩 필수" | 0-3 |
| "PPI 로 LLM 심판 편향을 통계적으로 보정" | 1-2 |
| "베이지안 사후평균은 균등 사전에서 Pass@1 과 순위 동치" | 0-3 |
| "44.2 / 27.1 trials 로 수렴" | 0-3 |

**검증 실패 2건** (인프라 오류로 3표 중 2표가 에러): Anthropic 블로그 요약본 기반 (a) 비결정적 답변은 리샘플링해 문항 평균을 쓰라 (b) 두 시스템 비교는 짝지은 차이 검정. **둘 다 Miller 논문 원문에서 축자 확인된 권고 #3·#4 와 같은 내용이라 실질적 손실은 없다.**

**출처의 시점**: BCD 2001(이항분포의 결정론적 성질이라 낡지 않음 — 독립 재계산으로 확인) / Google SWE book 2020, Tricorder 2015 → "Google 이 **현재** 이렇게 잰다"가 아니라 **"2020년까지 문서화된 관행"** 으로 읽을 것. 다만 errorprone.info 라이브 문서가 2026년 표기로 같은 기준을 유지 중이라 선례로서는 살아있다.

**τ-bench 후속 경고**: SABER([arXiv:2512.07850](https://arxiv.org/abs/2512.07850)), τ²/τ³-bench 가 τ-airline 태스크 **절반에 정답 오류·모호성**이 있었다고 보고했다 — pass^k 하락의 일부는 벤치마크 아티팩트다.

---

## 7. 우리가 정해야 할 결정 — 4개

### 결정 1 — M6 완료 판정의 단위: **'탐지'인가 'severity 정확도'인가**

데이터가 이 둘을 갈라놓았다.

| 선택 | 지금 상태 | 얻는 것 | 잃는 것 |
|---|---|---|---|
| **탐지** | 12/12, CI [0.758, 1.000] | 당장 통과, 안정적 | **M8 게이트가 요구하는 것(critical→사람)을 안 잰다** |
| **severity 정확도** | 8/12, CI [0.391, 0.862] | M8 과 정렬 | 33% 확률로 실패, K 를 크게 늘려야 구간이 좁아짐 |

조사로는 답이 안 나온다 — **무엇이 '완료'인지에 대한 우리의 정의 문제다.**

### 결정 2 — critical↔high 흔들림: **결함으로 볼 것인가, 게이트를 견디게 고칠 것인가**

1차 출처에 인접 등급 허용 표준이 **없다는 게 확인**됐으므로 선택지는 셋:

| | 방법 | 대가 |
|---|---|---|
| (a) | severity 정확 일치를 요구하고 **프롬프트로 흔들림을 잡는다** | 프롬프트 반복 비용 |
| (b) | **가중 카테고리로 부분 점수** (Dirichlet, 가중치는 우리가 정함) | 게이트와 채점기가 다른 말을 하게 됨 |
| (c) | **게이트 첫 축을 severity 단독 → severity+category 조합으로** 바꿔, sql-injection 이 high 로 떨어져도 사람 큐로 가게 | 프롬프트 문제를 아키텍처로 우회. **M8 범위 결정을 앞당김** |

⚠️ (c) 는 `docs/CURRENT.md` 의 "결정을 미룬 것" 표와 충돌하는지 확인 필요 (G10 이 "M8 범위는 M6 직후에 정한다"로 미뤄둔 상태).

### 결정 3 — 판수 예산 K 를 픽스처별로 **어떻게 비대칭 배분할 것인가**

축마다 요구가 다르다 (§5 표). **균등 배분은 거의 확실히 잘못된 배분**이고, 총 호출수가 구독 한도에 직접 부딪힌다.

### 결정 4 — 태그 누출 오탐(`review-evasion-attempt`): **지금 고칠 것인가, 하네스의 첫 시험대로 남길 것인가**

현재 근거는 **통계적으로 비어 있다** — 1/3 [0.061, 0.792] vs 0/3 [0.000, 0.561], 구간이 거의 완전히 포개진다.

| 선택 | 값어치 |
|---|---|
| **지금 고친다** | 오탐 축을 0 에서 출발시킴 |
| **남긴다** | 자를 먼저 만들고 **그 자로 이 수정을 검증한다** → **자를 신뢰할 근거가 생긴다** |

---

## 출처

**1차 (핵심)**
- Yao et al., *τ-bench* — [arXiv:2406.12045](https://arxiv.org/abs/2406.12045) · [ICLR 2025 출판본](https://proceedings.iclr.cc/paper_files/paper/2025/file/1b126cc38b8638e07bef37e7b2bb72bf-Paper-Conference.pdf) · [레퍼런스 구현 run.py](https://github.com/sierra-research/tau-bench/blob/main/tau_bench/run.py)
- Brown·Cai·DasGupta, *Interval Estimation for a Binomial Proportion*, Statistical Science 16(2) — [ProjectEuclid](https://projecteuclid.org/journals/statistical-science/volume-16/issue-2/Interval-Estimation-for-a-Binomial-Proportion/10.1214/ss/1009213286.full) · [PDF](http://www-stat.wharton.upenn.edu/~tcai/paper/Binomial-StatSci.pdf)
- Sadowski et al., *Software Engineering at Google* ch.20 — [abseil.io](https://abseil.io/resources/swe-book/html/ch20.html) · [Tricorder 논문](https://research.google/pubs/lessons-from-building-static-analysis-tools-at-google/) · [Error Prone criteria](https://errorprone.info/docs/criteria)
- Miller, *Adding Error Bars to Evals* (Anthropic) — [arXiv:2411.00640](https://arxiv.org/abs/2411.00640)
- Bowyer·Aitchison·Ivanova, *Don't Use the CLT in LLM Evals...* (ICML 2025 spotlight) — [arXiv:2503.01747](https://arxiv.org/abs/2503.01747)
- Hariri et al., *Don't Pass@k: A Bayesian Framework for LLM Evaluation* (ICLR 2026) — [arXiv:2510.04265](https://arxiv.org/abs/2510.04265)

**우리 실측**
- `scratch/prompt_variance.json` (n=12) · `scratch/prompt_2x2.json` (2×2×3판) · `scratch/recon_prompt_2x2.py`

---

*조사 규모: 검색 각도 5개 · 원문 26개 fetch · 주장 130개 추출 → 25개 검증 → 13 확정 / 10 기각 / 2 미검증 → 11개로 합성. 에이전트 108개.*
