-- 003_immutable.sql — agent_events 를 DB 레벨에서 append-only 로 못 박는다 (INV-4)
--
-- 왜 코드가 아니라 DB 인가: 코드 규칙은 누군가 까먹거나 우회한다.
-- DB 가 거부하면 누가 쓰든 물리적으로 불가능하다.
-- 수정 가능한 감사 로그는 감사 로그가 아니다.
--
-- 트리거가 chunk 까지 따라가는가 — 따라간다. 확인된 사실이다:
--   "When you create, alter, drop, enable, or disable a trigger on a hypertable...
--    TimescaleDB propagates the change to every chunk."
--   https://www.tigerdata.com/docs/build/performance-optimization/automate-tasks-with-triggers
--
-- 이 파일이 막지 못하는 것 (Lesson 05 의 문 ④⑤):
--   · SELECT drop_chunks(...)   → chunk 파일을 지우는 DDL. DML 트리거의 사정거리 밖
--   · DROP TABLE agent_events   → 같은 이유
--   둘 다 006_rbac.sql 에서 권한으로 막는다. 트리거로는 원리적으로 불가능하다.

-- ── 거부 함수 ────────────────────────────────────────────────────────
-- 트리거 셋이 이 함수 하나를 공유한다. TG_OP 에 'UPDATE' / 'DELETE' / 'TRUNCATE' 중
-- 무엇이 발동시켰는지 들어오므로, 에러 메시지가 어느 문에서 막혔는지 알려준다.
--
-- CREATE OR REPLACE 라 재실행 가능하다.

CREATE OR REPLACE FUNCTION agent_events_append_only()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'agent_events 는 append-only 다 (INV-4). % 는 허용되지 않는다.', TG_OP;
END;
$$;

-- ── 트리거 ──────────────────────────────────────────────────────────
-- 재실행 가능하게 DROP IF EXISTS → CREATE 로 쓴다.

-- 문 ①: UPDATE — row 단위 동작이므로 FOR EACH ROW
DROP TRIGGER IF EXISTS agent_events_no_update ON agent_events;
CREATE TRIGGER agent_events_no_update
    BEFORE UPDATE ON agent_events
    FOR EACH ROW
    EXECUTE FUNCTION agent_events_append_only();


-- ─────────────────────────────────────────────────────────────────────
-- TODO(human) 문 ②③ 을 잠근다. 위 UPDATE 트리거를 본떠서 쓴다.
--
-- ── 문 ②: DELETE ─────────────────────────────────────────
--   위 UPDATE 트리거를 그대로 복사해서 두 군데만 바꾸면 된다:
--     · 트리거 이름  agent_events_no_update → agent_events_no_delete
--     · BEFORE UPDATE → BEFORE [빈칸]
--   나머지(FOR EACH ROW, EXECUTE FUNCTION)는 같다. DELETE 도 row 단위 동작이니까.
DROP TRIGGER IF EXISTS agent_events_no_delete ON agent_events;
CREATE TRIGGER agent_events_no_delete 
    BEFORE DELETE  ON agent_events
    FOR EACH ROW
    EXECUTE FUNCTION agent_events_append_only();
-- ── 문 ③: TRUNCATE ───────────────────────────────────────
--   여기가 다르다. 한 군데를 더 바꿔야 한다:
--     · 트리거 이름  → agent_events_no_truncate
--     · BEFORE UPDATE → BEFORE [빈칸]
--     · FOR EACH ROW → FOR EACH [빈칸]        ← 이 줄이 핵심
--

DROP TRIGGER IF EXISTS agent_events_no_truncate ON agent_events;
CREATE TRIGGER agent_events_no_truncate 
    BEFORE TRUNCATE  ON agent_events
    FOR EACH STATEMENT
    EXECUTE FUNCTION agent_events_append_only();
--   왜 다른가 (Lesson 05):
--     "Triggers on TRUNCATE may only be defined at statement level, not per-row."
--     — PostgreSQL Docs, CREATE TRIGGER
--
--   TRUNCATE 는 "이 줄을 지워라"가 아니라 "표를 비워라"다. 줄을 하나씩 보지 않으므로
--   FOR EACH ROW 가 성립하지 않는다. 후보: ROW / STATEMENT
--
--   그리고 왜 DELETE 트리거로는 이게 안 막히나:
--     "TRUNCATE will not fire any ON DELETE triggers that might exist for the tables.
--      But it will fire ON TRUNCATE triggers."
--     — PostgreSQL Docs, TRUNCATE
--
-- 틀리면 뭐가 깨지나: 셋 중 하나라도 빠지면 그 문으로 감사 로그가 통째로 사라진다.
-- 그리고 빠진 걸 알아챌 방법이 없다 — 나머지 둘이 잘 막고 있으면 "막았다"고 착각한다.
-- 영상에서도 빌더가 TRUNCATE 를 놓치고 독립 검증자가 잡았다 [03:02:54].
-- ─────────────────────────────────────────────────────────────────────


-- 확인용 — 셋 다 에러가 나야 통과다 (마이그레이션의 일부가 아니다):
--   INSERT INTO agent_events (agent, event_type) VALUES ('test', 'ping');  -- OK 여야 한다
--   UPDATE agent_events SET agent = 'x';    -- ERROR
--   DELETE FROM agent_events;               -- ERROR
--   TRUNCATE agent_events;                  -- ERROR
--
-- ⚠️ INSERT 가 되는지도 반드시 같이 확인할 것.
--    셋 다 막혔는데 INSERT 도 막혔다면 그건 보안이 아니라 표가 죽은 것이고,
--    "전부 에러 남"만 보면 두 경우가 구분되지 않는다.
