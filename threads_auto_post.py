# -*- coding: utf-8 -*-
"""
진안사우나(@jinan.sauna) 스레드(Threads) 완전 자동 포스팅 앱
================================================================
홍삼빌호텔 × 성수주조장의 '진안 사우나투어'(핀란드 배럴 사우나 + 토도노이 냉수욕 + 마이산 러닝
+ 호텔 1박 + 딸기막걸리 시음 + 조식, www.jinansauna.kr)를 소개하는 스레드 계정 @jinan.sauna 에
하루 3회 자동 게시합니다.

동작 순서 (홍삼빌호텔 자동 포스팅 앱과 동일 로직):
  1. topics.json 에서 이번 회차 주제를 선택 (순환 방식)
  2. Claude API 로 스레드 스타일 글 생성 (500자 이내, 최근 글과 중복 방지, 시간대 반영)
  3. images/ 폴더에서 랜덤 3장 추출 → GitHub 공개 URL 생성
  4. Threads API 로 캐러셀(3장) + 글 게시
     → 게시 직후 첫 댓글로 문의 전화(1661-3889) 안내 자동 작성
  5. posted_log.json 에 기록 저장 (다음 회차 중복 방지용)
  6. 토큰 만료 임박 시 자동 갱신

필요한 환경변수 (GitHub Secrets):
  ANTHROPIC_API_KEY      : Claude API 키
  THREADS_ACCESS_TOKEN   : Threads 장기 액세스 토큰 (60일 유효, 자동 갱신)
  THREADS_USER_ID        : @jinan.sauna 계정의 Threads 사용자 ID (숫자)
  GH_PAT                 : (선택) 갱신된 토큰을 Secrets 에 자동 저장할 때 사용
  GITHUB_REPOSITORY      : (Actions 가 자동 주입) owner/repo 형식
"""

import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
THREADS_API = "https://graph.threads.net/v1.0"
IMAGE_DIR = "images"
LOG_FILE = "posted_log.json"
TOKEN_FILE = ".token_meta.json"          # 토큰 갱신 날짜 기록
MAX_TEXT_LEN = 480                        # Threads 500자 제한, 여유분 확보
IMAGE_COUNT = 3                           # 랜덤 추출 이미지 수
IMAGE_EXTS = {".jpg", ".jpeg", ".png"}
POSTS_PER_DAY = 3                         # 하루 게시 횟수
RECENT_COMPARE = POSTS_PER_DAY * 3        # 최근 3일치(9개)와 중복 방지
TOKEN_REFRESH_DAYS = 20                   # 토큰 갱신 주기(일)
KST = timezone(timedelta(hours=9))

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
ACCESS_TOKEN = os.environ["THREADS_ACCESS_TOKEN"]
USER_ID = os.environ["THREADS_USER_ID"]
REPO = os.environ.get("GITHUB_REPOSITORY", "")   # 예: "chinyangwoo/jinan-sauna-threads"
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")


def http_json(url, data=None, method=None):
    """간단한 HTTP 요청 헬퍼 (표준 라이브러리만 사용)"""
    if data is not None and not isinstance(data, bytes):
        data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as res:
            return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} 오류: {url}\n응답: {body}") from e


# ─────────────────────────────────────────────
# 시간대(회차) 판별 — 글의 분위기에 반영
# ─────────────────────────────────────────────
def time_slot():
    """현재 한국시간 기준 회차 힌트를 돌려준다."""
    h = datetime.now(KST).hour
    if h < 11:
        return "아침 (출근길·기상 직후에 보는 글. 새벽 러닝, 아침 사우나, 조식 이야기가 어울림)"
    if h < 16:
        return "점심 (나른한 시간. 주말 계획, 피로 회복, 사우나에서 땀 빼는 이야기가 어울림)"
    return "저녁 (퇴근 후 하루 마무리. 막걸리 한 잔, 조용한 진안의 밤, 쉬고 싶다는 공감)"


# ─────────────────────────────────────────────
# 1. 주제 선택 (순환)
# ─────────────────────────────────────────────
def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"count": 0, "posts": []}


