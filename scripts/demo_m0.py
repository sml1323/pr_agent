#!/usr/bin/env python
"""M0 데모 — diff 하나 → Finding JSON.

    uv run python scripts/demo_m0.py fixtures/sample.diff security

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

# ⚠️ 토큰 필드 이름 (2026-08-28에 실제로 터진 것):
#    Responses API 는 input_tokens / output_tokens 다.
#    Chat Completions 의 prompt_tokens / completion_tokens 가 아니다.
#    M3 에서 record_event(tokens) 를 붙일 때 같은 자리에서 또 틀릴 수 있다.
from openai.types.responses import ResponseUsage  # noqa: E402

from backend.agents.base import review_diff  # noqa: E402


def _tokens(usage: ResponseUsage | None) -> str:
    """토큰 줄. usage 가 없을 수도 있다 — 없으면 0 으로 꾸미지 않고 모른다고 쓴다."""
    if usage is None:
        return "모름 (usage 없음)"
    return f"{usage.input_tokens} in / {usage.output_tokens} out"


def main() -> int:
    # ⚠️ 인자가 둘이 됐다 (2026-08-28, M6-4). 기본값을 안 주는 건 의도다 —
    #    M6 부터 프롬프트가 관점별로 갈려서, 어느 관점으로 잰 결과인지 모르면
    #    이 데모의 출력이 무슨 뜻인지 말할 수 없다.
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <diff 파일> <security|quality|testing|docs>",
              file=sys.stderr)
        return 2

    diff_path = Path(sys.argv[1])
    # ⚠️ `sys.argv` 는 str 이라 그대로는 AgentType 이 아니다.
    #    이 if 문이 **타입 좁히기(narrowing)** 를 한다 — 통과한 뒤엔 검사기도
    #    이 값이 넷 중 하나임을 안다. 검사기를 위한 게 아니라, 사용자가 오타를
    #    쳤을 때 KeyError 대신 사람이 읽을 메시지를 주려는 것이다.
    agent_type = sys.argv[2]
    if agent_type not in ("security", "quality", "testing", "docs"):
        print(f"모르는 agent_type: {agent_type}", file=sys.stderr)
        return 2
    if not diff_path.is_file():
        print(f"파일이 없다: {diff_path}", file=sys.stderr)
        return 2

    findings, usage = review_diff(diff_path.read_text(encoding="utf-8"), agent_type)

    # ① Finding JSON 배열
    print(json.dumps(
        [f.model_dump() for f in findings],
        ensure_ascii=False,
        indent=2,
    ))

    # ─── 완료 판정 도우미 ───────────────────────────────────────
    print("\n" + "─" * 62, file=sys.stderr)

    if not findings:
        print("⚠️  finding 0개. 심어둔 SQL 인젝션을 못 찾았거나,", file=sys.stderr)
        print("   프롬프트 인젝션이 성공했을 수 있다.", file=sys.stderr)
        print(f"토큰: {_tokens(usage)}", file=sys.stderr)
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
    print(f"   토큰         : {_tokens(usage)}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
