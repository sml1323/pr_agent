-- 004_truth.sql — reviews / findings / hitl_decisions
--
-- "진실(truth) 모양" — 에이전트가 **만들어낸 것**을 담는다.
-- 002 의 agent_events 와 대조하면 이 파일의 모든 선택이 설명된다:
--
--   agent_events         이 표들
--   ──────────────       ──────────────
--   일어난 일             현재 상태
--   시간으로 자른다        id 로 집는다
--   절대 안 바뀐다(INV-4)  바뀐다 (queued → auto_posted)
--   하이퍼테이블           평범한 테이블
--   PK 없음               PK 있음
--
-- 같은 사건이 양쪽에 다 남는다. 중복이 아니라 역할이 다르다 —
-- agent_events 는 "그때 이런 일이 있었다"(영구 증거),
-- findings 는 "지금 이 지적이 이 상태다"(변함).
--
-- 왜 하이퍼테이블이 아닌가: 하이퍼테이블은 "시간 범위로 자른다"에 최적화된 물건이다.
-- 이 표들의 주 질문은 "리뷰 42번의 finding 들"이고 시간 범위가 아니다.
-- 게다가 UNIQUE/PRIMARY KEY 에 파티션 키를 포함해야 하는 제약이 붙는데,
-- 여기선 id 하나로 참조할 수 있어야 한다 (findings → reviews 외래키).
--
-- 재실행 가능 — DROP → CREATE. 자식부터 지운다.

DROP TABLE IF EXISTS hitl_decisions CASCADE;
DROP TABLE IF EXISTS findings CASCADE;
DROP TABLE IF EXISTS reviews CASCADE;


-- ═════════════════════════════════════════════════════════════════════
-- reviews — PR 하나에 대한 리뷰 한 건
-- ═════════════════════════════════════════════════════════════════════

