# 시스템 인수인계 메모 (새 대화에서 이 파일부터 읽으세요)

최종 업데이트: 2026-08-02

## 한 줄 요약
네이버 홈판 경제 블로그(브랜드: 경제비버) 자동 생성 시스템. 매일 새벽 클라우드 루틴이
기사→본문+이미지4장을 만들어 이 저장소 output/ 에 커밋. 사용자는 GitHub Desktop으로
받아 네이버에 복붙 발행. (자동 발행은 네이버 정책상 불가 — 복붙까지가 자동화 범위)

## 지금 상태: 시스템 구축 완료, 실제 발행 검증 대기
- 코드/규칙/이미지 파이프라인 전부 완성. 규격 위반 0으로 빌드됨.
- 아직 사용자가 네이버에 실제 1회 발행은 안 해봄 (다음 할 일).

## 폴더 구조
```
output/{MMDD}/{순번}/   ← 사용자가 매일 보는 결과물
   0번 본문.txt          붙여넣기용 (제목+본문, 점자빈칸 문단간격)
   1~4번 사진.jpg        1080px JPG, 【N번 사진】 마커 자리에 삽입
_engine/                ← 코드·규칙 (사용자는 안 봄)
   build_posts.py        기사JSON → output 생성 (핵심)
   common_utils.py       이미지 카드 SVG 빌더들
   image_sourcing.py     Wikimedia/Openverse 이미지 소싱
   fetch_logo/photo/portrait.py, build_photo/ticker_library.py  자산 수집 CLI
   PROMPT_V1.md          경제 주제 생성 규칙 (제목/본문/썸네일/반응장치/가독성/스키마)
   PROMPT_AUTO_V1.md     자동차 주제 규칙 (보류 상태)
   articles_test.json    시연용 기사 1건
assets/                 ← 이미지 재료 (로고 22종/사진/인물, 자동 수집)
state/                  ← 중복방지 기록 seen_articles.json
```

## 빌드/실행 (반드시 저장소 루트에서)
```
python _engine/build_posts.py _engine/articles.json 0802
```
→ output/0802/{순번}/ 에 0번 본문.txt + N번 사진.jpg 생성. build_report.json에 검증 결과.

## 확정된 규칙 (사용자 피드백으로 굳은 것 — 함부로 바꾸지 말 것)
- 문장 중간 줄바꿈 금지. 문단(2~3문장) = 한 줄, 네이버가 감쌈. 110자 넘으면 문장경계서 빈줄.
- 소제목 📌 밑에 구분선 ━×19 자동. 콜아웃 💡(핵심/관점)·👉는 독립문단.
- 여운형 질문은 글 맨끝(정리 다음, 면책 앞). '댓글' 단어 절대 금지, 구걸 금지.
- 면책 짧게: "※ 본 게시글은 투자 권유가 아니며, 투자 판단과 책임은 본인에게 있습니다."
- 이미지 4장은 빌더가 글자수 균등 배치 (body에 마커 안 넣어도 됨). 마지막은 정리카드=맨끝.
- ⭐ images 1번 = 반드시 '홈판 대표 썸네일'. 종목 등락=stock_thumbnail(곤두박질/급등 차트),
  그 외=thumbnail(사진배경+2줄 스레드체 카피+민트강조+경제비버 배지). 데이터카드로 만들지 말 것!
  2~4번만 bar/rank/summary/number/photo_card. (PROMPT_V1.md 7절 참고)
- 이미지 = 1080px JPG q92 (폴더 540KB). 종목기사 썸네일은 한국식 색(상승 빨강/하락 파랑).
- 볼드마킹(▶)은 폐기 (네이버 미적용). 강조는 이모지+카드가 담당.

## 이미지 종류 (common_utils.py)
photo_card(사진배경+숫자) / bar_card(막대) / rank_card(순위) / summary_card(정리3줄)
/ number_card(숫자카드) / thumbnail(사진2줄카피) / stock_thumbnail(주가 곤두박질/급등 차트)

## 이미지 소싱 한계 (실측 확정)
- Wikimedia Commons 직접 = 고해상 보장, 채택. Openverse = 축소본 많아 실측검증 필수.
- Unsplash/Freepik/Pexels = 차단(401/403). korea.kr = 720px 상한.
- 감정 스톡사진(슬픈 직장인 등) 무료로 거의 없음 → 종목은 차트 직접 생성, 생활감정은 사물 대체.
- 로고/인물은 상표·초상. 재게시 가능 라이선스(PD/CC/KOGL)만, 반드시 육안 검수.

## 자동화 루틴 (claude.ai 스케줄)
- 경제: trig_0185N5DzZMWkwwVQFHaNWC1u (활성, 매일 06:00 KST)
- 자동차: trig_017PWa529j3mbdgB8Tq96PtC (비활성/보류)
- 환경: env_01R9XQUDmstnAoB8JoQWebwF (네트워크 무제한). 저장소·프롬프트 연결됨.
- 주의: RemoteTrigger 부분 업데이트가 sources/프롬프트를 지운 적 있음 → update 시 전체 유지.

## 확장 방법 (자동차/건강 등 새 주제)
GitHub 링크 공유 방식으로 무한 확장. 새 주제 = 새 저장소 복제:
1. _engine 코드는 100% 재사용
2. 바꿀 것 4개: 브랜드명(build_posts.py 기본값) / 사진검색어(build_photo_library.py CATEGORIES)
   / 주제규칙(PROMPT) / RSS소스(루틴 프롬프트)
3. 새 저장소 Public → 담당자에게 output 폴더 링크 공유 → 각자 복붙
4. 주제별로 분리돼야 유사문서 회피됨 (같은 공장 티 안 남)

## 다음 할 일 (우선순위)
1. [사용자] 경제 output/0802/1 을 네이버에 실제 발행 → 홈판 노출·저품질·문단·이미지 검증
2. 발행 중 걸린 디테일만 새 짧은 대화로 수정
3. 검증되면 config.json으로 주제설정 중앙화(복제 5분화) → 자동차/건강 복제
