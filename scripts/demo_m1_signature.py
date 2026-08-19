"""verify_signature() 가 실제로 통과시키고 실제로 거부하는지 눈으로 본다.

아직 웹서버가 없어도 돌아간다 — security.py 가 FastAPI 를 모르게 만들어둔 덕이다.

    uv run python scripts/demo_m1_signature.py

'전부 통과'가 아니라 **정상 요청이 True 이고 나머지가 전부 False 인 것**이 성공이다.
전부 False 면 보안이 아니라 기능이 죽은 것이고, 겉으로는 구분되지 않는다.
"""

import hashlib
import hmac
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.webhook.security import (  # noqa: E402
    SIGNATURE_PREFIX,
    WEBHOOK_SECRET,
    verify_signature,
)

# GitHub 이 보낼 법한 raw body. 공백 없는 압축 JSON — 실제로 이렇게 온다.
BODY = b'{"action":"opened","number":42,"pull_request":{"id":1}}'


def sign(body: bytes, secret: bytes = WEBHOOK_SECRET) -> str:
    """GitHub 이 하는 계산을 우리가 흉내낸다 — 대칭키라서 가능하다."""
    digest = hmac.new(key=secret, msg=body, digestmod=hashlib.sha256).hexdigest()
    return SIGNATURE_PREFIX + digest


good = sign(BODY)

cases = [
    ("정상 요청",                      BODY,            good,                        True),
    ("헤더 없음",                      BODY,            None,                        False),
    ("접두사 없음",                    BODY,            good.removeprefix(SIGNATURE_PREFIX), False),
    ("서명 한 글자 변조",              BODY,            good[:-1] + ("0" if good[-1] != "0" else "1"), False),
    ("다른 secret 으로 서명",          BODY,            sign(BODY, b"attacker"),     False),
    ("본문에 공백 하나 추가",          BODY + b" ",     good,                        False),
    ("본문을 파싱했다 되돌림",         b'{"action": "opened", "number": 42, "pull_request": {"id": 1}}', good, False),
]

width = max(len(name) for name, *_ in cases)
failed = 0

for name, body, header, expected in cases:
    actual = verify_signature(body, header)
    ok = actual == expected
    failed += not ok
    print(f"{'✓' if ok else '✗'} {name:<{width}}  기대 {expected!s:<5} 실제 {actual!s:<5}")

print()
print("모두 통과" if not failed else f"{failed}개 실패")
