"""테스트가 쓸 도구들. 케이스는 여기 없다 — test_webhook.py 에 사람이 쓴다.

이 파일이 주는 것: 요청을 만들고 쏘는 법. 무엇을 확인할지는 주지 않는다.
그 구분이 이 프로젝트에서 중요한 이유는 아래 test_webhook.py 상단에 적어뒀다.
"""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from backend.queue.router import queue_depth, reset
from backend.webhook.app import DELIVERY_HEADER, EVENT_HEADER, app
from backend.webhook.security import SIGNATURE_HEADER, SIGNATURE_PREFIX, WEBHOOK_SECRET


@pytest.fixture(autouse=True)
def clean_queue():
    """테스트마다 큐와 dedup 기록을 비운다.

    autouse=True 라 따로 부르지 않아도 모든 테스트에 적용된다.
    이게 없으면 앞 테스트가 남긴 delivery ID 때문에 뒤 테스트가
    '중복'으로 판정되고, 실패 원인이 엉뚱한 곳을 가리킨다.
    """
    reset()
    yield
    reset()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def payload_bytes() -> bytes:
    """GitHub 이 보낼 법한 raw body. 공백 없는 압축 JSON."""
    return json.dumps(
        {"action": "opened", "number": 42, "pull_request": {"id": 1}},
        separators=(",", ":"),
    ).encode()


@pytest.fixture
def sign():
    """body 에 대한 올바른 서명을 만든다 — GitHub 이 하는 계산과 같다.

    대칭키라서 우리도 만들 수 있다. secret 을 바꿔 '남이 만든 서명'도 흉내낼 수 있다.
    """

    def _sign(body: bytes, secret: bytes = WEBHOOK_SECRET) -> str:
        digest = hmac.new(key=secret, msg=body, digestmod=hashlib.sha256).hexdigest()
        return SIGNATURE_PREFIX + digest

    return _sign


@pytest.fixture
def post(client):
    """웹훅 요청 하나를 쏜다. 헤더를 개별로 빼거나 바꿀 수 있다.

    None 을 주면 그 헤더를 아예 보내지 않는다 (빈 문자열과 다르다).
    """

    def _post(
        body: bytes,
        *,
        signature: str | None,
        event: str | None = "pull_request",
        delivery: str | None = "test-delivery-0001",
    ):
        headers = {"Content-Type": "application/json"}
        if signature is not None:
            headers[SIGNATURE_HEADER] = signature
        if event is not None:
            headers[EVENT_HEADER] = event
        if delivery is not None:
            headers[DELIVERY_HEADER] = delivery
        return client.post("/webhook", content=body, headers=headers)

    return _post


@pytest.fixture
def depth():
    """지금 큐에 쌓인 잡 수. '진짜로 들어갔는지'를 보는 창구."""
    return queue_depth
