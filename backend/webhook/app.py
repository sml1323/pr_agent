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
# TODO(human) ① 응답 계약 — 세 가지 결과에 각각 몇 번을 줄 것인가
#
# 아래 상수 세 개를 정하는 일이다. 숫자만 고르는 게 아니라 "왜 그 숫자인가"가
# 답이어야 한다. Lesson 03 함정 ③을 읽었으면 재료는 다 있다.
#
#   OK        큐에 넣는 데 성공했다.
#             영상은 200 을 두 번 명시했다 [01:28:30] [01:31:39].
#             의미상으로는 202(Accepted, "받았고 나중에 처리함")가 더 정확하다.
#             어느 쪽이든 **하나로 고정하고 그 선택을 적어둘 것.**
#
#   REJECTED  서명이 틀렸다 / 헤더가 없다 / 본문이 깨졌다.
#             GitHub 공식 예제는 403, 우리 INV-1은 "이유와 무관하게 항상 같은 400".
#             왜 획일화하는지 말할 수 있어야 한다.
#
#   IGNORED   pull_request 가 아닌 이벤트(ping, push, issues...).
#             이건 아직 아무도 안 가르쳐준 판단이다. 힌트:
#             웹훅을 처음 등록하면 GitHub 이 제일 먼저 ping 을 쏜다.
#             거기에 4xx 를 주면 GitHub UI 의 그 웹훅에 빨간 X 가 붙는다.
#             "우리가 안 쓰는 이벤트"는 **에러인가, 정상인가?**
#
# 틀리면:
#   IGNORED 를 4xx 로 두면 웹훅이 고장 난 것처럼 보인다. 실제로는 멀쩡한데
#   그 표시를 보고 설정을 뒤지게 된다 — 시간을 태우는 종류의 거짓 신호다.
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
    # ─────────────────────────────────────────────────────────────────
    # TODO(human) ② 핸들러 본문
    #
    # 재료:
    #   await request.body()          → raw bytes (파싱 전!)
    #   request.headers.get(이름)      → 헤더 값 또는 None
    #   verify_signature(body, sig)   → bool
    #   json.loads(body)              → dict, 실패 시 json.JSONDecodeError
    #   Response(status_code=...)     → 본문 없는 응답
    #
    # 순서는 Lesson 03에서 다뤘다. 손으로 다시 세워볼 것 —
    # 무엇이 무엇보다 반드시 먼저여야 하는지, 그 이유와 함께.
    #
    # 판단 두 개:
    #   (a) 이벤트 필터를 서명 검증 **앞**에 둘 것인가 뒤에 둘 것인가.
    #       영상이 두 군데서 다르게 말한다(03-build-plan.md M1 절에 기록).
    #       X-GitHub-Event 는 헤더라 body 를 안 건드리고도 읽을 수 있다 —
    #       그래서 실제 위험은 작다. 그럼에도 기본값을 하나로 정해야 한다.
    #
    #   (b) json.loads 가 터지는 경우.
    #       여기가 M1의 진짜 체크포인트다. 영상에서 빌더는 완료를 선언했고
    #       독립 검증자가 이 자리에서 500 크래시를 잡아냈다 [02:38:39].
    #       예외를 잡지 않으면 FastAPI 가 알아서 처리해버린다 — 즉 우리 통제 밖이다.
    #
    # 아직 안 하는 것:
    #   enqueue 는 M1 (3/3)에서 queue/router.py 가 생기면 붙는다.
    #   지금은 파싱까지 성공하면 STATUS_OK 를 돌려주면 된다.
    #   DELIVERY_HEADER 는 읽어만 두고 쓰지 않아도 된다(다음 파트의 재료).
    #
    # 틀리면:
    #   순서를 뒤집으면 "서명을 안 본 요청"에 파싱 로직이 먼저 도는 표면이 생긴다.
    #   (b)를 빠뜨리면 깨진 body 하나로 500 이 뜨고, 서버 모니터링에 헛경보가 쌓인다.
    # ─────────────────────────────────────────────────────────────────

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

    # 6. 여기까지 오면 진짜다. M1 (3/3)에서 이 자리에 enqueue(payload) 가 붙는다.
    #    지금 payload 는 "파싱 가능한가"를 확인하려고 만들었을 뿐 쓰이지 않는다.
    _ = payload
    return Response(status_code=STATUS_OK)


# ─────────────────────────────────────────────────────────────────────
# 앱 조립. 라우터를 따로 둔 이유는 M3에서 헬스체크·메트릭 엔드포인트가
# 붙을 때 이 파일이 다시 커지지 않게 하려는 것뿐이다.
# ─────────────────────────────────────────────────────────────────────
from fastapi import FastAPI  # noqa: E402

app = FastAPI(title="PR Review Agent — webhook ingress")
app.include_router(router)
