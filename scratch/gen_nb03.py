"""Notebook 03 생성 — 명령 하나가 숫자가 되기까지 (grader 추적).

⚠️ 이건 friction 노트북이 아니다. `TODO(human)` 이 없다 —
   **이미 만든 코드를 따라 읽는** 용도이고, 그래서 "동시에 열린 노트북 1개" 규칙과 안 부딪힌다.

⚠️ 왜 HTML 스테퍼가 아니라 노트북인가: 이 노트북은 **진짜 함수를 import 한다.**
   코드가 바뀌면 셀이 다르게 돌거나 터진다 — 그림으로 그리면 조용히 낡는다.
"""
import json
from pathlib import Path

OUT = Path("/Users/imseungmin/work/llm_study/pr_agent_project/learning/notebooks/03-grader-trace.ipynb")
OUT.parent.mkdir(parents=True, exist_ok=True)

C = []


def md(s):
    C.append({"cell_type": "markdown", "id": f"cell-{len(C)}", "metadata": {},
              "source": s.strip("\n")})


def code(s):
    C.append({"cell_type": "code", "id": f"cell-{len(C)}", "execution_count": None,
              "metadata": {}, "outputs": [], "source": s.strip("\n")})


md(r"""
# 03 · 명령 하나가 숫자가 되기까지 — 자(ruler)를 따라 읽기
""")

md(r"""
## 지금 어디인가

```
PR 리뷰 멀티에이전트   ①웹훅 → ②큐 → ③워커 → ④에이전트 4 → ⑤애그리게이터 → ⑥게이트
 └─ M6 — ④⑤ 를 진짜 LLM 으로
     └─ 고치기 전에 "나아졌나"를 판정할 자부터 세운다 (M6-1)   ← 다 만들었다
         └─ 그 자가 **어떻게 도는지** 한 흐름으로 따라 읽는다   ← 이 노트북
```

**이 노트북엔 `TODO(human)` 이 없다.** 채우는 게 아니라 **읽는** 물건이다.
노트북 01(Wilson)·02(pass^k)는 공식을 손으로 구현했고, 여기선 그게 **실제 코드에서
어디에 꽂혀 있는지**를 본다.

⚠️ 모든 셀이 **진짜 함수를 import 한다.** 코드가 바뀌면 이 노트북은 다르게 돌거나 터진다 —
그게 의도다. 그림으로 그렸으면 조용히 낡았을 것.
""")

md(r"""
## 한 장 요약

```bash
uv run python scripts/eval_prompt.py regrade
```

```
 ① 재료 둘을 읽는다
      evals/runs/*.json         모델이 뱉은 것       do_regrade()      eval_prompt.py
      fixtures/expected.yaml    정답이 뭔가          load_expected()   grader.py
                    │
 ② 판마다 채점 (K번 반복)
      grade_run(fixture, findings, expected)                          grader.py
        ├ _covers(item, f)      category + file                       grader.py
        │    └ category_matches()   대소문자·구분자 통일
        ├ _item_hit(item, f)    _covers + severity_min                grader.py
        │    └ meets_severity()     critical>high>medium>low>info
        └ 출구 두 개
             caught  → passed   (판 단위)     _item_hit 을 쓴다
             labels  → (conf,y) (finding 단위) _covers 를 쓴다   ← 축이 여기서 갈린다
                    │
 ③ 모아서 숫자 둘
      wilson_ci(x, n)   판을 센다          stats.py       "진짜 비율은 어디쯤"
      Brier             finding 을 센다    eval_prompt.py "확신도가 믿을 만한가"
```

**Wilson 과 Brier 가 다른 걸 센다는 게 핵심**이다. 그래서 grader 의 출구가 둘이다.
""")

md(r"""
---
## 준비 — 레포 루트를 path 에 꽂는다
""")

code(r"""
import sys, json
from pathlib import Path

ROOT = Path.cwd()
while not (ROOT / "fixtures").exists():      # 노트북을 어디서 열든 루트를 찾는다
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT))
print("레포 루트:", ROOT)
""")

md(r"""
---
# ① 재료 둘

## 재료 A — 모델이 뱉은 것 (`evals/runs/`)

📍 `scripts/eval_prompt.py` · `do_regrade()`
""")

