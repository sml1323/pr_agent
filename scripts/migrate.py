"""migrations/*.sql 을 번호 순서대로 전부 실행한다.

    uv run python scripts/migrate.py            # 전부 실행
    uv run python scripts/migrate.py 001        # 001 로 시작하는 것만

**적용 이력을 추적하지 않는다.** 매번 처음부터 전부 다시 돌린다.
그래서 모든 마이그레이션이 재실행 가능(idempotent)해야 한다 —
`DROP ... IF EXISTS` → `CREATE`, `CREATE ... IF NOT EXISTS` 형태.

이력 추적(schema_migrations 테이블)을 안 쓰는 이유: M2 는 스키마를 수십 번 갈아엎는다.
이력이 있으면 "적용됨"으로 기록된 걸 다시 안 돌려서, 파일과 DB 상태가 조용히 어긋난다.
전부 재실행하면 **파일이 항상 진실**이다. 느리지만 이 규모에서는 문제가 안 된다.

'에러 없이 끝남'이 아니라 **두 번 연속 돌려도 같은 결과**가 성공 판정이다.
한 번은 되고 두 번째에 깨지면 그 마이그레이션은 재실행 가능하지 않다.
"""

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "migrations"

load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    # M1 의 WEBHOOK_SECRET 과 같은 판단 — 기본값을 주지 않는다.
    # 로컬 DB 로 조용히 붙어서 "돌아가는데 아무것도 안 남는" 상태를 만들지 않는다.
    sys.exit("DATABASE_URL 이 없다. .env 에 넣어라 (tiger db connection-string --with-password)")

prefix = sys.argv[1] if len(sys.argv) > 1 else ""
files = sorted(p for p in MIGRATIONS.glob("*.sql") if p.name.startswith(prefix))

if not files:
    sys.exit(f"실행할 마이그레이션이 없다: {MIGRATIONS}/{prefix}*.sql")

print(f"대상 {len(files)}개 — {DATABASE_URL.split('@')[-1].split('/')[0]}\n")

with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
    for path in files:
        sql = path.read_text()
        try:
            conn.execute(sql)  # type: ignore[arg-type]
            print(f"  ✓ {path.name}")
        except psycopg.Error as e:
            # 어디서 깨졌는지 파일명이 같이 나와야 한다. 스택 트레이스만으론 못 찾는다.
            print(f"  ✗ {path.name}\n\n{e}")
            sys.exit(1)

print("\n전부 적용됨. 한 번 더 돌려서 같은 결과가 나오는지 확인할 것.")
