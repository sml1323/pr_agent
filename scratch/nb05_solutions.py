"""Notebook 05 정답 — **검수 전용.** 노트북에는 절대 안 들어간다.

검수기가 `ast` 로 같은 이름의 최상위 def 를 찾아 스텁 본문을 바꿔치기한다.
그래서 규칙 셋:
  · 최상위 `def` 만
  · 기본 인자에 노트북 전역을 쓰지 않는다
  · 노트북이 먼저 정의하는 전역(`SEVERITY_RANK`)만 본문에서 참조한다

⚠️ `my_dedup_key` 는 (c) 정규화 안으로 썼다. 이건 **하나의 답**이지 유일한 답이 아니다 —
   학습자가 (a)나 (b)를 골라도 §6 의 세 검사는 통과한다. 검수기가 보는 건
   "정답을 넣으면 노트북이 끝까지 도는가"뿐이다.
"""


def my_dedup_key(f):
    """(c) — 표기 흔들림까지 흡수한다.

    ⚠️ 부분 문자열 매칭은 열지 않는다. 복수형 `s` 만 떼고, 구분자와 대소문자를 통일한다.
       (`sql-injection` 이 `missing-sql-injection-tests` 와 붙으면 다른 결함 둘이 하나가 된다)
    """
    cat = f["category"].strip().lower()
    for sep in (" ", "_"):
        cat = cat.replace(sep, "-")
    while "--" in cat:
        cat = cat.replace("--", "-")
    if cat.endswith("s") and not cat.endswith("ss"):
        cat = cat[:-1]
    return (f["file"], cat)


def my_pick_representative(group, order):
    """지금 코드와 같은 규칙 — 대표 하나를 통째로. 필드를 섞지 않는다.

    정렬 키 넷 전부 결정성을 위해 있다. 하나라도 빠지면 §6 의 셔플 검사가 잡는다.
    """
    rank = {a: i for i, a in enumerate(order)}
    return min(
        group,
        key=lambda f: (
            SEVERITY_RANK[f["severity"]],  # noqa: F821 — 노트북이 먼저 정의한다
            -f["confidence"],
            rank.get(f.get("agent_type", ""), len(order)),
            f["line"],
            f["rationale"],
        ),
    )
