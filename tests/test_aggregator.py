"""`backend/agents/aggregator.py` — **어느 후보를 골라도 성립해야 하는 성질**만 잠근다.

⚠️ **잠정값을 테스트하지 않는다.** 그 파일의 TODO ①②③ 은 사용자가 뒤집을 자리이고,
`dedup_key` 가 `(file, category)` 라는 사실이나 대표를 severity 로 고른다는 사실을
테스트에 박으면 **뒤집는 순간 테스트가 빨간불이 되어 "고치지 마라"고 압박한다.**
테스트가 설계 결정을 인질로 잡는 건 이 프로젝트가 원하는 게 아니다.

그래서 여기 있는 건 **후보와 무관한 성질**뿐이다:

    결정성        같은 입력 → 같은 출력. 어느 dedup 키를 골라도 이건 참이어야 한다
    입력 비변경   원본 findings 는 "누가 무엇을 말했나"의 유일한 기록이다 (INV-4 의 정신)
    출처 보존     합쳐진 것의 sources 가 원본의 agent_type 집합과 같다
    시끄러운 실패 출처 없는 입력은 **무엇을 고칠지 말하며** 터진다

⚠️ 아래 각 테스트에 **어느 TODO 를 뒤집으면 다시 봐야 하는지** 적어뒀다.
   그 표시가 없는 테스트는 뭘 고르든 통과해야 한다.
"""

import copy

import pytest

from backend.agents.aggregator import aggregate

ORDER = ("security", "quality", "testing", "docs")


def f(agent, severity, category, line, conf, rationale="근거", file="a.py"):
    return {
        "agent_type": agent, "severity": severity, "category": category,
        "file": file, "line": line, "confidence": conf, "rationale": rationale,
    }


# 2026-08-28 실측 (`fixtures/sample.diff`, 관점 넷 각 1판). 지어낸 값이 아니다.
MEASURED = [
    f("security", "high", "sql-injection", 17, 1.00),
    f("quality", "critical", "sql-injection", 17, 0.99),
    f("quality", "medium", "resource-leak", 15, 0.97),
    f("testing", "critical", "sql-injection", 15, 1.00),
    f("testing", "medium", "resource-leak", 12, 0.95),
    f("testing", "low", "missing-test-coverage", 16, 0.98),
    f("docs", "critical", "sql-injection", 17, 1.00),
    f("docs", "medium", "resource-leak", 18, 0.98),
]


# ══════════════════════════════════════════════════════════════════════
# 결정성 — 완료 판정이 회귀 감지기가 되려면 이게 먼저다
# ══════════════════════════════════════════════════════════════════════


def test_입력_순서가_결과를_안_바꾼다():
    """리듀서는 **노드 완료 순서대로** 쌓는다. 그 순서는 비결정적이다 (Lesson 07).
    → 순서에 의존하면 같은 리뷰가 판마다 다른 답을 낸다."""
    import random

    base = aggregate(MEASURED, order=ORDER)
    for seed in range(10):
        shuffled = MEASURED[:]
        random.Random(seed).shuffle(shuffled)
        assert aggregate(shuffled, order=ORDER) == base, f"seed {seed} 에서 결과가 갈렸다"


def test_완전_동률에서도_결정적이다():
    """**셔플 테스트가 못 잡는 경우** (2026-08-28 에 실제로 뚫렸다).

    같은 관점 + 같은 severity + 같은 confidence 면 정렬 키 셋이 전부 같아진다.
    그런 입력은 상상이 아니다 — M0 에서 한 관점이 같은 결함을 두 번 뱉었다
    (`PLAN.md` G-M0-3).
    """
    tie = [
        f("security", "high", "sql-injection", 10, 0.9, "A 쪽 설명"),
        f("security", "high", "sql-injection", 20, 0.9, "B 쪽 설명"),
    ]
    assert aggregate(tie, order=ORDER) == aggregate(tie[::-1], order=ORDER)