CREATE TABLE reviews (
    id          BIGSERIAL PRIMARY KEY,
    -- BIGSERIAL = 자동 증가하는 정수. findings 가 이걸 가리킨다.
    -- agent_events 에 PK 를 안 둔 것과 정반대인 이유: 저긴 개별 행을 집을 일이 없고
    -- 여긴 집는 게 전부다.

    repo        TEXT    NOT NULL,   -- 'owner/name'. PR 번호는 레포마다 1부터 시작하므로
                                    -- pr_id 만으로는 세계에서 유일하지 않다
    pr_id       INTEGER NOT NULL,   -- 002 의 agent_events.pr_id 와 같은 타입으로 맞춘다

    head_sha    TEXT    NOT NULL,
    -- 어느 커밋을 봤나. 이게 없으면 "같은 PR 을 이미 리뷰했다"가 거짓말이 된다 —
    -- PR 에 push 가 이어지면 코드가 달라지므로 다시 리뷰해야 한다.
    -- INV-2 정정 노트 ③ ("같은 PR 에 push 가 이어질 때")이 여기 걸린다.

    delivery_id TEXT,
    -- X-GitHub-Delivery GUID. M1 큐의 dedup 은 인메모리라 재시작을 못 넘기는데(INV-2),
    -- 여기 남으면 영구 dedup 의 재료가 된다. M4 에서 Redis 로 갈 때 쓴다.
    -- NULL 허용 — 수동으로 돌린 리뷰는 배달이 없다.

    -- ── status — 이 리뷰가 파이프라인 어디쯤 있나 ──────────────────────
    --
    -- 이 컬럼은 딱 세 개의 쿼리를 위해 존재한다:
    --   ① 대시보드   WHERE status = 'awaiting_human'
    --   ② 워커 복구  WHERE status IN ('queued', 'running')    ← 죽은 워커의 잔해
    --   ③ 게이트     WHERE status = 'running'                 ← 판단할 차례인 것
    --
    -- 정상 여정:  queued → running → auto_posted
    -- 사람 경로:  queued → running → awaiting_human → human_posted | dismissed
    -- 사고 경로:  queued → running → partial | failed
    --
    -- ⚠️ partial 과 auto_posted 를 가르는 것이 이 컬럼의 존재 이유다 (G2 리스크).
    --    에이전트 하나가 죽으면 애그리게이터는 "critical 없음"을 본다. 진실은
    --    "그 관점은 아무도 안 봤다" 다. 둘이 같은 값이면 확인 안 된 PR 이 자동 게시된다.
    --    건강검진에서 엑스레이 기계가 고장났는데 "이상 없습니다"라고 말하는 것과 같다.
    --
    -- ⚠️ 임계값 0.6 은 여기 없다. 스키마는 "무엇이 존재할 수 있나"고
    --    정책은 "그중 뭘 통과시키나"다. 0.6 은 M8 backend/gate/ 에만 산다.
    --    partial 을 자동 게시로 보낼지 말지도 게이트의 판단이지 스키마의 일이 아니다.
    --
    -- ⚠️ 값에 에이전트 이름을 넣지 않았다 ('security_failed' 같은 것).
    --    status 는 "어디쯤 있나" 하나만 답한다. "누가 죽었나"는 다른 질문이고
    --    아래 failed_agents 가 답한다. 둘을 한 컬럼에 겹치면 값이 곱해진다 —
    --    에이전트 4개면 실패 조합이 15가지고, 5번째를 추가하면 31가지다.
    --    그리고 그 목록을 아는 코드가 M8 대시보드까지 번진다.
    status      TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN (
            'queued',          -- 큐에 있고 워커가 아직 안 집었다
            'running',         -- 에이전트들이 돌고 있다
            'auto_posted',     -- 게이트 통과 → GitHub 에 자동 게시됨
            'awaiting_human',  -- 게이트가 사람에게 넘겼다 (HITL 큐)
            'human_posted',    -- 사람이 검토하고 게시했다
            'dismissed',       -- 사람이 "게시 안 함"으로 닫았다
            'partial',         -- 일부 에이전트가 죽었다. findings 는 있지만 불완전하다
            'failed'           -- 전부 죽었다. 볼 findings 자체가 없다
        )),
    -- DEFAULT 는 반드시 CHECK 목록 안의 값이어야 한다.
    -- 아니면 status 를 생략한 INSERT 가 전부 거부된다 — 그리고 그 에러는
    -- "DEFAULT 가 틀렸다"가 아니라 "제약 위반"으로 뜨므로 원인이 안 보인다.

    failed_agents TEXT[] NOT NULL DEFAULT '{}',
    -- 누가 죽었나. status='partial' 일 때 채워진다.
    -- 왜 개수(INTEGER)가 아니라 이름 배열인가: security 가 죽은 것과 docs 가 죽은 것은
    -- 심각도가 완전히 다르다. 개수만 세면 그 차이가 사라진다.
    -- 왜 agent_events 를 뒤지지 않나: "없는 줄을 찾는" 쿼리는 무겁고,
    -- 게이트는 리뷰마다 이걸 봐야 한다. 저긴 증거고 여긴 작업 지시다.
    -- 조회:  WHERE 'security' = ANY(failed_agents)

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    -- agent_events 에는 ts 하나뿐이었다 — 안 바뀌니까 "언제 생겼나"가 곧 전부였다.
    -- 여긴 상태가 바뀌므로 "언제 생겼나"와 "언제 마지막으로 움직였나"가 다르다.
);

-- 같은 커밋을 두 번 리뷰하지 않는다. INV-2 를 DB 레벨로 한 겹 더.
-- repo 를 포함하는 이유: PR 번호는 레포마다 1부터 다시 시작한다.
CREATE UNIQUE INDEX reviews_unique_head ON reviews (repo, pr_id, head_sha);

-- 대시보드와 워커 복구가 둘 다 status 로 찾는다.
CREATE INDEX reviews_by_status ON reviews (status);


-- ═════════════════════════════════════════════════════════════════════
-- findings — 그 리뷰가 낸 지적들
-- 컬럼이 backend/agents/schema.py 의 Finding 과 1:1 로 대응한다.
-- ═════════════════════════════════════════════════════════════════════

