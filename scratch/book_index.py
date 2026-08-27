"""AI-Agents-in-Depth-ko.pdf 에서 절 목록을 뽑는다.

왜 목록을 파일로 박제하지 않나 — 박제하면 낡는다. 30초면 다시 뽑히므로 그때그때 뽑는다.

⚠️ **쪽번호가 둘이다.** 책에 인쇄된 번호(인용에 쓰는 것)와 PDF 뷰어의 번호가 다르다:
        PDF 쪽 = 인쇄 쪽 + 8
   M6-PLAN 의 "인쇄 200" 은 PDF 208 쪽이다. 아래 출력은 둘 다 찍는다.

사용:
    uv run python scratch/book_index.py            # 전체 절 목록
    uv run python scratch/book_index.py 2.4        # 2.4 로 시작하는 절만
    uv run python scratch/book_index.py --page 63  # PDF 63쪽 본문 출력
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF = ROOT / "AI-Agents-in-Depth-ko.pdf"
TXT = Path("/tmp/ai-agents-in-depth.txt")
OFFSET = 8  # PDF 쪽 = 인쇄 쪽 + OFFSET


def pages() -> list[str]:
    if not TXT.exists():
        subprocess.run(["pdftotext", "-layout", str(PDF), str(TXT)], check=True)
    return TXT.read_text().split("\f")


def main() -> None:
    args = sys.argv[1:]
    pg = pages()

    if args and args[0] == "--page":
        i = int(args[1]) - 1
        print(f"=== PDF {i + 1} (인쇄 {i + 1 - OFFSET}) ===\n{pg[i]}")
        return

    prefix = args[0] if args else ""
    seen: set[str] = set()
    for i, page in enumerate(pg):
        for m in re.finditer(r"^\s*(\d{1,2}\.\d(?:\.\d)?)\s+(\S.{2,55})$", page, re.M):
            key = m.group(1)
            if key in seen or not key.startswith(prefix):
                continue
            seen.add(key)
            print(f"PDF {i + 1:>3} (인쇄 {i + 1 - OFFSET:>3})  {key:8} {m.group(2).strip()}")


if __name__ == "__main__":
    main()
