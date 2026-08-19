#!/usr/bin/env python3
"""학습 사이클(읽기 → 만지기 → 적기)이 레슨마다 어디까지 왔는지 파일로 판정한다.

LLM 이 "있는 것 같다" 고 말하지 못하게 하는 게 이 스크립트의 존재 이유다.
판정 근거는 전부 파일 시스템과 NOTEBOOK.md 의 실제 내용이다.

    python3 check.py            전체 표
    python3 check.py 3          3번 레슨만 자세히
    python3 check.py --json     기계용 출력
    python3 check.py --check-only   NOTEBOOK.md 링크를 고치지 않는다

기본 동작에 NOTEBOOK.md 의 산출물 링크 줄(`> 📄 ... · 🎮 ...`) 갱신이 포함된다.
그 한 줄 말고는 아무것도 건드리지 않는다 — 사용자가 쓴 본문은 이 스크립트의 소관이 아니다.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]      # .claude/skills/learn-check/scripts/ → 레포 루트
LEARNING = ROOT / "learning"
LESSONS = LEARNING / "lessons"
SIMS = LEARNING / "sims"
NOTEBOOK = LEARNING / "NOTEBOOK.md"

# NOTEBOOK.md 의 각 레슨 섹션에 있어야 하는 칸들.
# 이 라벨이 바뀌면 여기도 바꿔야 한다 — 그래서 한 곳에만 적는다.
FIELDS = [
    "한 문장으로",
    "내 말로 (3줄 이내)",
    "시뮬에서 틀린 예측 / 놀란 것",
    "우리 코드 어디에 있나",
]

LINK_PREFIX = "> 📄"        # 스크립트가 관리하는 줄의 표식


def num_of(path: Path):
    """0001-foo.html → 1. 번호로 시작하지 않으면 None."""
    m = re.match(r"^(\d+)-", path.name)
    return int(m.group(1)) if m else None


def title_of(html_path: Path) -> str:
    try:
        text = html_path.read_text(encoding="utf-8", errors="replace")[:4000]
    except OSError:
        return ""
    m = re.search(r"<title>(.*?)</title>", text, re.S)
    if not m:
        return ""
    t = re.sub(r"\s+", " ", m.group(1)).strip()
    # "Lesson 01 — 제목" 에서 접두사를 떼어 표를 좁게 유지한다
    return re.sub(r"^(Lesson|Sim)\s*\d+\s*[—-]\s*", "", t)


def scan(directory: Path):
    """번호 → 파일 경로. 같은 번호가 둘이면 이름순 첫 번째."""
    out = {}
    if not directory.is_dir():
        return out
    for p in sorted(directory.glob("*.html")):
        n = num_of(p)
        if n is not None and n not in out:
            out[n] = p
    return out


def parse_notebook(text: str):
    """레슨 번호 → {'span': (start, end), 'header_end': int, 'filled': {필드: bool}}

    섹션 경계는 `## Lesson NN` 부터 다음 `## ` 또는 `---` 앞까지.
    칸이 채워졌는지는 라벨 다음 콜론부터 다음 라벨까지에 공백 아닌 글자가 있는지로 본다.
    """
    sections = {}
    heads = list(re.finditer(r"^##\s+Lesson\s+(\d+)\b.*$", text, re.M))
    for i, h in enumerate(heads):
        n = int(h.group(1))
        start = h.start()
        # 다음 레슨 헤딩 또는 다른 ## 섹션까지
        nxt = heads[i + 1].start() if i + 1 < len(heads) else None
        other = re.search(r"^##\s+(?!Lesson\s+\d)", text[h.end():], re.M)
        other_pos = h.end() + other.start() if other else None
        end = min(x for x in (nxt, other_pos, len(text)) if x is not None)

        body = text[h.end():end]
        filled = {}
        for j, f in enumerate(FIELDS):
            pat = re.escape("**" + f + "**") + r"\s*:"
            m = re.search(pat, body)
            if not m:
                filled[f] = False
                continue
            # 다음 라벨(어느 것이든) 또는 섹션 끝까지
            rest = body[m.end():]
            nxt_label = re.search(r"^\*\*[^*]+\*\*\s*:", rest, re.M)
            chunk = rest[:nxt_label.start()] if nxt_label else rest
            chunk = chunk.replace("---", " ")
            filled[f] = bool(chunk.strip())
        sections[n] = {"span": (start, end), "header_end": h.end(), "filled": filled}
    return sections


def build_link_line(n, lesson, sim):
    parts = []
    if lesson:
        parts.append(f"📄 [레슨](lessons/{lesson.name})")
    else:
        parts.append("📄 레슨 없음")
    if sim:
        parts.append(f"🎮 [시뮬](sims/{sim.name})")
    else:
        parts.append("🎮 시뮬 없음")
    return "> " + " · ".join(parts)


def sync_links(text, sections, lessons, sims):
    """각 레슨 섹션 제목 바로 아래의 링크 줄을 만들거나 갱신한다.

    LINK_PREFIX 로 시작하는 줄만 건드린다. 사용자가 쓴 본문은 손대지 않는다.
    뒤에서부터 고쳐야 앞쪽 오프셋이 안 밀린다.
    """
    changed = []
    for n in sorted(sections, reverse=True):
        sec = sections[n]
        want = build_link_line(n, lessons.get(n), sims.get(n))
        h_end = sec["header_end"]
        after = text[h_end:sec["span"][1]]

        m = re.match(r"\n*(" + re.escape(LINK_PREFIX) + r"[^\n]*)", after)
        if m:
            if m.group(1) == want:
                continue
            s = h_end + m.start(1)
            e = h_end + m.end(1)
            text = text[:s] + want + text[e:]
        else:
            text = text[:h_end] + "\n\n" + want + text[h_end:]
        changed.append(n)
    return text, sorted(changed)


def main():
    args = [a for a in sys.argv[1:]]
    as_json = "--json" in args
    check_only = "--check-only" in args
    only = None
    for a in args:
        if not a.startswith("-") and a.isdigit():
            only = int(a)

    lessons, sims = scan(LESSONS), scan(SIMS)
    nb_text = NOTEBOOK.read_text(encoding="utf-8") if NOTEBOOK.exists() else ""
    sections = parse_notebook(nb_text)

    # 링크 동기화 — 검사보다 먼저 해서 결과가 최신 상태를 반영하게 한다
    link_changes = []
    if nb_text and not check_only:
        new_text, link_changes = sync_links(nb_text, sections, lessons, sims)
        if new_text != nb_text:
            NOTEBOOK.write_text(new_text, encoding="utf-8")
            nb_text = new_text
            sections = parse_notebook(nb_text)

    rows = []
    for n in sorted(set(lessons) | set(sims) | set(sections)):
        sec = sections.get(n)
        filled = sec["filled"] if sec else {f: False for f in FIELDS}
        rows.append({
            "n": n,
            "lesson": lessons.get(n).name if n in lessons else None,
            "sim": sims.get(n).name if n in sims else None,
            "in_notebook": sec is not None,
            "filled": filled,
            "filled_count": sum(filled.values()),
            "title": title_of(lessons[n]) if n in lessons else "",
        })

    if only is not None:
        rows = [r for r in rows if r["n"] == only]
        if not rows:
            print(f"레슨 {only:04d} 은 아직 아무것도 없다.")
            print("  → /mattpocock-skills:teach 로 레슨부터 만들 것 (사용자가 직접 쳐야 하는 명령)")
            return 1

    if as_json:
        print(json.dumps({"rows": rows, "link_changes": link_changes},
                         ensure_ascii=False, indent=2))
        return 0

    ok = lambda b: "✅" if b else "⬜"

    if only is None:
        print("레슨   읽기  만지기  적기      제목")
        print("─" * 62)
        for r in rows:
            note = f"{r['filled_count']}/4"
            print(f"{r['n']:04d}   {ok(r['lesson'])}    {ok(r['sim'])}    "
                  f"{ok(r['filled_count'] == len(FIELDS))} {note}   {r['title'][:26]}")
        done = sum(1 for r in rows
                   if r["lesson"] and r["sim"] and r["filled_count"] == len(FIELDS))
        print("─" * 62)
        print(f"3단계 모두 끝난 레슨: {done}/{len(rows)}")
    else:
        r = rows[0]
        print(f"Lesson {r['n']:04d} — {r['title']}\n")
        print(f"  읽기   {ok(r['lesson'])}  {r['lesson'] or 'learning/lessons/ 에 파일 없음'}")
        print(f"  만지기 {ok(r['sim'])}  {r['sim'] or 'learning/sims/ 에 파일 없음'}")
        print(f"  적기   {ok(r['filled_count'] == len(FIELDS))}  "
              f"NOTEBOOK.md {r['filled_count']}/{len(FIELDS)} 칸")
        if r["in_notebook"]:
            for f in FIELDS:
                print(f"           {ok(r['filled'][f])} {f}")
        else:
            print("           NOTEBOOK.md 에 이 레슨 섹션이 없다")

    if link_changes:
        print(f"\n(NOTEBOOK.md 링크 줄 갱신: "
              f"{', '.join(f'{n:04d}' for n in link_changes)})")

    # 종료 코드로도 알린다 — 다른 스크립트가 이걸 게이트로 쓸 수 있게
    incomplete = [r for r in rows
                  if not (r["lesson"] and r["sim"] and r["filled_count"] == len(FIELDS))]
    return 1 if incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
