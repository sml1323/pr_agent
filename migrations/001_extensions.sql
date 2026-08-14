-- 001_extensions.sql — 이 프로젝트가 요구하는 Postgres 확장
--
-- Tiger Cloud 의 애드온(time-series, ai)이 이미 켜준 상태일 수 있다.
-- 그래도 여기 적는 이유: 애드온이 우연히 준 것과 이 프로젝트가 요구하는 것은 다르다.
-- 다른 환경으로 옮길 때 이 파일이 없으면 확장 부재를 런타임에야 알게 된다.
--
-- 재실행 가능(idempotent) — 몇 번 돌려도 결과가 같다.
-- M2 는 갈아엎기가 잦으므로 모든 마이그레이션이 이 성질을 지켜야 한다.

CREATE EXTENSION IF NOT EXISTS timescaledb;   -- 하이퍼테이블. agent_events 가 쓴다
CREATE EXTENSION IF NOT EXISTS vector;        -- vector(N) 타입. code_chunks 가 쓴다 (M7)

-- pgvectorscale(= 확장명 vectorscale)은 여기 넣지 않는다.
-- 검색 성능을 위한 것이고, 검색이 실제로 생기는 M7 에서 필요해지면 그때 요구한다.
-- 지금 넣으면 "왜 있는지 아무도 모르는 의존성"이 된다.

-- 확인용 (마이그레이션의 일부가 아니라 눈으로 볼 때 쓰는 쿼리):
--   SELECT extname, extversion FROM pg_extension ORDER BY extname;