code(r"""
RUN_PATH = ROOT / "evals" / "runs" / "sample__luna__orig__k9.json"
data = json.loads(RUN_PATH.read_text(encoding="utf-8"))

print("픽스처:", data["fixture"], "· 판 수:", len(data["runs"]))
print("조건  :", data["meta"]["variant"], "·", data["meta"]["prompt_source"])
print()
run0 = data["runs"][0]
print("판1 의 status:", run0["status"])
for f in run0["findings"]:
    print(f"  [{f['severity']:<9}] {f['category']:<24} {f['file']}:{f['line']}  conf={f['confidence']}")
""")

md(r"""
## 재료 B — 정답지 (`fixtures/expected.yaml`)

📍 `evals/grader.py` · `load_expected()` — YAML 의 `fixtures:` 블록만 돌려준다.
""")

code(r"""
from evals.grader import load_expected

expected = load_expected()
exp = expected["sample"]

print("통 세 개:")
for 통 in ("must_catch", "must_not_appear", "not_graded"):
    items = exp.get(통) or []
    print(f"  {통:<16} {len(items)}개")
    for it in items:
        extra = f" · severity_min={it['severity_min']}" if "severity_min" in it else ""
        print(f"      {it['category']}{extra}")
""")

md(r"""
---
# ② 판정 — 함수 셋을 손으로 굴려본다

## 가장 안쪽: `category_matches` — 표기 흔들림만 없앤다

📍 `evals/grader.py` · `normalize_category()` / `category_matches()`

⚠️ **부분 문자열은 안 연다.** 열면 `sql-injection` 이 `missing-sql-injection-tests` 와
매칭되어 y 라벨이 오염된다 (D6).
""")

code(r"""
from evals.grader import normalize_category, category_matches

for raw in ["SQL-Injection", "sql injection", "sql_injection", "  sql   injection "]:
    print(f"{raw!r:26} → {normalize_category(raw)!r}")

print()
print("sql-injection vs missing-sql-injection-tests :", category_matches("sql-injection", "missing-sql-injection-tests"))
print("missing-edge-case-test vs -tests             :", category_matches("missing-edge-case-test", "missing-edge-case-tests"))
""")

md(r"""
👆 마지막 줄이 `False` 인 게 **오늘 실제로 문제가 된 지점**이다 — 모델이 같은 지적을
단수/복수로 다르게 뱉었고, 그래서 `expected.yaml` 의 `not_graded` 에 **둘 다 나열**했다.
""")

md(r"""
## 그 다음: `meets_severity` — 순서를 어디서 가져오나

📍 `evals/grader.py` · `SEVERITY_ORDER`

**여기 순서를 복사해 적지 않았다.** `backend/agents/schema.py` 의 `Literal` 선언에서
`get_args()` 로 뽑는다 — 같은 사실이 두 곳에 적히면 반드시 갈라지기 때문이다.
""")

code(r"""
from evals.grader import SEVERITY_ORDER, SEVERITY_RANK, meets_severity

print("schema.py 에서 뽑은 순서:", SEVERITY_ORDER)
print("rank (작을수록 심각)     :", SEVERITY_RANK)
print()
for actual in ["critical", "high", "medium"]:
    print(f"{actual:<9} 가 severity_min=critical 을 넘나 → {meets_severity(actual, 'critical')}")
""")

md(r"""
## 축이 갈리는 자리: `_covers` vs `_item_hit`

📍 `evals/grader.py` · `_covers()` / `_item_hit()`

| | 보는 축 | 답하는 질문 | 어디로 가나 |
|---|---|---|---|
| `_covers` | category + file | **"정답지가 아는 지적인가"** | `y` 라벨 → Brier |
| `_item_hit` | + `severity_min` | **"제대로 잡았나"** | `caught` → `passed` → Wilson |

`line` 은 **어느 쪽에도 안 쓴다** — 픽스처마다 안정성이 달라서 뺐다 (D1).
""")