CREATE TABLE findings (
    id          BIGSERIAL PRIMARY KEY,

    review_id   BIGINT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    -- ON DELETE CASCADE — 리뷰가 사라지면 그 finding 들도 같이 사라진다.
    -- 부모 없는 finding 은 "어느 PR 의 무슨 커밋에 대한 지적인지"를 잃어서 쓸 데가 없다.
    -- ⚠️ 이게 INV-4 를 어기는 게 아니다. INV-4 는 agent_events 에만 걸린다.
    --    감사 증거는 저쪽에 남아 있고, 여긴 "지금의 상태"라 지워도 된다.

    -- ── CHECK 를 거는 것과 안 거는 것 ────────────────────────────────
    -- 판단 기준은 "Pydantic 과 중복이냐"가 아니라 **"DB 에 쓰는 경로가 앱 하나뿐이냐"**다.
    -- 아니다 — psql 수동 삽입, 백필 스크립트, 컬럼 순서를 바꿔 넣는 INSERT 코드가 있다.
    -- Pydantic 은 LLM 출력을 검증하는 물건이지 DB 삽입을 지키지 않는다.
    -- (M0 에서 실제로 line=0 이 나왔고 완료 판정을 그대로 통과했다 — schema.py:41)
    --
    -- 드리프트 위험은 인정한다. schema.py 의 Literal 을 고치면 여기도 고쳐야 한다.
    -- 그 비용을 받아들이는 이유: 틀린 값이 들어가면 터지는 곳이 M8 이고 원인은 여기다.
    -- 멀리서 터지는 버그가 마이그레이션 한 줄보다 비싸다.

    agent_type  TEXT NOT NULL
        CHECK (agent_type IN ('security', 'quality', 'testing', 'docs')),
        -- 닫힌 목록. M6 에서 이 4개로 확정된다.
        -- 늘어나면 마이그레이션이 필요하지만, 그때 reviews.failed_agents 와
        -- 프롬프트도 같이 봐야 하므로 "고칠 곳이 하나 더 느는" 정도다.

    severity    TEXT NOT NULL
        CHECK (severity IN ('critical', 'high', 'medium', 'low', 'informational')),
        -- 게이트의 첫 번째 축. 'Critical' 과 'critical' 이 다르게 취급되면
        -- critical 이 하나 있는데 게이트가 못 보고 자동 게시한다.

    category    TEXT NOT NULL,
        -- 제약 없음 — 자유 태그다. 'sql-injection', 'resource-leak' 처럼
        -- 무엇이 나올지 미리 다 알 수 없다. 닫으면 새 종류의 버그를 못 적는다.

    file        TEXT NOT NULL,

    line        INTEGER NOT NULL CHECK (line >= 1),
        -- 파일에 0번 줄은 없다. 0 이 들어가면 M8 에서 GitHub 0번 줄에
        -- 코멘트를 달려다 실패한다 — 원인이 여기라는 걸 그때는 모른다.

    confidence  NUMERIC(4, 3) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    -- (4,3) = 전체 4자리 중 소수 3자리 → 0.000 ~ 9.999. 1.0 이 들어간다.
    -- 왜 부동소수점(REAL)이 아닌가: M8 게이트가 `confidence >= 0.6` 을 한다.
    -- 0.6 은 2진 분수로 정확히 표현되지 않아서 경계값이 어느 쪽으로 떨어질지가
    -- 저장 방식에 달리게 된다. NUMERIC 은 10진수를 그대로 담아 그 흔들림이 없다.
    -- (002 의 cost_usd 를 NUMERIC 으로 한 것과 이유는 다르다 — 저건 SUM 누적 오차,
    --  이건 경계 비교. 결론만 같다)
    --
    -- ⚠️ CHECK 는 범위(0~1)만 건다. 임계값 0.6 은 여기 없다 — 정책이니까.

    rationale   TEXT NOT NULL,
    -- INV-3. 근거 없는 지적은 리뷰가 아니라 소음이다.

    posted_at   TIMESTAMPTZ,
    -- GitHub 에 실제로 코멘트가 달린 시각. NULL = 아직 안 달림.
    -- 이 컬럼이 바뀐다는 게 findings 가 하이퍼테이블이 아닌 이유 그 자체다.

    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 주 질문이 "리뷰 42번의 finding 들" 이므로 review_id 로 찾는 길을 낸다.
CREATE INDEX findings_by_review ON findings (review_id);


-- ═════════════════════════════════════════════════════════════════════
-- hitl_decisions — 사람이 내린 결정
-- HITL = Human In The Loop. 게이트가 사람에게 넘긴 것에 사람이 답한 기록.
-- ═════════════════════════════════════════════════════════════════════
--
-- ── finding 단위로 붙인다 (리뷰 단위가 아니라) ─────────────────────────
-- 게이트는 리뷰 단위로 판단하지만(critical 하나면 리뷰 전체가 사람에게),
-- 사람이 큐 앞에서 하는 일은 지적 하나씩 고르는 것이다 —
-- 5개 중 3개는 맞고 2개는 헛소리인 게 보통이다.
--
-- 결정적인 이유는 M9 다. 이 프로젝트의 제1원칙이 **선별**이고,
-- 선별이 잘 되는지 재는 유일한 자가 사람의 판정이다:
--     "우리가 낸 지적 중 몇 %가 맞았나"
--     → SELECT decision, count(*) FROM hitl_decisions GROUP BY decision
-- 리뷰 단위로 뭉치면 이 숫자를 영영 못 낸다. 그리고 사람이 한 판단은
-- 나중에 다시 물어볼 수가 없다 — 안 남기면 그걸로 끝이다.

CREATE TABLE hitl_decisions (
    id          BIGSERIAL PRIMARY KEY,

    finding_id  BIGINT NOT NULL REFERENCES findings(id) ON DELETE CASCADE,

    decision    TEXT NOT NULL
        CHECK (decision IN (
            'accepted',   -- 맞는 지적이다 → 게시한다
            'rejected',   -- 오탐이다 → 버린다.  M9 의 오탐률이 이 숫자로 나온다
            'deferred'    -- 지금은 판단 못 하겠다 → 큐에 남긴다
        )),

    decided_by  TEXT NOT NULL,   -- GitHub 유저명. 누가 판단했는지가 남아야 한다
    note        TEXT,            -- 왜 그렇게 판단했나. 선택
    decided_at  TIMESTAMPTZ NOT NULL DEFAULT now()

    -- ⚠️ finding_id 에 UNIQUE 를 걸지 않았다 — 일부러다.
    --    번복을 UPDATE 로 하지 않고 **새 행을 append 하고 최신 것을 읽는다.**
    --    INV-4 의 사고방식을 빌려온 것이다: "맞다"고 했다가 "아니다"로 바꾼
    --    과정 자체가 M9 의 재료다. UPDATE 로 덮으면 그게 사라진다.
    --    대가는 조회가 한 겹 복잡해지는 것:
    --      SELECT DISTINCT ON (finding_id) * FROM hitl_decisions
    --        ORDER BY finding_id, decided_at DESC;
);

CREATE INDEX hitl_by_finding ON hitl_decisions (finding_id, decided_at DESC);


-- 확인용 (마이그레이션의 일부가 아니다):
--   \d reviews
--   \d findings
--   \d hitl_decisions
--
--   -- 정상 경로 — 세 표가 실제로 이어지는지
--   INSERT INTO reviews (repo, pr_id, head_sha) VALUES ('me/toy', 42, 'abc123');
--   INSERT INTO findings (review_id, agent_type, severity, category, file, line,
--                         confidence, rationale)
--     VALUES (1, 'security', 'critical', 'sql-injection', 'app.py', 16, 0.95, 'x');
--   INSERT INTO hitl_decisions (finding_id, decision, decided_by)
--     VALUES (1, 'accepted', 'sml1323');
--
--   -- CHECK 가 실제로 거부하는지 — 넷 다 ERROR 여야 한다
--   UPDATE reviews  SET status = 'Posted'     WHERE id = 1;   -- 목록에 없는 값
--   UPDATE findings SET severity = 'CRITICAL' WHERE id = 1;   -- 대소문자
--   UPDATE findings SET line = 0              WHERE id = 1;   -- 0번 줄
--   UPDATE findings SET confidence = 1.5      WHERE id = 1;   -- 범위 밖
--
-- ⚠️ 003 에서와 같은 함정: "에러 났다"만 보지 말 것.
--    정상 INSERT 가 되는지도 같이 봐야 제약이 일하는 건지 표가 죽은 건지 구분된다.
