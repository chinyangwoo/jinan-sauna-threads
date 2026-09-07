# 진안사우나(@jinan.sauna) 스레드 완전 자동 포스팅 앱 🧖🤖

사진만 폴더에 넣어두면, Claude AI가 글을 쓰고 **하루 3번(오전 8시 · 낮 12시 30분 · 저녁 7시)** 랜덤 사진 3장과 함께 스레드 계정 **@jinan.sauna** 에 자동 게시합니다. 홍삼빌호텔 자동 포스팅 앱과 동일한 구조이며, **서버 비용 0원** — GitHub Actions가 무료로 24시간 돌아갑니다. PC를 꺼놔도 됩니다.

소개 상품: **진안 사우나투어** (www.jinansauna.kr) = 핀란드 배럴 사우나 + 토도노이 냉수욕 + 마이산 사우나러닝 + 홍삼빌호텔 1박 + 성수주조장 딸기막걸리 시음 + 제철 조식 (1인 99,000원, 월~목 한정)

---

## 동작 원리

```
[사장님]  images/ 폴더에 사진 업로드 (끝!)
    ↓
[하루 3회 자동 실행]
    1. topics.json 의 주제 18개를 순서대로 선택
    2. Claude AI가 스레드 스타일 글 작성
       (게시 시간대 반영 · 최근 9개 글과 중복 방지)
    3. images/ 에서 랜덤 3장 추출 (직전 회차와 겹치지 않게)
    4. 스레드에 글 + 사진 3장 캐러셀 게시
    5. 기록 저장 → 다음 글에서 같은 내용 반복 안 함
```

---

## 최초 설정 (약 30분, 한 번만 하면 됩니다)

### 1단계. GitHub 저장소 만들기
1. https://github.com 로그인 → **New repository** 클릭
2. 이름: `jinan-sauna-threads` (아무거나 가능)
3. **Public(공개)** 으로 설정 ← 중요! 스레드가 이미지를 가져가려면 공개여야 합니다
4. 이 폴더의 파일 전체를 저장소에 업로드 (웹에서 드래그&드롭 가능)
   - `.github/workflows/post.yml` 은 폴더 구조 그대로 올려야 합니다 (숨김 폴더 주의)

> ⚠️ 저장소가 공개이므로 **홍보용 사진만** 넣으세요. 개인 사진·문서는 넣지 마세요.

### 2단계. Meta 개발자 앱 만들기 (Threads API 권한)
홍삼빌호텔 때 만든 Meta 앱을 **그대로 재사용**할 수 있습니다. 새 앱을 만들 필요 없이 테스터에 계정만 추가하세요.
1. https://developers.facebook.com → 기존 앱 선택 (없으면 **앱 만들기 → "Threads API 액세스"**)
2. **Threads API 사용 사례 → 설정**에서 권한 확인: `threads_basic`, `threads_content_publish`
3. **역할 → Threads 테스터**에 **@jinan.sauna** 계정 추가
4. 스레드 앱에 **@jinan.sauna 로 로그인** → **설정 → 계정 → 웹사이트 권한 → 초대** 수락
5. 개발자 대시보드 → **그래프 API 탐색기** → 도메인 `.threads.net` → **@jinan.sauna 계정으로** Generate Threads Access Token
6. 1시간 안에 장기 토큰으로 교환 (브라우저 주소창):
   ```
   https://graph.threads.net/access_token?grant_type=th_exchange_token&client_secret=앱시크릿&access_token=단기토큰
   ```
   결과의 `"access_token"` 값을 **따옴표 빼고** 복사

> ⚠️ 토큰은 **반드시 @jinan.sauna 계정으로 로그인한 상태**에서 발급해야 합니다. 홍삼빌호텔 계정 토큰을 쓰면 홍삼빌호텔 계정에 글이 올라갑니다.

### 3단계. Threads 사용자 ID 확인
브라우저 주소창에 아래를 입력 (토큰 부분만 교체):
```
https://graph.threads.net/v1.0/me?fields=id,username&access_token=여기에토큰붙여넣기
```
→ `"username": "jinan.sauna"` 인지 확인하고 `"id": "숫자"` 를 복사해 둡니다.

### 4단계. Claude API 키
홍삼빌호텔에서 쓰는 키를 그대로 써도 되고, 새로 만들어도 됩니다.
https://console.anthropic.com → **API Keys → Create Key** → `sk-ant-...` 복사
(하루 3회 글 생성 비용은 월 약 2,000~3,000원 수준)

### 5단계. GitHub Secrets 등록
저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | 4단계의 Claude API 키 |
| `THREADS_ACCESS_TOKEN` | 2단계의 장기 액세스 토큰 (@jinan.sauna 계정) |
| `THREADS_USER_ID` | 3단계의 숫자 ID |
| `GH_PAT` (선택) | 갱신된 토큰 자동 저장용 개인 토큰 |

**GH_PAT 만들기:** GitHub 프로필 → Settings → Developer settings → Fine-grained tokens → Generate new token → Repository access: 이 저장소만 → Permissions → **Secrets: Read and write** → 생성된 `github_pat_...` 를 `GH_PAT` Secret 으로 등록.
안 해도 되지만, 그 경우 20일에 한 번 Actions 로그 안내에 따라 토큰을 수동 교체해야 합니다.

### 6단계. 사진 넣고 테스트
1. `images/` 폴더에 사우나·러닝·조식·전통주·객실 사진을 업로드 (JPG/PNG, 8MB 이하, **파일명은 영문·숫자**: `sauna_01.jpg` 등)
2. 저장소 → **Actions → 진안사우나 스레드 자동 포스팅 → Run workflow** 클릭 → 1~2분 뒤 @jinan.sauna 확인!

---

## 평소 사용법

- **사진 추가/교체**: `images/` 폴더에 파일 넣기 — 이게 전부입니다
- **주제 바꾸기**: `topics.json` 의 `topics` 목록 수정 (시즌 이벤트, 프로모션 등)
- **패키지 구성 바꾸기**: `topics.json` 의 `package_items` 수정
- **시간 바꾸기**: `.github/workflows/post.yml` 의 cron 수정 (UTC 기준 = 한국시간 −9시간)
- **글 톤 바꾸기**: `threads_auto_post.py` 안의 프롬프트(system 부분) 수정
- **하루 횟수 줄이기**: post.yml 에서 cron 줄 삭제

## 자주 묻는 질문

**Q. 게시가 안 돼요.**
Actions 탭 → 실패한 실행 클릭 → 로그 확인. 대부분 토큰 만료(재발급 후 Secret 교체) 또는 이미지 파일명의 한글/특수문자 문제입니다.

**Q. 홍삼빌호텔 계정에 글이 올라갔어요.**
토큰을 홍삼빌호텔 계정으로 발급한 것입니다. @jinan.sauna 로 로그인한 뒤 토큰을 다시 발급해 `THREADS_ACCESS_TOKEN` 과 `THREADS_USER_ID` 를 교체하세요.

**Q. 사진이 3장 미만이면?**
게시를 건너뛰고 오류 로그를 남깁니다. 최소 3장, 넉넉히 20~30장을 넣어두면 매번 다른 조합이 나갑니다.

**Q. Threads API 게시 한도는?**
계정당 24시간에 250회 — 하루 3회는 여유가 아주 많습니다.