code(r"""
from evals.grader import _covers, _item_hit

item = exp["must_catch"][0]          # sql-injection · severity_min=critical
print("정답지 항목:", item)
print()

for sev in ["critical", "high"]:
    f = {"severity": sev, "category": "sql-injection", "file": "api/users.py",
         "line": 17, "confidence": 1.0}
    print(f"[{sev:<9}] sql-injection   _covers={_covers(item, f)}   _item_hit={_item_hit(item, f)}")
""")

md(r"""
👆 **`high` 줄이 오늘 잡은 버그다.**

`_covers=True` 인데 `_item_hit=False` — *"진짜 SQL 인젝션이 맞다. 다만 심각도를 낮게 봤다."*

처음엔 `_item_hit` **하나로** 둘 다 판정했다. 그러면 이 finding 이 `must_catch` 실패 →
어느 통에도 없음 → **화이트리스트가 "지어냈다"(y=0)로 찍는다.** 진짜 인젝션을.

`schema.py:52` 의 confidence 정의가 이걸 금지한다:
> *"이 지적이 **사실일** 확률. **심각도와 무관하게** '내가 틀렸을 가능성'만 본다."*
""")

md(r"""
## 오탐 판정: `find_violations` — 화이트리스트

📍 `evals/grader.py` · `find_violations()`

**어느 통에도 안 걸리면 오탐이다** (D6). `not_graded` 가 탈출구.
""")

code(r"""
from evals.grader import find_violations

시험판 = [
    {"severity": "critical", "category": "sql-injection",   "file": "api/users.py", "line": 17, "confidence": 1.0},
    {"severity": "medium",   "category": "resource-leak",   "file": "api/users.py", "line": 14, "confidence": 0.95},
    {"severity": "low",      "category": "missing-docstring","file": "api/users.py", "line": 12, "confidence": 0.9},
    {"severity": "high",     "category": "hardcoded-path",  "file": "api/users.py", "line": 11, "confidence": 0.7},
]
for f in find_violations(시험판, exp):
    print("오탐:", f["category"])
print("\n(missing-docstring 은 not_graded 라 빠졌고, hardcoded-path 만 걸렸다)")
""")

md(r"""
## 합치는 곳: `grade_run` — 출구 둘을 동시에 만든다

📍 `evals/grader.py` · `grade_run()` → `RunGrade`
""")

code(r"""
from evals.grader import grade_run

g = grade_run("sample", 시험판, expected)
print("passed :", g.passed)
print("caught :", g.caught, "  ← must_catch 항목별")
print("labels :", g.labels, "  ← (confidence, y)")
print()
print("y 의 뜻:  1=사실  0=지어냄  -1=판정 보류(not_graded)")
""")

md(r"""
---
# ③ 숫자 둘 — 서로 다른 걸 센다

## Wilson — **판**을 센다

📍 `evals/stats.py` · `wilson_ci()` (노트북 01 에서 만든 것)

$$\text{두 근 사이} \;:\; \left(1+\tfrac{z^2}{n}\right)p^2 \;-\; \left(2\hat p+\tfrac{z^2}{n}\right)p \;+\; \hat p^2 \;\le\; 0$$

**왜 Wald 가 아닌가**: `p̂` 가 0 이나 1 에 붙으면 Wald 의 폭이 **0 으로 붕괴**한다 —
*"3판 중 0판이니 오탐률은 정확히 0%"* 라고 말하게 된다. 우리 n 은 3~18 이라 자주 난다.
""")

code(r"""
from evals.stats import wilson_ci

for x, n in [(7, 9), (3, 3), (2, 3), (0, 3)]:
    lo, hi = wilson_ci(x, n)
    print(f"{x}/{n} = {x/n:.2f}   Wilson 95% [{lo:.2f}, {hi:.2f}]   폭 {hi-lo:.2f}")
""")

md(r"""
👆 `3/3` 의 구간이 `[0.44, 1.00]` 인 게 요점이다 — **만점이어도 아무 말도 못 한다.**
Wald 였으면 폭이 0 이라 *"정확히 100%"* 라고 말했을 것.
""")

