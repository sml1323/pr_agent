"""노트북 04 정답 — 검수 전용. 노트북에는 절대 들어가지 않는다.

검수기가 ast 로 같은 이름의 스텁 본문을 이걸로 바꿔치기해서 실행한다.
규칙: 최상위 def 만 · 기본 인자에 노트북 전역 금지 · np/rng/AGENTS 는 노트북이 정의한다.
"""


def count_mismatch(findings, called_agent):
    """후보 (a) — 출처가 틀린 것만 센다. D3 가 이 필드를 '출처'로 확정했으므로."""
    typed = [f for f in findings if "agent_type" in f]
    bad = sum(1 for f in typed if f["agent_type"] != called_agent)
    return bad, len(typed)


def g2_verdict(findings, failed, key):
    """후보 (a) — failed 를 먼저 본다. 선별 원칙상 '모르는데 안다고' 하지 않으려면."""
    sources = {f[key] for f in findings}
    out = {}
    for a in AGENTS:  # noqa: F821  (노트북이 정의한다)
        if a in failed:
            out[a] = "죽음"
        elif a in sources:
            out[a] = "찾음"
        else:
            out[a] = "없음"
    return out


def one_trial(rng, m, n_dead, p_find):
    """후보 (a) — 나머지 셋 중 균등하게. m 하나만 손잡이로 남기려면 이것뿐이다."""
    agents = list(AGENTS)  # noqa: F821
    dead = set(rng.choice(agents, size=n_dead, replace=False).tolist()) if n_dead else set()
    findings = []
    for a in agents:
        if a in dead:
            continue
        if rng.random() >= p_find:
            continue
        if rng.random() < m:
            others = [x for x in agents if x != a]
            said = str(rng.choice(others))
        else:
            said = a
        findings.append({"by_code": a, "by_model": said})
    return dead, findings
