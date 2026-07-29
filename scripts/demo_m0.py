#!/usr/bin/env python
"""M0 데모 — diff 하나 → Finding JSON.

    uv run python scripts/demo_m0.py fixtures/sample.diff

완료 판정 (docs/03-build-plan.md:123):
  ① Finding JSON 배열이 표준출력에 뜬다
  ② 모든 항목에 confidence·rationale·file·line 이 비어있지 않다
  ③ rationale 이 "이거 좀 이상함"이 아니라 근거를 인용한다
  ④ confidence 가 항상 같은 값이면 실패
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.agents.base import review_diff  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <diff 파일>", file=sys.stderr)
        return 2

    diff_path = Path(sys.argv[1])
    if not diff_path.is_file():
        print(f"파일이 없다: {diff_path}", file=sys.stderr)
        return 2

    result, usage = review_diff(diff_path.read_text(encoding="utf-8"))

    # ① Finding JSON 배열
    print(json.dumps(
        [f.model_dump() for f in result.findings],
        ensure_ascii=False,
        indent=2,
    ))

    # ─── 완료 판정 도우미 ───────────────────────────────────────
    findings = result.findings
    print("\n" + "─" * 62, file=sys.stderr)

    if not findings:
        print("⚠️  finding 0개. 심어둔 SQL 인젝션을 못 찾았거나,", file=sys.stderr)
        print("   프롬프트 인젝션이 성공했을 수 있다.", file=sys.stderr)
        print(f"토큰: {usage.prompt_tokens} in / {usage.completion_tokens} out", file=sys.stderr)
        return 1

    for f in findings:
        print(f"  {f.severity:<14} conf={f.confidence:<5} "
              f"{f.file}:{f.line}  [{f.category}]", file=sys.stderr)

    print("─" * 62, file=sys.stderr)

    # ② 빈 필드
    empty = [
        (i, name)
        for i, f in enumerate(findings)
        for name in ("file", "rationale")
        if not str(getattr(f, name)).strip()
    ]
    print(f"② 빈 필드      : {'FAIL ' + str(empty) if empty else 'PASS'}", file=sys.stderr)

    # ④ confidence 분포 — 항상 같은 값이면 게이트가 죽는다
    confs = [f.confidence for f in findings]
    distinct = len(set(confs))
    verdict = "PASS" if distinct > 1 else ("FAIL — 전부 같은 값" if len(confs) > 1 else "판정 불가(1개)")
    print(f"④ confidence   : {verdict}  {sorted(confs)}", file=sys.stderr)

    sev = Counter(f.severity for f in findings)
    print(f"   severity    : {dict(sev)}", file=sys.stderr)
    print(f"   토큰         : {usage.prompt_tokens} in / {usage.completion_tokens} out", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
