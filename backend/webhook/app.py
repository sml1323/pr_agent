"""GitHub 웹훅 인그레스 — 전체 그림의 ①.

택배를 받는 자리다: 맞는 주문인지 확인하고, 사인하고, 문을 닫고,
**그 다음에** 뜯어본다 [01:28:30]. 뜯어보는 건 여기가 아니다.

이 파일이 security.py 와 나뉜 이유:
    security.py 는 "진짜인가?"에 True/False 로만 답한다. HTTP 를 모른다.
    app.py 는 그 답을 **몇 번으로 내보낼지** 정한다. 그게 정책이고 여기 산다.
    같은 구분이 M8에서 다시 나온다 — 스키마는 무엇이 존재할 수 있나,
    게이트는 그중 뭘 통과시키나.

실행:
    uv run uvicorn backend.webhook.app:app --reload
"""

import json

from fastapi import APIRouter, Request, Response

from ..queue.router import enqueue, is_duplicate
from .security import SIGNATURE_HEADER, verify_signature

router = APIRouter()

# GitHub 이 이벤트 종류를 담아 보내는 헤더. body 를 건드리지 않고도 읽을 수 있다.
EVENT_HEADER = "X-GitHub-Event"

# 배달 하나하나의 고유 ID. INV-2(멱등성)의 키가 될 값이다.
# M1 (3/3)에서 queue/router.py 가 이걸로 중복을 걸러낸다. 지금은 읽어만 둔다.
DELIVERY_HEADER = "X-GitHub-Delivery"

# 우리가 실제로 리뷰하는 이벤트. 나머지는 받되 아무것도 하지 않는다.
HANDLED_EVENT = "pull_request"


# ─────────────────────────────────────────────────────────────────────
# 응답 계약 — 세 결과에 각각 무엇을 돌려주나
#
#   OK        큐에 넣었다. 영상이 두 번 명시한 200 을 따랐다 [01:28:30] [01:31:39].
#             202(Accepted)가 의미상 더 정확하지만, 하나로 고정하는 게 우선이다.
#   REJECTED  서명 불일치 / 헤더 없음 / 깨진 본문 — 이유와 무관하게 같은 400 (INV-1).
#             이유별로 코드를 나누면 공격자가 응답만 보고 어디까지 맞췄는지 알게 된다.
#   IGNORED   pull_request 가 아닌 이벤트. 에러가 아니다 —
#             웹훅 등록 직후 오는 ping 에 4xx 를 주면 GitHub UI 에 빨간 X 가 붙는다.
#
# OK 와 IGNORED 가 같은 200 인데도 상수를 나눈 이유: M3에서 로깅이 붙으면
# "큐에 넣음"과 "관심 없어 버림"은 구분해서 남겨야 하는 다른 사건이다.
# ─────────────────────────────────────────────────────────────────────
STATUS_OK = 200
STATUS_REJECTED = 400
STATUS_IGNORED = 200


@router.post("/webhook")
async def receive_webhook(request: Request) -> Response:
    """GitHub 웹훅을 받는 유일한 입구.

    여기서 LLM 을 부르면 안 된다. GitHub 은 ack 를 ~10초 안에 기대하고
    (영상 두 수치: [00:03:06] ~10초 / [01:31:39] ~10-12초, 화자가 불확실하다고 밝힘)
    전체 리뷰는 30~90초가 걸린다. 이건 취향이 아니라 외부 제약이다.
    """
    # 1. 원본 바이트를 먼저 잡는다. 이 값 하나를 검증에도 파싱에도 쓴다.
    body = await request.body()
    # 2. 헤더를 꺼낸다. get() 에 넣는 건 헤더 '이름'이다.
    signature = request.headers.get(SIGNATURE_HEADER)
    event = request.headers.get(EVENT_HEADER)

    # 3. 출처 증명 실패 — 이유와 무관하게 같은 응답(INV-1).
    if not verify_signature(body, signature):
        return Response(status_code=STATUS_REJECTED)

    # 4. 우리가 안 쓰는 이벤트. 비교 대상은 헤더에 담겨 온 '값'이다.
    #    에러가 아니므로 정상 응답을 준다 — ping 에 4xx 를 주면 웹훅이 고장 나 보인다.
    if event != HANDLED_EVENT:
        return Response(status_code=STATUS_IGNORED)

    # 5. 이제야 파싱. 서명을 통과했다 = 인증된 호출자이므로,
    #    깨진 본문은 서버 잘못(5xx)이 아니라 클라이언트 잘못(4xx)이다.
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return Response(status_code=STATUS_REJECTED)

    # ─────────────────────────────────────────────────────────────────
    # TODO(human) ② 멱등성 + enqueue 배선
    #
    # 재료:  request.headers.get(DELIVERY_HEADER)  ·  is_duplicate(...)  ·  enqueue(payload)
    #
    # 판단: 중복이었을 때 **몇 번을 돌려줄 것인가.**
    #   같은 배달을 또 받았다 = 우리가 이미 처리했다 = GitHub 입장에선 성공한 배달이다.
    #   여기서 4xx 를 주면 GitHub 의 전달 기록에 실패로 남고, 멀쩡한 웹훅이 고장 나 보인다.
    #   그런데 "큐에 새로 넣었다"와 "중복이라 버렸다"는 우리에겐 분명 다른 사건이다.
    #   같은 숫자를 써도 되나? 된다면 왜 되나?
    #
    # 순서 판단 하나 더: dedup 검사가 파싱보다 앞인가 뒤인가.
    #   앞에 두면 깨진 body 도 "봤다"로 기록된다 — 재배달로 고쳐 보낼 기회가 사라진다.
    #   뒤에 두면 파싱 비용을 중복에도 매번 치른다.
    #   지금 payload 크기(수십 KB)와 10초 예산을 놓고 어느 쪽이 나은가.
    #
    # 틀리면:
    #   중복에 4xx 를 주면 GitHub UI 가 빨간 X 로 덮인다.
    #   dedup 을 아예 빼면 같은 PR 에 리뷰 코멘트가 두 번 붙는다 — INV-2 위반이다.
    # ─────────────────────────────────────────────────────────────────
    delivery_id = request.headers.get(DELIVERY_HEADER)

    # 이미 처리한 배달. GitHub 입장에선 성공한 배달이므로 실패로 남기지 않는다.
    # OK 가 아니라 IGNORED 인 건 "큐에 넣음"과 "받았지만 아무것도 안 함"이
    # 다른 사건이기 때문 — 값은 같아도 M3 로깅에서 갈린다.
    if is_duplicate(delivery_id):
        return Response(status_code=STATUS_IGNORED)

    enqueue(payload)
    return Response(status_code=STATUS_OK)


# ─────────────────────────────────────────────────────────────────────
# 앱 조립. 라우터를 따로 둔 이유는 M3에서 헬스체크·메트릭 엔드포인트가
# 붙을 때 이 파일이 다시 커지지 않게 하려는 것뿐이다.
# ─────────────────────────────────────────────────────────────────────
from fastapi import FastAPI  # noqa: E402

app = FastAPI(title="PR Review Agent — webhook ingress")
app.include_router(router)
