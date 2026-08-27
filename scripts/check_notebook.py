"""노트북 검수 — 사람에게 내보내기 전에 반드시 통과시킨다.

왜 필요한가 (2026-08-25, 01번을 깨진 채로 내보내고 나서 만듦):
    nbformat.validate() 는 **스키마만** 본다. `source` 가 리스트냐 문자열이냐,
    필수 키가 있느냐까지다. **코드가 파싱되는지는 안 본다.**
    실제로 source 를 `.split("\\n")` 으로 만들어 개행이 다 빠졌는데
    validate() 는 통과했고, 사람이 열었을 때 SyntaxError 가 났다.

검사 셋:
    ① 스키마        nbformat.validate
    ② 구문          코드 셀마다 compile() — 개행 유실·오타를 여기서 잡는다
    ③ 실행(선택)    --solutions 로 TODO 정답 구현을 주입해 끝까지 돌린다
                    TODO(human) 이 `...` 스텁이라 그냥 돌리면 반드시 실패하므로,
                    "정답을 넣으면 도는가"를 확인하는 것이 유일하게 의미 있는 실행 검사다.

사용:
    uv run python scripts/check_notebook.py learning/notebooks/01-*.ipynb
    uv run python scripts/check_notebook.py <nb> --solutions scratch/nb01_solutions.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import nbformat


def cell_src(cell) -> str:
    """source 는 str 이거나 list[str] 이다. 둘 다 받는다."""
    s = cell.get("source", "")
    return s if isinstance(s, str) else "".join(s)


def check_schema(nb, path: Path) -> list[str]:
    try:
        nbformat.validate(nb)
    except Exception as e:  # noqa: BLE001 — 어떤 예외든 리포트로 바꾼다
        return [f"스키마: {e}"]
    return []


def check_syntax(nb) -> list[str]:
    """코드 셀마다 compile(). 개행 유실이 여기서 걸린다."""
    errs = []
    for i, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        src = cell_src(cell)
        try:
            compile(src, f"<cell {i}>", "exec")
        except SyntaxError as e:
            head = src.splitlines()[0][:70] if src.strip() else "(빈 셀)"
            errs.append(f"셀 {i} 구문오류 {e.msg} (line {e.lineno}) — 첫 줄: {head!r}")
    return errs


def check_newlines(nb) -> list[str]:
    """개행 유실 조기 경보 — 한 줄인데 이상하게 긴 셀을 의심한다.

    구문검사가 이미 대부분 잡지만, 마크다운 셀은 compile 이 안 되므로 이쪽이 유일한 그물이다.
    """
    errs = []
    for i, cell in enumerate(nb.cells):
        src = cell_src(cell)
        if not src.strip():
            continue
        lines = src.splitlines()
        if len(lines) == 1 and len(src) > 200:
            errs.append(f"셀 {i}({cell.cell_type}) 개행 없이 {len(src)}자 — source 가 붙었을 가능성")
        # 리스트 형태면 각 원소가 개행으로 끝나야 한다 (마지막 줄 제외)
        s = cell.get("source")
        if isinstance(s, list) and len(s) > 1:
            bad = sum(1 for x in s[:-1] if not x.endswith("\n"))
            if bad:
                errs.append(f"셀 {i}({cell.cell_type}) list 원소 {bad}개가 '\\n' 으로 안 끝난다")
    return errs


def check_todos(nb) -> list[str]:
    """TODO(human) 이 실제로 비어 있는지 — 답을 실수로 채워 내보내는 사고 방지."""
    warns = []
    for i, cell in enumerate(nb.cells):
        if cell.cell_type != "code":
            continue
        src = cell_src(cell)
        if "TODO(human)" in src and "..." not in src:
            warns.append(f"셀 {i} 에 TODO(human) 이 있는데 `...` 스텁이 없다 — 답이 채워졌나?")
    return warns


def _parse_solutions(src: str) -> dict[str, str]:
    """.py 에서 최상위 함수 정의를 {이름: 소스} 로 뽑는다."""
    import ast

    lines = src.splitlines(keepends=True)
    return {
        n.name: "".join(lines[n.lineno - 1 : n.end_lineno])
        for n in ast.parse(src).body
        if isinstance(n, ast.FunctionDef)
    }


def _fill_stubs(cell_source: str, sols: dict[str, str]) -> str:
    """`def f(...): ...` 스텁을 정답 구현으로 **바꿔치기**한다.

    ⚠️ 뒤에 새 셀로 덧붙이면 안 된다 — TODO 셀은 스텁을 정의하고 **같은 셀 안에서
    바로 호출**하므로, 정답이 그 뒤에 와봐야 이미 늦다 (2026-08-25 실패에서 배움).
    """
    import ast

    try:
        tree = ast.parse(cell_source)
    except SyntaxError:
        return cell_source
    out = cell_source.splitlines(keepends=True)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in sols]
    for node in reversed(funcs):  # 뒤에서부터 — 앞 교체가 줄번호를 밀지 않게
        out[node.lineno - 1 : node.end_lineno] = [sols[node.name].rstrip() + "\n"]
    return "".join(out)


def check_run(nb, solutions: Path) -> list[str]:
    """정답 구현으로 스텁을 채운 뒤 끝까지 실행한다."""
    try:
        from nbclient import NotebookClient
    except ImportError:
        return ["실행검사 건너뜀: nbclient 없음 (uv add --dev nbclient)"]

    sols = _parse_solutions(solutions.read_text())
    if not sols:
        return [f"{solutions} 에서 함수 정의를 못 찾았다"]

    cells, filled = [], 0
    for cell in nb.cells:
        if cell.cell_type == "code":
            src = cell_src(cell)
            new = _fill_stubs(src, sols)
            if new != src:
                filled += 1
            cell = nbformat.v4.new_code_cell(new)
        cells.append(cell)
    print(f"           (스텁 {filled}개 셀을 정답으로 채움)")
    run_nb = nbformat.v4.new_notebook(cells=cells, metadata=nb.metadata)

    import matplotlib
    matplotlib.use("Agg")
    try:
        NotebookClient(run_nb, timeout=300, kernel_name="python3").execute()
    except Exception as e:  # noqa: BLE001
        return [f"실행 실패: {type(e).__name__}: {str(e)[:400]}"]
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("notebook", type=Path)
    ap.add_argument("--solutions", type=Path, default=None,
                    help="TODO(human) 정답 구현 .py — 주면 실행검사까지 한다")
    args = ap.parse_args()

    nb = nbformat.read(args.notebook, as_version=4)
    print(f"검수: {args.notebook}  (셀 {len(nb.cells)}개)")

    fails: list[str] = []
    for name, errs in [
        ("① 스키마", check_schema(nb, args.notebook)),
        ("② 구문", check_syntax(nb)),
        ("③ 개행", check_newlines(nb)),
    ]:
        print(f"  {name:8} {'✅' if not errs else '❌'}")
        fails += errs

    warns = check_todos(nb)
    print(f"  ④ TODO   {'✅' if not warns else '⚠️'}")

    if args.solutions:
        errs = check_run(nb, args.solutions)
        print(f"  ⑤ 실행   {'✅' if not errs else '❌'}")
        fails += errs

    for e in fails:
        print(f"    ❌ {e}")
    for w in warns:
        print(f"    ⚠️  {w}")

    if fails:
        print(f"\n{len(fails)}건 실패 — 사람에게 내보내지 말 것")
        return 1
    print("\n통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