md(r"""
## Brier — **finding** 을 센다

📍 `scripts/eval_prompt.py` · `_print_table()` 안 한 줄 (별도 함수가 아직 없다)

$$\text{Brier} \;=\; \frac{1}{N}\sum_i (\text{conf}_i - y_i)^2$$

**Glenn Brier, 1950, 기상 예보 채점용.** *"비 올 확률 70%"* 같은 **확률 예측**은
○/✗ 로 채점이 안 되니까 만든 것.

읽는 법: **0 = 완벽 · 0.25 = 매번 0.5 찍기(무정보) · 1 = 최악.**
제곱이라서 **확신하고 틀리면 벌점이 폭발**한다.
""")

code(r"""
print("한 건짜리 벌점 — 오탐(y=0)일 때 confidence 별:")
for conf in [1.0, 0.9, 0.5, 0.1]:
    print(f"  conf={conf}  →  ({conf} - 0)^2 = {(conf-0)**2:.2f}")

print("\n정탐(y=1)일 때:")
for conf in [1.0, 0.5]:
    print(f"  conf={conf}  →  ({conf} - 1)^2 = {(conf-1)**2:.2f}")
""")

md(r"""
⚠️ **`y=-1` 은 빼고 센다.** 라벨 없는 걸 0 으로 세면 **오탐으로 세는 것**이다.
""")

md(r"""
---
# 전체를 한 번에 — 진짜 9판으로

위 조각들이 실제로 어떻게 합쳐지는지, `do_regrade` 가 하는 일을 그대로 재현한다.
""")

code(r"""
grades = []
errors = 0
for r in data["runs"]:
    if "findings" not in r:          # 인프라 오류 — 분모에서 뺀다 (D7)
        errors += 1
        continue
    grades.append((r.get("status", "ok"), grade_run(data["fixture"], r["findings"], expected)))

x, n = sum(g.passed for _, g in grades), len(grades)
lo, hi = wilson_ci(x, n)
print(f"{data['fixture']}: {x}/{n} = {x/n:.2f}   Wilson 95% [{lo:.2f}, {hi:.2f}]")

labels = [(c, y) for _, g in grades for c, y in g.labels]
scored = [(c, y) for c, y in labels if y != -1]
brier = sum((c - y) ** 2 for c, y in scored) / len(scored)
print(f"Brier = {brier:.4f}  (라벨 {len(labels)} 중 채점 {len(scored)} · 보류 {len(labels)-len(scored)})")

print("\nBrier 에 크게 기여한 것들:")
for c, y in sorted(scored, key=lambda t: -((t[0]-t[1])**2))[:3]:
    print(f"  conf={c}  y={y}  →  벌점 {(c-y)**2:.2f}")
""")

md(r"""
👆 **벌점 1.00 짜리가 곧 M8 의 위험**이다. `confidence=1.0` 인데 오탐이면:

```
게이트 규칙:  confidence >= 0.6  →  PR 에 자동 게시
              conf=1.0 짜리 오탐  →  아무도 안 보고 나간다
```

`conf=0.5` 였다면 임계값 아래라 **사람 큐로 갔을 것**이다.
Brier 가 `1.0` 짜리에 큰 벌점을 주는 건 수학의 우연이 아니라 **그게 실제로 더 비싸기 때문**이다.

그리고 이게 **INV-3 이 위험해지는 지점**이다 — 불변식은 *"모든 finding 은 confidence 를
갖는다"* 인데, **값이 있는 것**과 **값이 쓸모 있는 것**은 다르다.
""")

md(r"""
---
## 다음에 이어질 것

- **ECE** — Brier 의 짝. *"0.9 라고 말한 것들만 모으면 실제로 90% 가 맞았나"* 를 **구간별로** 본다.
  Brier 는 전체 평균이라 **어느 확신 구간이 망가졌는지**를 못 알려준다. (M6-0b)
- **McNemar** — 프롬프트 두 개를 **짝지어** 비교. 오늘 `orig [0.45,0.94]` vs
  `no-tag-rule [0.21,0.94]` 가 거의 포개져서 아무 말도 못 했다 → **K 를 올려야 한다.** (M6-3b)
- **pass^k** — 노트북 02. K판 **연속** 성공 확률. M6-6 완료 판정에서 연다.
""")

nb = {"cells": C,
      "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                   "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
OUT.write_text(json.dumps(nb, ensure_ascii=False, indent=1))
print("썼다:", OUT)