def pick_topic(log):
    with open("topics.json", encoding="utf-8") as f:
        cfg = json.load(f)
    topics = cfg["topics"]
    topic = topics[log["count"] % len(topics)]
    return topic, cfg


# ─────────────────────────────────────────────
# 2. Claude 로 글 생성 (MZ 말투 + 댓글 유도)
# ─────────────────────────────────────────────
def generate_post(topic, cfg, log):
    recent = [p["text"] for p in log["posts"][-RECENT_COMPARE:]]
    recent_block = "\n---\n".join(recent) if recent else "(없음)"
    slot = time_slot()

    system = f"""당신은 대한민국 스레드(Threads)에서 조회수가 팡팡 터지는 글을 쓰는 20대 SNS 크리에이터입니다.
전북 진안군 마이산 근처 '{cfg['brand_name']}'이 운영하는 '{cfg['product_name']}'를 소개하는
스레드 계정 @{cfg['threads_handle']} 의 글을 작성합니다.

상품 기본 정보:
{cfg['brand_info']}

패키지 구성 (매 글마다 1~2가지에 집중, 6가지를 골고루 돌아가며):
{chr(10).join('- ' + x for x in cfg['package_items'])}

말투와 표현 (MZ 감성 필수):
- 20대가 친구한테 카톡 보내듯 편한 반말 톤
- 요즘 스레드에서 쓰는 표현을 자연스럽게 1~3개 섞기:
  "찐", "갓생", "~해버렸다", "미쳤다", "국룰", "진심", "TMI",
  "~인 사람 손", "이거 나만 몰랐음?", "개맛도리", "도파민",
  "저장 필수", "~각", "인생샷", "억까 아님"
- 단, 억지로 유행어를 도배하면 오히려 없어 보이니 자연스러운 것만 골라 쓰기
- 짧은 문장 + 잦은 줄바꿈으로 모바일 가독성 극대화
- 이모지는 1~3개만

조회수 터지는 글의 구조:
- 첫 줄: 스크롤을 멈추게 하는 훅 (의외의 고백, 논쟁적 한마디, 공감 백퍼 상황, 숫자 활용)
  예시 스타일: "솔직히 말하면 나만 알고 싶었음", "한국의 핀란드가 전북에 있다는 거 실화?", "80도 사우나에서 나와서 냉수에 풍덩, 이거 못 끊음"
- 중간: 스토리텔링으로 궁금증 유지 (광고 티 절대 금지, 후기/경험담 느낌)
- 웹사이트 www.jinansauna.kr 은 글마다 넣지 말고 3~4번 중 1번 정도만 자연스럽게 언급
- 마지막 줄: 댓글을 부르는 장치 반드시 1개 (매번 다른 방식으로):
  · 밸런스 게임 ("러닝 먼저 vs 사우나 먼저, 님들 선택은?")
  · 경험 소환 ("사우나 갔다가 잠든 적 있는 사람?")
  · 의견 요청 ("이거 나만 그런 거 아니지?")
  · 정보 요청 ("전통주 잘 아는 사람 댓글로 추천 좀")
  · 태그 유도 ("같이 땀 뺄 사람 소환해봐")

지금 게시 시간대: {slot}
→ 이 시간대에 읽는 사람의 상황에 맞게 분위기를 잡을 것

해시태그: 마지막 줄에 2~3개만, {' '.join(cfg['hashtags'])} 중에서 선택
전체 길이: 공백 포함 {MAX_TEXT_LEN}자 이내 (매우 중요!)

절대 금지:
- 최근 게시글과 비슷한 소재/문장/훅/댓글유도 방식 반복
- 과장 광고 표현, 노골적인 예약 유도
- 상품 정보에 없는 가격·할인율·이벤트를 지어내기 (가격은 "1인 99,000원, 평일 월~목 한정·성수기 제외" 그대로만, 매 글마다 넣지는 말 것)
- 사우나·냉수욕·막걸리의 건강 효능을 의학적으로 단정하는 표현 (예: "면역력 올라감", "병이 낫는다"). "개운하다", "정신이 번쩍", "도파민 터짐" 같은 체감 표현은 OK
- 음주 권장·과음 조장 표현 (막걸리는 '시음', '한 잔 맛보기' 수준으로만)
- 호텔이 고기·식재료를 판다는 표현 (바비큐는 시설만 제공, 재료는 직접 준비)
- 유행어 4개 이상 남발 (없어 보임)
- 글 외의 다른 설명, 따옴표, 머리말 출력"""

    user = f"""오늘의 주제: {topic}

최근 게시글 (이것과 겹치지 않게):
{recent_block}

위 주제로 스레드 게시글 본문만 출력해 주세요."""

    body = json.dumps({
        "model": "claude-sonnet-5",
        "max_tokens": 800,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }).encode()

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        data = json.loads(res.read().decode())

    text = "".join(b["text"] for b in data["content"] if b["type"] == "text").strip()
    if len(text) > 495:
        text = text[:495]
    return text


