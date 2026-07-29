"""웹훅 요청이 GitHub에서 왔는지 확인한다 — INV-1이 코드가 되는 자리.

전체 그림에서 ①의 첫 번째 관문. 여기를 통과하지 못한 요청은
파싱도, 큐 진입도, 로깅도 하지 않는다. 아무 일도 일어나지 않는다.

이 모듈은 stdlib만 쓴다(의존성 없음). FastAPI를 모르고, HTTP 상태 코드도 모른다.
"진짜인가?"만 답하고, 그걸 몇 번으로 응답할지는 app.py 의 일이다.
경계를 이렇게 나눠두면 이 함수를 테스트할 때 웹 서버가 필요 없다.

읽고 올 것: learning/lessons/0003-signature-over-bytes.html
"""

import hashlib
import hmac
import os

from dotenv import load_dotenv

load_dotenv()

# GitHub이 서명을 담아 보내는 헤더. sha1 버전(X-Hub-Signature)도 있지만 쓰지 않는다 —
# SHA-1은 충돌 공격이 실증된 해시다.
SIGNATURE_HEADER = "X-Hub-Signature-256"

# 헤더 값의 실제 형태: "sha256=a8f3...9c2"  (알고리즘 접두사가 붙어서 온다)
SIGNATURE_PREFIX = "sha256="


# ─────────────────────────────────────────────────────────────────────
# TODO(human) ① secret 이 없을 때 어떻게 할 것인가
#
# GitHub 웹훅 설정에서 Secret 칸을 비워두면, GitHub은 서명 헤더를 아예 안 보낸다.
# 우리 쪽 .env 에 WEBHOOK_SECRET 이 없는 경우도 마찬가지로 검증이 불가능해진다.
#
# 판단: 이 상태에서 서버가 떠도 되나?
#   · 뜨게 두고 요청마다 거부한다   → 엔드포인트는 살아있는데 아무것도 못 받는다
#   · 부팅 자체를 거부한다(fail-fast) → 배포가 실패한다. 시끄럽다
#   · 검증을 건너뛴다                → 절대 아님. 왜 절대인지 말할 수 있어야 한다
#
# 힌트: invariants.md 의 표현은 "규칙을 잊을 수 있는 사람은 있어도,
#       DB가 거부하는 건 아무도 못 뚫는다"다. 여기서 '아무도 못 뚫게' 만드는
#       가장 이른 시점이 언제인가.
#
# 틀리면:
#   검증을 건너뛰면 INV-1이 조용히 꺼진다. 로그도 안 남고 테스트도 통과한다.
#   "개발 편의를 위해 secret 없으면 통과"가 프로덕션에 그대로 나가는 게
#   이 종류 사고의 표준 시나리오다.
#
# 아래 한 줄을 고쳐서 판단을 표현할 것 (필요하면 여러 줄이 돼도 된다).
# ─────────────────────────────────────────────────────────────────────
# 판단: fail-fast. 기본값을 주지 않고, 없으면 import 시점에 터진다.
#
# 이유 — secret 이 없다는 건 "검증을 할 수 없다"는 뜻이고, 그 상태로 뜬 서버는
# 살아있는 것처럼 보이면서 INV-1을 못 지킨다. 조용히 틀리는 것보다 시끄럽게
# 죽는 게 낫다(base.py 의 refusal 처리와 같은 원칙).
#
# 부팅 시점에 거는 이유: 요청이 올 때까지 기다리면, 첫 배포 후 첫 웹훅이
# 올 때까지 아무도 모른다. '아무도 못 뚫게' 만드는 가장 이른 시점이 여기다.
#
# str 이 아니라 bytes 로 굳혀둔다 — hmac.new(key=...) 가 bytes 를 요구하고,
# 매 요청마다 .encode() 하는 건 같은 변환을 반복하는 것뿐이다.
_secret = os.getenv("WEBHOOK_SECRET")
if not _secret:
    raise RuntimeError(
        "WEBHOOK_SECRET 이 없다. GitHub 웹훅 설정의 Secret 과 같은 값을 .env 에 넣을 것. "
        "이게 없으면 INV-1(서명 검증)을 지킬 수 없으므로 서버를 띄우지 않는다."
    )
