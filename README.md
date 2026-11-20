# 공장 주문·출고 도우미 (factory-ops)

카카오톡 주문 → 주문장 정리 → 택배/화물 분기 → 송장·배차 → 거래처 알림톡 → 자재 재고 → 월말 거래명세표까지,
부모님 식품 공장의 업무를 자동화하는 웹 시스템입니다.

- **백엔드**: Python 3.11 · FastAPI · Google Sheets(gspread) · Claude API · ReportLab — `backend/`
- **프론트**: React 18 · Vite · TypeScript · Tailwind · lucide-react — `frontend/`
- **배포**: Render(백엔드) + Vercel(프론트) + GitHub Actions(정기작업)

| 분기 | 모듈 | 하는 일 |
|---|---|---|
| 1 | `q1_masters` `q1_orders` `q1_shipping` | 카톡 주문 AI 정리, 주문장 저장, 택배/화물 자동 분기, 택배 엑셀, 배차 문자 |
| 2 | `q2_self_order` `q2_briefing` | 거래처 전용 주문 링크(/order/…), 매일 아침 부모님 카톡 브리핑, 카카오 연결 |
| 3 | `q3_tracking` `q3_notify` `q3_marketplace` | 송장 엑셀 역등록, 화물 차량정보, 거래처 출고 알림톡, 스마트스토어·쿠팡 엑셀 수집 |
| 4 | `q4_inventory` `q4_settlement` `q4_reorder` | 자재 자동 차감·경고·소진 예측, 거래명세표 PDF·발송·수금, 단골 발주주기 리마인드 |

---

## 1. Codespaces 에서 바로 실행 (구글·카카오 연결 전, 예시 데이터)

1. GitHub 저장소 → **Code → Codespaces → Create codespace** (Python·Node·패키지 자동 설치)
2. 터미널 두 개:
   ```bash
   # 터미널 1 — 백엔드
   cd backend && uvicorn app.main:app --reload --port 8000
   # 터미널 2 — 프론트
   cd frontend && npm install && npm run dev
   ```
3. 포트 5173 을 열면 화면이 나와요. `SHEETS_BACKEND=memory` 에서는 예시 품목·거래처·지난 두 달 주문이 들어 있고,
   서버를 끄면 사라져요. API 문서는 포트 8000 의 `/docs`.

테스트:
```bash
cd backend && python -m pytest -q && python -m mypy app --ignore-missing-imports
cd frontend && npm run build
```

---

## 2. Google Sheets 연결

