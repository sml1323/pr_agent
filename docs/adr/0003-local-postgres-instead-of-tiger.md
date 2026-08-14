# ADR 0003 — DB를 Tiger Cloud에서 로컬 Postgres로 바꾼다

**날짜**: 2026-07-30
**상태**: 확정
**개정 대상**: [ADR 0001](0001-project-setup.md) D3 (DB는 처음부터 Tiger Cloud, 로컬 Docker 안 씀)
**시점**: M2 착수 직후. Tiger 서비스를 실제로 하나 띄워보고, 마이그레이션을 돌리기 직전

---

## 결정

`agent_events`·`reviews`·`code_chunks`가 사는 DB를 **로컬 Docker의 `timescale/timescaledb-ha`**로 옮긴다.
Tiger Cloud 서비스 `pr-agent`(`ypkw5jevyw`)는 삭제한다.

## 왜 바꾸나

**1. 포트폴리오에서 재현 가능한 레포가 되는 게 더 값어치 있다.**
Tiger Cloud에 붙어 있으면 레포를 clone한 사람이 계정을 만들어야 하고, 대부분 그냥 안 돌려본다.
`docker compose up -d` 세 줄이면 남이 돌려볼 수 있다. "Tiger Cloud 써봤다"는 이력서 한 줄로는 안 팔리고,
관리형 서비스를 클릭한 경험은 인프라 역량의 증거로 읽히지 않는다.

**2. 배우는 내용이 동일하다.**
하이퍼테이블·트리거·RBAC·pgvector는 Tiger가 주는 게 아니라 **Postgres와 TimescaleDB가 주는 것**이다.
M2~M8에서 손으로 쓰는 SQL은 한 글자도 안 바뀐다.

**3. ADR 0001에 이미 리스크로 적어둔 마찰이 실제로 확인됐다.**
`CURRENT.md`의 "알려진 리스크" 첫 줄이 *"Tiger를 처음부터 쓰면 초반 마이그레이션 반복이 로컬보다 느림"*이었다.
M2는 스키마를 수십 번 갈아엎는 마일스톤이고, `docker compose down -v` 한 줄과
클라우드 서비스 재프로비저닝은 마찰이 다르다.

**4. 무료 플랜의 제약이 드러났다.**
`0.5 CPU/2 GB`는 `plan not found`로 거부됐고, shared 사양은 `us-east-1`만 허용됐다.
ADR 0001 D3이 상정한 "dedicated CPU + 애드온" 구성은 결제 정보 없이는 불가능했다.

## 무엇을 잃나

- **Tiger MCP로 SQL을 바로 돌리는 편의.** `mcp__tiger__db_execute_query`가 없어지므로
  `scripts/migrate.py`(psycopg)와 `docker exec ... psql`로 대체한다. 오히려 실행 경로가 레포 안에 남는다.
- **영상과의 일치.** 영상은 Tiger Cloud를 쓰고 $1,000 크레딧을 언급한다 [02:48:27]. 이제 다르다.
- **연속 집계·보존 정책의 관리형 튜닝.** M10이 범위 밖이므로 이번 프로젝트에서는 영향 없다.

## 무엇을 이미 얻었나 (낭비가 아닌 이유)

ADR 0001 D3이 노린 학습 포인트는 **"인프라 셋업도 콘솔 클릭이 아니라 에이전트가 코드처럼 프로비저닝한다"**였다 [02:51:04].
그건 이미 했다 — `tiger mcp install` → MCP 연결 → `service_create`로 서비스를 띄우고
`pg_extension`을 조회해 확장 목록을 확인했다. **경험은 얻고 의존성만 버린다.**

부수적으로 얻은 것: MCP 설정의 스코프 구분(user `~/.claude.json` vs project `.mcp.json`)과,
`--config-path`가 무시될 수 있다는 관측.

## 되돌리기

싸다. `.env`의 `DATABASE_URL` 한 줄이다.
마이그레이션이 표준 SQL이고 Tiger Cloud도 Postgres이므로, 나중에 클라우드로 올릴 때 그대로 돌아간다.
**이게 로컬로 가는 결정이 안전한 이유다** — 벤더에 묶이는 방향이 아니라 푸는 방향이다.

## 따라오는 변경

- `docker-compose.yml` 추가 — `timescale/timescaledb-ha:pg17`, `127.0.0.1`에만 바인드, healthcheck 포함
- `.env`에 `DATABASE_URL` (로컬이므로 비밀이 아니지만 `.env`는 계속 추적 제외)
- `scripts/migrate.py` — `migrations/*.sql`을 번호 순서대로 전부 재실행
- `docs/03-build-plan.md` M2 절의 "Tiger Cloud 서비스 프로비저닝" 항목이 무효
- `docs/CURRENT.md`의 "TigerData 계정 + Tiger CLI" 준비물이 무효
- `.mcp.json`의 `tiger` MCP 서버는 **남긴다** — `search_docs`가 TimescaleDB·Postgres 공식 문서
  검색에 계속 쓸 만하다. DB 조작 도구만 안 쓴다
