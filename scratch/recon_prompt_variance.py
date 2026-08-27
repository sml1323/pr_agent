"""같은 diff · 같은 프롬프트를 N번 돌려 무엇이 흔들리는지 잰다.

왜: Lesson 12 의 전제("프롬프트에는 assert 를 못 쓴다")가 참인지 실측하고,
    RESOURCES.md Gaps 의 "정상 LLM 응답의 지연 분포"(M6 타임아웃 값의 재료)를 메운다.

산출물: scratch/prompt_variance.json  — code-trace 가 이 파일의 숫자만 쓴다.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.agents.base import MODEL, review_diff  # noqa: E402

DIFF_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "sample.diff"
OUT_PATH = Path(__file__).resolve().parent / "prompt_variance.json"
N = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def main() -> None:
    diff_text = DIFF_PATH.read_text()
    runs = []

    for i in range(N):
        t0 = time.perf_counter()
        result, usage = review_diff(diff_text)
        elapsed = time.perf_counter() - t0

        # Responses API 필드명 — prompt/completion 이 아니라 input/output.
        details = getattr(usage, "output_tokens_details", None)
        reasoning = getattr(details, "reasoning_tokens", None)

        run = {
            "i": i + 1,
            "elapsed": round(elapsed, 2),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
            "reasoning_tokens": reasoning,
            "findings": [
                {
                    "agent_type": f.agent_type,
                    "severity": f.severity,
                    "category": f.category,
                    "file": f.file,
                    "line": f.line,
                    "confidence": f.confidence,
                    "rationale": f.rationale,
                }
                for f in result.findings
            ],
        }
        runs.append(run)

        print(f"--- run {i + 1}/{N} · {elapsed:.2f}s · findings {len(result.findings)} "
              f"· in {run['input_tokens']} / out {run['output_tokens']} "
              f"(reasoning {reasoning})")
        for f in result.findings:
            print(f"    [{f.severity:13}] {f.category:28} {f.file}:{f.line} conf={f.confidence}")

    OUT_PATH.write_text(json.dumps({"model": MODEL, "diff": DIFF_PATH.name, "runs": runs},
                                   ensure_ascii=False, indent=2))
    print(f"\n→ {OUT_PATH}")

    # 무엇이 흔들렸나 — 세 축을 따로 센다.
    counts = [len(r["findings"]) for r in runs]
    keys = [sorted({(f["file"], f["line"], f["category"]) for f in r["findings"]}) for r in runs]
    sev = [sorted(f["severity"] for f in r["findings"]) for r in runs]
    print(f"\nfindings 개수 : {counts}   {'흔들림' if len(set(counts)) > 1 else '동일'}")
    print(f"(file,line,cat): {'동일' if all(k == keys[0] for k in keys) else '흔들림'}")
    print(f"severity 묶음  : {'동일' if all(s == sev[0] for s in sev) else '흔들림'}")
    print(f"지연           : {[r['elapsed'] for r in runs]}")


if __name__ == "__main__":
    main()