# ─────────────────────────────────────────────
# 3. 랜덤 이미지 3장 → 공개 URL
# ─────────────────────────────────────────────
def pick_images(log):
    """images/ 폴더와 저장소 루트(최상위) 양쪽에서 사진을 모은다."""
    files = []  # (상대경로) 예: "images/sauna_01.jpg" 또는 "coldplunge.png"
    for folder in (IMAGE_DIR, "."):
        if not os.path.isdir(folder):
            continue
        for f in os.listdir(folder):
            if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                files.append(f if folder == "." else f"{folder}/{f}")
    if len(files) < IMAGE_COUNT:
        raise RuntimeError(
            f"이미지가 {len(files)}장뿐입니다. 최소 {IMAGE_COUNT}장이 필요합니다. "
            f"(images/ 폴더 또는 저장소 최상위에 JPG/PNG 업로드)"
        )
    # 직전 게시글과 같은 사진은 가급적 피한다 (사진이 충분할 때만)
    last_used = set(log["posts"][-1]["images"]) if log["posts"] else set()
    pool = [f for f in files if f not in last_used]
    if len(pool) < IMAGE_COUNT:
        pool = files
    chosen = random.sample(pool, IMAGE_COUNT)
    urls = [
        f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{urllib.parse.quote(f)}"
        for f in chosen
    ]
    return chosen, urls


# ─────────────────────────────────────────────
# 4. Threads 캐러셀 게시 (컨테이너 생성 → 게시)
# ─────────────────────────────────────────────
def post_to_threads(text, image_urls):
    # 4-1. 각 이미지를 캐러셀 아이템 컨테이너로 생성
    child_ids = []
    for url in image_urls:
        res = http_json(f"{THREADS_API}/{USER_ID}/threads", {
            "media_type": "IMAGE",
            "image_url": url,
            "is_carousel_item": "true",
            "access_token": ACCESS_TOKEN,
        })
        child_ids.append(res["id"])
        time.sleep(3)

    # 4-2. 캐러셀 컨테이너 생성 (글 + 자식 이미지들)
    res = http_json(f"{THREADS_API}/{USER_ID}/threads", {
        "media_type": "CAROUSEL",
        "children": ",".join(child_ids),
        "text": text,
        "access_token": ACCESS_TOKEN,
    })
    creation_id = res["id"]

    # 4-3. 미디어 처리 대기 후 게시 (Meta 권장: 30초 내외)
    time.sleep(35)
    res = http_json(f"{THREADS_API}/{USER_ID}/threads_publish", {
        "creation_id": creation_id,
        "access_token": ACCESS_TOKEN,
    })
    return res["id"]


# ─────────────────────────────────────────────
# 4-4. 첫 댓글 자동 작성 (문의 전화 안내)
# ─────────────────────────────────────────────
FIRST_COMMENT = "진안 홍삼빌호텔의 사우나팩키지상품에 관한 문의는 1661-3889 로 연락주세요"


def post_first_comment(post_id):
    """게시 직후 본문 글에 고정 안내 댓글을 단다. 실패해도 본문 게시는 유지."""
    try:
        time.sleep(10)  # 게시 반영 대기
        res = http_json(f"{THREADS_API}/{USER_ID}/threads", {
            "media_type": "TEXT",
            "text": FIRST_COMMENT,
            "reply_to_id": post_id,
            "access_token": ACCESS_TOKEN,
        })
        time.sleep(5)
        res = http_json(f"{THREADS_API}/{USER_ID}/threads_publish", {
            "creation_id": res["id"],
            "access_token": ACCESS_TOKEN,
        })
        print(f"💬 첫 댓글 작성 완료! reply id = {res['id']}")
        return res["id"]
    except Exception as e:
        print(f"⚠️ 첫 댓글 작성 실패 (본문은 게시됨): {e}")
        return None


