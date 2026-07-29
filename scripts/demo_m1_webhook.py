"""요청 하나가 인그레스의 가드 절을 어떻게 통과하거나 튕기는지 눈으로 본다.

    uv run python scripts/demo_m1_webhook.py

FastAPI 의 TestClient 를 쓴다 — 진짜 uvicorn 을 띄우지 않고 앱을 직접 호출한다.
포트도, 터널도, GitHub 도 필요 없다. app.py 가 순수 함수에 가깝게 유지된 덕이다.

읽는 법: 각 줄의 상태 코드가 '어느 가드에서 나왔는지'를 옆에 적어뒀다.
같은 200 이라도 나온 자리가 다르면 다른 일이 일어난 것이다.
"""

import hashlib
import hmac
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from backend.queue.router import queue_depth, reset  # noqa: E402
from backend.webhook.app import DELIVERY_HEADER, EVENT_HEADER, app  # noqa: E402
from backend.webhook.security import (  # noqa: E402
    SIGNATURE_HEADER,
    SIGNATURE_PREFIX,
    WEBHOOK_SECRET,
)

client = TestClient(app)
reset()  # 데모는 항상 빈 상태에서 시작한다

PAYLOAD = {"action": "opened", "number": 42, "pull_request": {"id": 1}}
BODY = json.dumps(PAYLOAD, separators=(",", ":")).encode()


def sign(body: bytes) -> str:
    return SIGNATURE_PREFIX + hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()


def post(
    label: str,
    body: bytes,
    *,
    event: str | None,
    signature: str | None,
    expect: int,
    delivery: str | None = "demo-delivery-0001",
    expect_depth: int | None = None,
):
    headers = {"Content-Type": "application/json"}
    if delivery is not None:
        headers[DELIVERY_HEADER] = delivery
    if event is not None:
        headers[EVENT_HEADER] = event
    if signature is not None:
        headers[SIGNATURE_HEADER] = signature

    res = client.post("/webhook", content=body, headers=headers)
    ok = res.status_code == expect

    depth_note = ""
    if expect_depth is not None:
        ok = ok and queue_depth() == expect_depth
        depth_note = f"  큐={queue_depth()} (기대 {expect_depth})"

    print(f"{'✓' if ok else '✗'} {label:<34} → {res.status_code}  (기대 {expect}){depth_note}")
    return ok


print("=" * 62)
print("가드 절을 순서대로 하나씩 건드려본다")
print("=" * 62)

results = [
    # ── 가드 3: 서명 검증 ────────────────────────────────────────────
    post("서명 헤더 없음", BODY, event="pull_request", signature=None, expect=400),
    post("서명이 틀림", BODY, event="pull_request", signature=sign(b"other"), expect=400),
    # 서명은 맞지만 body 가 1바이트 다르다 — 내용은 같아 보여도 다른 문서다
    post(
        "body 에 공백 하나 추가",
        BODY + b" ",
        event="pull_request",
        signature=sign(BODY),
        expect=400,
    ),
    # ── 가드 4: 이벤트 필터 (서명은 통과한 상태) ──────────────────────
    post("ping 이벤트 (웹훅 등록 직후)", BODY, event="ping", signature=sign(BODY), expect=200),
    post("push 이벤트 (관심 없음)", BODY, event="push", signature=sign(BODY), expect=200),
    # ── 가드 5: JSON 파싱 (서명·이벤트 모두 통과) ─────────────────────
    post(
        "서명 맞음 + 깨진 JSON",
        b'{"action":"ope',
        event="pull_request",
        signature=sign(b'{"action":"ope'),
        expect=400,
    ),
    # ── 전부 통과 ────────────────────────────────────────────────────
    post("정상 PR 이벤트", BODY, event="pull_request", signature=sign(BODY), expect=200, expect_depth=1),
]

print()
print("=" * 62)
print("멱등성 — 같은 배달이 또 왔을 때 (INV-2)")
print("=" * 62)

results += [
    # 같은 delivery ID 로 두 번 더. 응답은 200 이지만 큐는 그대로여야 한다.
    post("같은 배달 재전송 (2회차)", BODY, event="pull_request", signature=sign(BODY), expect=200, expect_depth=1),
    post("같은 배달 재전송 (3회차)", BODY, event="pull_request", signature=sign(BODY), expect=200, expect_depth=1),
    # 다른 배달이면 당연히 들어가야 한다 — dedup 이 과하게 막고 있지 않은지 확인.
    post("다른 배달 ID", BODY, event="pull_request", signature=sign(BODY), expect=200, delivery="other-0002", expect_depth=2),
    # 헤더가 아예 없으면? 열쇠가 없으니 판단 불가 → 통과시킨다.
    post("delivery 헤더 없음", BODY, event="pull_request", signature=sign(BODY), expect=200, delivery=None, expect_depth=3),
    post("delivery 헤더 없음 (또)", BODY, event="pull_request", signature=sign(BODY), expect=200, delivery=None, expect_depth=4),
]

print()
print(f"{'모두 통과' if all(results) else f'{results.count(False)}개 실패'}")
print()
print("눈여겨볼 것")
print("  · 3번째: 내용은 같은데 바이트가 달라서 거부됐다. 서명은 의미가 아니라 바이트에 걸린다")
print("  · 4·5번째: 서명은 통과했지만 우리가 안 쓰는 이벤트다. 에러가 아니므로 200")
print("  · 6번째: M1의 진짜 체크포인트. 500 이 아니라 400 이어야 한다")
print("  · 재전송 2·3회차: 응답은 200 인데 큐가 안 늘었다 — 이게 멱등성이다")
print("  · delivery 헤더 없음: 열쇠가 없으면 판단 불가라 매번 통과한다(의도)")