# ══════════════════════════════════════════════════════════════════════
# 입력 비변경 — 원본이 "누가 무엇을 말했나"의 유일한 기록이다
# ══════════════════════════════════════════════════════════════════════


def test_입력을_안_건드린다():
    """`state["findings"]` 는 리듀서가 쌓은 원본이고, 애그리게이터가 **뭘 버렸는지**를
    되짚을 유일한 자료다. 여기가 깨지면 M8 에서 "왜 이 지적이 사라졌나"에 답할 수 없다."""
    before = copy.deepcopy(MEASURED)
    aggregate(MEASURED, order=ORDER)
    assert MEASURED == before


def test_출력이_입력_dict_와_다른_객체다():
    """같은 객체를 돌려주면 호출부가 `merged` 를 고칠 때 원본까지 바뀐다."""
    out = aggregate(MEASURED, order=ORDER)
    assert all(m is not src for m in out for src in MEASURED)


# ══════════════════════════════════════════════════════════════════════
# 출처 — M8 게이트의 커버리지 판정(G2)이 읽는 값
# ══════════════════════════════════════════════════════════════════════


def test_sources_가_원본의_출처_집합과_같다():
    """합치면서 출처를 **잃지도 지어내지도** 않는다.
    ⚠️ dedup 키를 뒤집어도(TODO ①) 이 성질은 그대로여야 한다 — 묶는 방식이 바뀔 뿐이다."""
    out = aggregate(MEASURED, order=ORDER)
    for m in out:
        origin = {x["agent_type"] for x in MEASURED
                  if x["file"] == m["file"] and x["category"] == m["category"]}
        assert set(m["sources"]) == origin


def test_sources_가_팬아웃_순서로_정렬된다():
    """같은 집합이면 같은 리스트여야 표가 재현된다 — 관측 순서로 적으면 비결정적이다."""
    out = aggregate(MEASURED, order=ORDER)
    for m in out:
        assert m["sources"] == [a for a in ORDER if a in m["sources"]]


def test_merged_from_은_합친_개수다():
    """`len(sources)` 와 **다를 수 있다** — 한 관점이 같은 결함을 두 번 뱉으면."""
    dup = [
        f("security", "high", "x", 1, 0.9, "첫 번째"),
        f("security", "high", "x", 2, 0.8, "두 번째"),
    ]
    out = aggregate(dup, order=ORDER)
    assert len(out) == 1
    assert out[0]["merged_from"] == 2
    assert out[0]["sources"] == ["security"], "출처는 하나인데 합친 건 둘이다"


def test_출처가_없으면_무엇을_고칠지_말하며_터진다():
    """옛 `evals/runs/*.json` 에 `agent_type` 이 없다 — 그게 이 경로의 실제 입력이다.
    날 것의 `ValidationError` 는 "왜"를 안 말한다."""
    no_source = [{k: v for k, v in MEASURED[0].items() if k != "agent_type"}]
    with pytest.raises(ValueError, match="agent_type"):
        aggregate(no_source, order=ORDER)


# ══════════════════════════════════════════════════════════════════════
# 스키마 — INV-3 이 병합 뒤에도 사는가
# ══════════════════════════════════════════════════════════════════════


def test_합친_뒤에도_INV3_이_산다():
    """`MergedFinding` 생성자를 지나므로 `line >= 1` · `0 <= confidence <= 1` 이 재확인된다."""
    for m in aggregate(MEASURED, order=ORDER):
        assert m["rationale"].strip()
        assert 0.0 <= m["confidence"] <= 1.0
        assert m["line"] >= 1


def test_빈_입력은_빈_출력이다():
    """넷이 다 죽었거나 넷 다 찾은 게 없을 때. 터지면 안 된다 —
    그 구분은 `failed_agents` 가 하고, 애그리게이터의 일이 아니다."""
    assert aggregate([], order=ORDER) == []