# ─────────────────────────────────────────────
# 5. 토큰 자동 갱신 (만료 60일 → 20일마다 갱신)
# ─────────────────────────────────────────────
def refresh_token_if_needed():
    meta = {}
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, encoding="utf-8") as f:
            meta = json.load(f)
    last = meta.get("refreshed_at")
    if last:
        days = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).days
        if days < TOKEN_REFRESH_DAYS:
            return None  # 아직 갱신 불필요

    try:
        res = http_json(
            f"https://graph.threads.net/refresh_access_token"
            f"?grant_type=th_refresh_token&access_token={ACCESS_TOKEN}"
        )
        new_token = res["access_token"]
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump({"refreshed_at": datetime.now(timezone.utc).isoformat()}, f)
        print("🔄 토큰이 갱신되었습니다.")
        return new_token
    except Exception as e:
        print(f"⚠️ 토큰 갱신 실패 (다음 실행에서 재시도): {e}")
        return None


def update_github_secret(new_token):
    """새 토큰을 GitHub Secret 에 자동 저장 (GH_PAT 이 설정된 경우)"""
    pat = os.environ.get("GH_PAT")
    if not pat or not new_token:
        if new_token:
            print("⚠️ GH_PAT 미설정: GitHub Secrets 의 THREADS_ACCESS_TOKEN 을 수동으로 교체해 주세요.")
            print(f"   새 토큰: {new_token[:20]}... (전체 값은 Actions 로그 보안상 출력 생략)")
        return
    try:
        # PyNaCl 로 시크릿 암호화 업로드
        from base64 import b64encode
        from nacl import encoding, public

        def gh_api(path, method="GET", body=None):
            req = urllib.request.Request(
                f"https://api.github.com{path}",
                data=json.dumps(body).encode() if body else None,
                method=method,
                headers={
                    "Authorization": f"Bearer {pat}",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as res:
                raw = res.read().decode()
                return json.loads(raw) if raw else {}

        key = gh_api(f"/repos/{REPO}/actions/secrets/public-key")
        pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
        sealed = public.SealedBox(pk).encrypt(new_token.encode())
        gh_api(
            f"/repos/{REPO}/actions/secrets/THREADS_ACCESS_TOKEN",
            method="PUT",
            body={"encrypted_value": b64encode(sealed).decode(), "key_id": key["key_id"]},
        )
        print("✅ 새 토큰이 GitHub Secrets 에 자동 저장되었습니다.")
    except Exception as e:
        print(f"⚠️ Secrets 자동 저장 실패, 수동 교체 필요: {e}")


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────
def main():
    log = load_log()
    topic, cfg = pick_topic(log)
    print(f"📌 이번 회차 주제: {topic}")
    print(f"🕒 시간대: {time_slot()}")

    text = generate_post(topic, cfg, log)
    print(f"✍️ 생성된 글 ({len(text)}자):\n{text}\n")

    chosen, urls = pick_images(log)
    print(f"🖼️ 선택된 이미지: {chosen}")

    post_id = post_to_threads(text, urls)
    print(f"🚀 게시 완료! post id = {post_id}")

    reply_id = post_first_comment(post_id)

    # 로그 저장 (최근 50개 유지 = 약 2주치)
    log["count"] += 1
    log["posts"].append({
        "at": datetime.now(KST).strftime("%Y-%m-%d %H:%M"),
        "topic": topic,
        "text": text,
        "images": chosen,
        "post_id": post_id,
        "reply_id": reply_id,
    })
    log["posts"] = log["posts"][-50:]
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    # 토큰 갱신 체크
    new_token = refresh_token_if_needed()
    update_github_secret(new_token)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"❌ 실행 실패: {e}", file=sys.stderr)
        sys.exit(1)