WEBHOOK_SECRET = _secret.encode()


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """요청이 우리 secret 을 아는 쪽에서 왔는지 확인한다.

    Args:
        raw_body: 손대지 않은 요청 본문 바이트. **파싱했다 되돌린 값이면 절대 안 맞는다**
                  (Lesson 03 함정 ①). app.py 에서 `await request.body()` 로 얻은 그 값.
        signature_header: X-Hub-Signature-256 헤더 값. 없으면 None.

    Returns:
        통과하면 True, 아니면 False.

        왜 bool 인가 — 실패 '이유'를 돌려주지 않는 게 의도다. 호출부가 이유별로
        다른 응답을 만들 수 없게 해서, INV-1의 "이유와 무관하게 항상 같은 400"을
        타입 수준에서 거든다. 디버깅이 필요하면 로그로 남긴다(M3에서 붙는다).
    """
    # ─────────────────────────────────────────────────────────────────
    # TODO(human) ② 검증 본문
    #
    # 필요한 재료는 위에 다 있다: WEBHOOK_SECRET · SIGNATURE_PREFIX · hmac · hashlib.
    #
    # 판단 세 개:
    #   (a) 헤더가 None 이거나 "sha256=" 로 시작하지 않으면?
    #       — 여기서 일찍 빠져나가는 것과, 그냥 계속 계산해서 어차피 불일치로
    #         떨어지게 두는 것 중 뭐가 나은가. 각각 무엇이 관측 가능해지나.
    #
    #   (b) 우리 쪽 서명 계산.
    #       hmac.new(key, msg, digestmod).hexdigest() 가 16진수 문자열을 준다.
    #       key 는 bytes 여야 한다 — str 을 그대로 넣으면 TypeError.
    #
    #   (c) 비교.
    #       `==` 를 쓰면 안 되는 이유는 Lesson 03 함정 ②. 대신 뭘 쓰나?
    #       그리고 접두사가 붙은 헤더 원문과 우리가 만든 16진수 문자열을
    #       어느 형태로 맞춰서 비교할 것인가 (양쪽에 접두사를 붙이든, 양쪽에서 떼든
    #       — 한쪽만 처리하면 영원히 불일치다).
    #
    # 틀리면:
    #   (c)를 `==` 로 쓰면 돌아간다. 테스트도 통과한다. 타이밍 공격에만 열린다.
    #   — 즉 이 실수는 실행해서는 발견되지 않는다. 그래서 여기 적어둔다.
    #
    # ⚠️ 채우기 전엔 모든 요청이 거부된다. 그게 의도다 —
    #    검증이 미완성일 때의 기본값은 '통과'가 아니라 '거부'여야 한다.
    # ─────────────────────────────────────────────────────────────────
    # (a) 헤더가 없거나 형태가 다르면 계산할 것도 없다.
    #     여기서 일찍 빠져나가도 되는 이유: '헤더가 있었나'는 비밀이 아니다.
    #     보낸 쪽이 이미 아는 사실이라 타이밍으로 새어나갈 정보가 없다.
    #     타이밍을 맞춰야 하는 건 아래 (c)의 서명 대조 한 자리뿐이다.
    if not signature_header or not signature_header.startswith(SIGNATURE_PREFIX):
        return False

    # (b) 우리 쪽에서 같은 지문을 다시 찍는다.
    #     msg 는 반드시 raw_body — 검증하려는 대상 그 자체다.
    #     digestmod 는 생략할 수 없다. 헤더 이름(sha256)과 반드시 같아야 한다.
    expected = hmac.new(
        key=WEBHOOK_SECRET,
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    # (c) 접두사를 뗀 쪽으로 형태를 맞춰서 대조한다.
    #     `==` 가 아니라 compare_digest — 앞에서부터 비교하다 멈추지 않고
    #     항상 전체를 훑는다. 이 한 줄이 서명을 한 글자씩 유출시키지 않는 이유다.
    received = signature_header.removeprefix(SIGNATURE_PREFIX)
    return hmac.compare_digest(expected, received)
