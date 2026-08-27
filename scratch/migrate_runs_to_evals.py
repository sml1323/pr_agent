"""일회용 — 2026-08-25 의 15판을 `evals/runs/` 로 옮긴다.

왜 옮기나 ─────────────────────────────────────────────────────────────
그 15판이 `scratch/` 에 있는데 `scratch/` 는 `.gitignore` 대상이다.
2026-08-27 에 자를 두 번 고치고도 호출 없이 다시 잰 건 그 파일이 **우연히 로컬에
남아 있어서**였다 — 새 세션이나 다른 머신에는 없다. 그 우연을 없앤다.

무엇이 어디로 ─────────────────────────────────────────────────────────
    scratch/prompt_2x2.json      (recon_prompt_2x2.py, 2026-08-25)
      with_tag_rule/clean     → sample          · variant=orig
      with_tag_rule/injected  → sample_injected · variant=orig
      no_tag_rule/clean       → sample          · variant=no-tag-rule
      no_tag_rule/injected    → sample_injected · variant=no-tag-rule
    scratch/prompt_variance.json (recon_prompt_variance.py, 2026-08-25)
      runs                    → sample          · variant=orig

⚠️ `variant` 를 정확히 나눠야 하는 이유 — `recon_prompt_2x2.py:32` 를 보면
   `with_tag_rule` 는 `SYSTEM_PROMPT` **원본 그대로**이고 `no_tag_rule` 은
   거기서 `TAG_RULE_LINE` 한 줄을 뺀 것이다. **다른 프롬프트다.**
   `recon_prompt_variance.py` 는 `review_diff()` 를 부르므로 역시 원본 = orig.
   → `with_tag_rule/clean` + `variance` + 2026-08-27 의 run 은 **같은 조건**이고,
     합치면 sample/orig 이 9판이 된다.

⚠️ status 는 전부 "ok" 다. 옛 스크립트는 실패한 판을 파일에 안 남겼다
   (D7 이 그 뒤에 생겼다). 그래서 이 파일들엔 refused/error 가 존재하지 않는다 —
   **"실패가 없었다"가 아니라 "기록이 없다"** 이고, 그 사실을 meta 에 남긴다.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.eval_prompt import run_identity  # noqa: E402

SCRATCH = ROOT / "scratch"
RUNS = ROOT / "evals" / "runs"
MEASURED_AT = "2026-08-25"

ORIG = "backend/agents/base.py:SYSTEM_PROMPT"
NO_TAG = "backend/agents/base.py:SYSTEM_PROMPT − TAG_RULE_LINE"

# (원본 셀, 픽스처, variant, prompt_source)
CELLS = [
    ("with_tag_rule/clean", "sample", "orig", ORIG),
    ("with_tag_rule/injected", "sample_injected", "orig", ORIG),
    ("no_tag_rule/clean", "sample", "no-tag-rule", NO_TAG),
    ("no_tag_rule/injected", "sample_injected", "no-tag-rule", NO_TAG),
]

NOTE = (
    "recon 스크립트가 만든 것을 옮겼다(scratch/migrate_runs_to_evals.py). "
    "status 는 전부 ok — 옛 스크립트는 실패한 판을 기록하지 않았다(D7 이 뒤에 생겼다). "
    "'실패가 없었다'가 아니라 '기록이 없다'."
)


def to_run(raw: dict, measured_at: str) -> dict:
    """옛 판 하나 → 지금 형식. 있는 필드만 옮기고 없는 걸 지어내지 않는다.

    판마다 `measured_at` 을 박는다 — 같은 조건이라도 **언제 잰 것인지는 남겨야** 한다.
    (같은 조건을 한 파일로 합치기 때문에, 파일 단위 날짜만으로는 출처를 잃는다.)
    """
    usage = {
        k: raw[k]
        for k in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens")
        if k in raw
    }
    out: dict = {"status": "ok", "measured_at": measured_at, "findings": raw["findings"]}
    if "elapsed" in raw:
        out["elapsed"] = raw["elapsed"]
    if usage:
        out["usage"] = usage
    return out


def write(fixture: str, variant: str, prompt_source: str, runs: list[dict], src: str) -> Path:
    dates = sorted({r["measured_at"] for r in runs})
    name, meta = run_identity(
        fixture, len(runs), variant=variant, prompt_source=prompt_source,
        measured_at=dates[-1],
    )
    meta["spans"] = dates          # 이 파일에 섞인 측정일. 판마다도 박혀 있다
    meta["migrated_from"] = src
    meta["note"] = NOTE
    path = RUNS / name
    path.write_text(
        json.dumps({"meta": meta, "fixture": fixture, "runs": runs},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  {src:<32} → {name}  ({len(runs)}판)")
    return path


def main() -> None:
    RUNS.mkdir(parents=True, exist_ok=True)

    two = json.loads((SCRATCH / "prompt_2x2.json").read_text(encoding="utf-8"))
    var = json.loads((SCRATCH / "prompt_variance.json").read_text(encoding="utf-8"))

    # sample/orig 은 **세 출처**가 합쳐진다:
    #   2x2 의 with_tag_rule/clean (2026-08-25) + variance (2026-08-25)
    #   + 2026-08-27 에 eval_prompt.py 로 돌린 3판 (이미 evals/runs/ 에 있다)
    # 셋 다 model·프롬프트·픽스처가 같다 — **날짜는 조건이 아니라 출처다.**
    buckets: dict[tuple[str, str], list[dict]] = {}
    for cell, fixture, variant, _src in CELLS:
        buckets.setdefault((fixture, variant), []).extend(
            to_run(r, MEASURED_AT) for r in two["cells"][cell]
        )
    buckets[("sample", "orig")].extend(to_run(r, MEASURED_AT) for r in var["runs"])

    # 오늘 것을 이어붙이고 옛 이름 파일은 지운다 (variant 슬롯이 없던 이름이다).
    today = RUNS / "sample__luna__k3.json"
    if today.exists():
        d = json.loads(today.read_text(encoding="utf-8"))
        stamped = [{**r, "measured_at": d["meta"]["measured_at"]} for r in d["runs"]]
        buckets[("sample", "orig")].extend(stamped)
        today.unlink()
        print(f"  {today.name} 흡수 후 삭제 ({len(stamped)}판)")

    print("이사:")
    for (fixture, variant), runs in sorted(buckets.items()):
        prompt_source = ORIG if variant == "orig" else NO_TAG
        write(fixture, variant, prompt_source, runs, "scratch/prompt_*.json")


if __name__ == "__main__":
    main()
