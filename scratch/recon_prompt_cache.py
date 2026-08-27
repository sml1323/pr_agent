"""프록시에서 프롬프트 캐시가 먹는가 — 호출 2번으로 확인한다.

왜 재나 (2026-08-27):
    책 2.3.4(인쇄 53) 는 "프롬프트 순서는 의미 논리보다 캐시 경제성에 좌우된다"고 한다.
    그 판단을 M6-3a 의 조립 순서에 반영하려는데, **전제가 확인 안 됐다.**

    cached_tokens=1792/2049 (87%) 는 M0 실측(2026-07-28)이고 그때는 **진짜 OpenAI API** 였다.
    2026-08-14 에 로컬 OAuth 프록시로 갈아탔고, 프록시가 캐시를 통과시키는지는 아무도 안 봤다.
    prompt_2x2.json 에도 input_tokens 만 있고 cached 는 안 찍혀 있다.

    안 먹으면 조립 순서 판단은 통째로 무의미해진다 → TODO 하나가 사라진다.

무엇을 보나:
    같은 접두부로 두 번 부르고 usage.input_tokens_details.cached_tokens 를 본다.
    캐시는 **접두부 매칭**이라 1회차는 miss, 2회차부터 적중해야 한다.
    ⚠️ OpenAI 는 캐시 최소 길이가 있다(보통 1024 토큰) — 짧은 프롬프트로 재면
       "안 먹는다"가 아니라 "짧아서 안 먹는다"를 재게 된다. 그래서 진짜 프롬프트를 쓴다.
"""

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv()

from backend.agents.base import MODEL, SYSTEM_PROMPT, build_user_message  # noqa: E402
from backend.agents.schema import ReviewResult  # noqa: E402


def usage_dict(u) -> dict:
    """SDK 버전마다 usage 모양이 달라서 통째로 펴서 본다."""
    if hasattr(u, "model_dump"):
        return u.model_dump()
    return json.loads(json.dumps(u, default=lambda o: getattr(o, "__dict__", str(o))))


def cached_of(d: dict) -> int:
    det = d.get("input_tokens_details") or d.get("prompt_tokens_details") or {}
    if isinstance(det, dict):
        return int(det.get("cached_tokens") or 0)
    return 0


def call(diff_text: str, label: str) -> dict:
    client = OpenAI()
    t0 = time.perf_counter()
    r = client.responses.parse(
        model=MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_message(diff_text)},
        ],
        text_format=ReviewResult,
    )
    dt = time.perf_counter() - t0
    u = usage_dict(r.usage)
    print(f"[{label}] {dt:6.2f}s   input {u.get('input_tokens')}   "
          f"cached {cached_of(u)}   output {u.get('output_tokens')}")
    return u


def main() -> None:
    diff = (ROOT / "fixtures" / "sample.diff").read_text()
    print(f"모델 {MODEL}   system 프롬프트 {len(SYSTEM_PROMPT)}자\n")

    u1 = call(diff, "1회차")
    u2 = call(diff, "2회차")

    print("\n--- usage 전체 (1회차) ---")
    print(json.dumps(u1, ensure_ascii=False, indent=2))

    c1, c2 = cached_of(u1), cached_of(u2)
    inp = u2.get("input_tokens") or 0
    print("\n=== 판정 ===")
    if c2 > 0:
        print(f"✅ 캐시가 먹는다 — 2회차 {c2}/{inp} ({c2 / max(inp, 1):.0%})")
        print("   → 조립 순서(정적 앞 · 동적 뒤)가 M6-3a 의 설계 제약이 된다. 책 2.3.4 적용.")
    elif "input_tokens_details" not in u1 and "prompt_tokens_details" not in u1:
        print("⚠️ usage 에 캐시 필드 자체가 없다 — 프록시가 그 정보를 안 내려준다.")
        print("   '캐시가 안 된다'가 아니라 '잴 수 없다'다. 위 usage 전체를 보고 판단할 것.")
    else:
        print(f"❌ 캐시 미적중 (1회차 {c1} · 2회차 {c2})")
        print("   → 조립 순서를 캐시 근거로 정할 수 없다. 그 판단은 M6-3a 에서 뺀다.")


if __name__ == "__main__":
    main()