1. [Google Cloud Console](https://console.cloud.google.com/) → 프로젝트 → **Google Sheets API 사용 설정**
2. **서비스 계정** 만들기 → **키 → JSON** 내려받기 (git 에 올리지 마세요)
3. 빈 스프레드시트 2개 만들기
   - `공장 주문장` — 부모님과 공유하는 시트 → `GOOGLE_SPREADSHEET_ID`
   - `공장 시스템` — 카카오 토큰·발송기록 (부모님과 공유 X) → `SYSTEM_SPREADSHEET_ID`
4. 두 시트 모두 서비스 계정 이메일을 **편집자**로 공유
5. 탭 자동 생성:
   ```bash
   cd backend
   export GOOGLE_SPREADSHEET_ID=... SYSTEM_SPREADSHEET_ID=...
   export GOOGLE_SERVICE_ACCOUNT_JSON="$(cat ~/Downloads/키파일.json)"
   python -m scripts.init_sheets --demo     # --demo: 예시 품목·거래처 (빈 시트일 때만)
   ```
   만들어지는 탭: `주문장 · 거래처 · 품목 · 자재재고 · 월말정산 · _설정 · _기록 · _상품매핑 · _재고이력`
   (시스템 시트: `토큰 · 발송기록`)

> 부모님이 **열 순서를 바꾸거나 메모 열·수식을 추가해도** 괜찮습니다. 서버는 헤더 이름으로 열을 찾고 바뀐 칸만 씁니다.
> 단, **1행 헤더 이름은 바꾸지 마세요.** `_설정` 탭의 '값' 칸은 시트에서 직접 고쳐도 됩니다.

---

## 3. 배포

### 백엔드 — Render
1. **New → Blueprint** → 이 저장소 (루트 `render.yaml` 자동 인식)
2. 빈 환경변수 채우기 — 목록과 설명은 `backend/.env.example`
3. `https://<서비스>.onrender.com/api/health` 가 `{"ok": true}` 이면 성공
4. `APP_ENV=prod` 에서 필수 설정이 빠지면 서버가 시작하지 않고 무엇이 빠졌는지 로그에 알려 줘요.

### 프론트 — Vercel
1. **New Project** → 이 저장소 → Root Directory `frontend`
2. 환경변수 `VITE_API_BASE_URL=https://<서비스>.onrender.com`
3. 배포 주소를 Render 의 `PUBLIC_WEB_URL`, `FRONTEND_ORIGINS` 에 넣고 Render 재배포

### 정기작업 — GitHub Actions
저장소 **Settings → Secrets and variables → Actions**
- Variables: `API_BASE_URL` = Render 주소
- Secrets: `JOB_SECRET` = Render 의 JOB_SECRET 값

| 파일 | 일정 (KST) | 작업 |
|---|---|---|
| `jobs-cron.yml` | 매일 07:40 | 거래처 주문주기 계산 |
| | 매일 08:00 | 아침 브리핑 카톡 |
| | 월 04:00 | 카카오 토큰 갱신 |
| | 매월 1일 09:00 | 지난달 거래명세표 생성 + 안내 |
| `keep-warm.yml` | 영업시간 10분마다 | 서버 잠들지 않게 깨우기 |

Actions 탭에서 `jobs-cron` → **Run workflow** 로 아무 작업이나 바로 실행해 볼 수 있어요.

### 카카오·솔라피·메일
- 카카오/알림톡: **`docs/카카오_연동_가이드.md`**, 템플릿 문구: **`docs/알림톡_템플릿.md`**
- 메일: Gmail 이면 2단계 인증 → 앱 비밀번호 → `SMTP_USER`, `SMTP_PASSWORD`

---

## 4. 구조

```
backend/app/
├─ main.py              FastAPI 생성, 활성 모듈 로드, 오류를 한국어 메시지로
├─ config.py            환경변수 (+ 운영 필수값 점검, 연동 경고)
├─ context.py           공유 객체(시트·저장소·외부API·이벤트·작업·브리핑) + 시작 준비
├─ demo_data.py         메모리 모드 예시 데이터
├─ core/                시트 스키마·캐시·저장소·이벤트·정기작업·브리핑·인증·서명·업로드
├─ schemas/             API 입출력 모델
├─ repositories/        시트 탭별 읽기/쓰기
├─ services/            택배/화물 분기, 이름 매칭, 주문 서비스
├─ integrations/        Claude · 카카오(나에게) · 솔라피(알림톡) · SMTP · http
├─ api/                 공통 엔드포인트, 인증 의존성
└─ modules/             분기별 기능 11개 (라우터 + 이벤트 구독 + 정기작업 + 브리핑 섹션)
backend/fonts/          거래명세표 PDF 한글 폰트 (Noto Sans KR, SIL OFL)
frontend/src/
├─ api/                 fetch 래퍼 · 타입 · 엔드포인트
├─ components/          큰 버튼 UI, 주문 폼, 주문 상세, 출고 대화상자
├─ layouts/             PC 왼쪽 메뉴 / 휴대폰 아래 탭
└─ pages/               홈·주문 넣기·주문 목록·출고·재고·정산·리마인드·오픈마켓·설정·더보기 + public/SelfOrder
```

**모듈끼리는 이벤트로만 연결**돼요. 출고 완료 → `order.shipped` 이벤트 → 알림톡(3분기)·자재 차감(4분기)이 각자 처리.
새 기능은 `modules/<이름>/` 폴더를 만들고 `register()` 에서 라우터·이벤트·작업·브리핑 섹션을 등록하면 붙어요.

### 이벤트
| 이벤트 | 발행 | 구독 |
|---|---|---|
| `order.created` | 주문 생성 | 셀프주문 카톡 알림, 주문 접수 알림톡 |
| `order.shipped` | 출고 완료 | 출고 알림톡, 자재 차감 |
| `order.shipping_info` | 출고 후 송장·차량 추가 | 출고 알림톡 |
| `order.unshipped` | 출고 되돌리기 | 자재 복원 |
| `order.cancelled` | 주문 취소 | 출고 후 취소면 자재 복원 |

---

## 5. 알아둘 점
- **택배사 엑셀 양식**: `carriers/logen.py`, `carriers/cj.py` 는 실제 업로드 양식과 대조 전 초안이에요(화면에 '양식 확인 필요').
  택배사 프로그램에서 받은 양식의 1행 열 이름·순서로 바꿔 주세요. '공통 양식'은 그대로 써도 돼요.
- **오픈마켓**: 판매자센터에서 내려받은 주문 엑셀을 올리는 방식이에요. 열 이름이 바뀌면 `q3_marketplace/adapters.py` 후보에 추가.
  (API 자동 수집은 넣지 않았어요. 셀러 API 승인 후 `adapters.py` 옆에 붙이면 됩니다.)
- **세금**: 품목 '과세구분'이 면세가 아니면 공급가액의 10% 를 세액으로 계산해요. 실제 신고 기준은 세무사와 확인하세요.
- **AI 모델**: 기본 `claude-haiku-5-5`(도구 강제 호출). 지원하지 않는 모델로 바꾸면 자동으로 `tool_choice=auto` 재시도.
- **시트 쿼터**: 탭 전체를 한 번에 읽어 30초 캐시, 쓰기는 batch, 429 는 지수 백오프로 재시도.
