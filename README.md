# AI 활용 외국어 말하기 학습에서 교정적 피드백의 시점 연구 — 실험 시스템

교정적 피드백 **제시 시점**(User Trigger / AI Decision / Delayed)을 비교하는 Formative Study용 웹 시스템.

- 서버: FastAPI (Python 3.11+) · 화면: Vanilla JS (ES modules) · 글꼴: Pretendard
- 대화·피드백·음성(TTS): OpenAI · 음성 인식(STT): 브라우저 내장 Web Speech API → **Chrome 필수**
- 로그: 로컬 `data/` 폴더 (JSONL + JSON), Admin 화면에서 CSV/ZIP 내려받기

---

## 1. 실행

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # OPENAI_API_KEY 입력
python run.py                                          # → http://127.0.0.1:8000
```

- 코드 입력란에 `admin` → 관리자 화면 (참가자 코드 생성 → 참가자는 그 코드로 입장)
- **MOCK 모드**: API 키가 없거나 `.env`에 `MOCK_LLM=1` 이면 가짜 응답으로 동작 (화면·흐름·로그 점검용, 비용 없음)
- **직접 입력 모드**: 주소 뒤에 `?typing=1` → 대화 화면에 텍스트 입력칸이 생김 (파일럿·디버깅용, 로그에 `input: typed`로 기록)
- 다른 PC에서 접속하려면 `.env`의 `HOST=0.0.0.0`. 단, 마이크는 `localhost` 또는 HTTPS에서만 허용됨

`.env` 주요 값: `OPENAI_API_KEY`, `CHAT_MODEL`, `FEEDBACK_MODEL`, `TTS_MODEL`, `TTS_VOICE`, `MOCK_LLM`

---

## 2. 파일 구조

```
feedback-timing-study/
├── run.py · requirements.txt · .env.example
├── config/                        # 코드 수정 없이 바꾸는 값 (매 요청마다 다시 읽음)
│   ├── settings.json              # 연구명, admin 코드, 세션 시간, 권장 발화 길이, STT 언어, 개입 파라미터
│   ├── topics.json                # 대화 주제 목록 (Admin 드롭다운) — label: 화면 표시, hint: AI용 설명
│   ├── tasks.json                 # 세 조건 이름·설명 문구, Task 안내 규칙
│   ├── annotation.json            # Annotation 질문과 조건별 적용 규칙
│   └── survey.json                # 세션 설문 문항, 자유 응답 예시(placeholder)
├── prompts/                       # 모든 프롬프트 ({{변수}} 치환, 수정 즉시 반영)
│   ├── conversation_system.txt    # 대화 파트너 역할
│   ├── conversation_opening.txt   # 첫 인사·첫 질문
│   ├── feedback_turn.txt          # 턴별 피드백 (의도 추정 + 의미 전달/더 나은 표현, JSON)
│   ├── intervention_decision.txt  # AI Decision 개입 판정 (0–100점 + 보여줄지)
│   └── delayed_summary.txt        # Delayed 종합 피드백 (패턴 + 총평)
├── server/
│   ├── main.py · config.py · auth.py
│   ├── routes/      session.py (로그인·진행·세션) · turn.py (발화·피드백) · tts.py · annotation.py
│   │                survey.py · log.py (브라우저 이벤트) · admin.py (코드·대시보드·로그·CSV) · common.py
│   ├── services/    llm.py · prompt_loader.py · conversation_agent.py · feedback_agent.py
│   │                feedback_jobs.py (백그라운드 피드백) · intervention_policy.py · delayed_summary.py
│   │                dashboard.py (대시보드 집계) · tts_service.py · mock.py
│   └── storage/     codes_store.py · session_store.py · event_logger.py · csv_export.py
├── web/
│   ├── index.html · fonts/ · css/ (base · layout · components)
│   └── js/
│       ├── app.js (화면 전환) · api.js · state.js
│       ├── pages/       login · admin · admin-dashboard · task-intro · mode-select · chat · delayed-summary · annotation · survey · done
│       ├── components/  sidebar · timer · message-bubble · feedback-card · mic-button · mode-toggle · page-footer
│       └── lib/         stt.js · audio-player.js · diff.js (바뀐 부분 강조) · log.js · dom.js · icons.js · toast.js
└── data/  (자동 생성, .gitignore)
    ├── codes.json · admin_events.jsonl · admin_tokens.json
    └── logs/{CODE}/  events.jsonl · state.json · user_session.json · ai_session.json · delayed_session.json
```

---

## 3. 참가자 흐름

```
코드 입력 → [Task 1 → Task 2 → Task 3] → 종료 화면(처음으로)
각 Task: 설명 → 피드백 방식 선택 → 10분 대화 → (Delayed만: 종합 피드백) → 평가(Annotation) → 세션 설문
```

- 좌측 사이드바에 Task 진행과 세부 단계 표시. **다음** 버튼은 본문 우측 하단
- 새로고침·재접속해도 같은 코드로 들어오면 마지막 단계부터 이어짐 (`state.json`, 세션 파일)
- 대화: AI가 먼저 말함(음성 + 왼쪽 말풍선) → 마이크 버튼으로 녹음 시작/종료, 오른쪽에 실시간 전사
  → 보내면 **대화 AI 응답**은 바로, **피드백**은 백그라운드에서 생성 (응답이 피드백을 기다리지 않음)
- 타이머는 경과 시간. 10:00이 넘으면 빨간색 + 안내. **세션 종료**는 항상 노출 (10분 전이면 확인 창)
- 피드백 방식 `간단한 피드백`(고친 문장, 바뀐 부분 강조) / `자세한 피드백`(+ 항목별 이유). 매 턴 두 버전이 모두 있으므로 대화 중 전환하면 이미 나온 피드백도 바뀜

| 조건 (내부 키) | 대화 중 피드백 |
|---|---|
| User Trigger (`user`) | 내 발화 아래 **피드백 보기** 버튼을 누른 발화만 표시. 누른 사실은 턴에 `requested`, `requested_at`, `request_count`로, 실제 표시는 `shown_via: request`로 기록 |
| AI Decision (`ai`) | 아래 개입 판단에서 `show=true`인 발화만 자동 표시 |
| Delayed (`delayed`) | 표시 안 함 → 종료 후 **종합 피드백**(간단/자세한 탭)으로 한 번에 |

### AI Decision 개입 판단 (`intervention_policy.py`, 값은 `settings.json → intervention`)
1. **LLM 판정** (`intervention_decision.txt`): 지금 보여줄 교육적 필요를 **0–100점**으로 매기고, 보여줄지(true/false)도 판단
2. **적응형 보정**: 최근 `window`(3)턴의 노출 비율을 목표 `target_rate`(≈2/3)와 비교해
   문턱값 `T = base_threshold(50) + gain(60) × (비율 − 목표)`를 만든다 (10~90으로 제한)
   - `warmup` 이전 턴이 2개 미만 / `on_target` 목표 근처 → LLM 판단 그대로
   - `too_many` 많이 보여줬음 → LLM이 보여주자고 하고 **점수 ≥ T**일 때만 (예: 3/3 → T=70)
   - `too_few` 적게 보여줬음 → LLM이 보여주자고 하거나 **점수 ≥ T**이면 (예: 1/3 → T=30, 0/3 → T=10)
3. 고칠 부분이 없으면 판정 없이 보여주지 않음 (`no_issue`)

점수, LLM 판단, 문턱값, 구간(zone), 보정 여부(`overridden`)는 모두 세션 파일·이벤트 로그·CSV에 남아요.

### 턴별 피드백 (`feedback_turn.txt` 출력)
```json
{ "intended_meaning": "AI가 추정한 의도(한국어)", "has_issue": true, "severity": 0-3,
  "revised": "고친 전체 문장",
  "items": [{ "type": "meaning | expression", "original": "...", "revised": "...", "explanation": "이유(한국어)" }] }
```
`meaning` = 의미가 제대로 전달되지 않은 부분 교정, `expression` = 의미는 통하지만 더 나은 표현

### Annotation (`annotation.json`)
모든 발화 + AI가 이해한 의도 + 피드백. **본 피드백은 컬러, 만들어졌지만 못 본 피드백은 회색·점선**.
발화마다 피드백 상태를 나누고, 상태에 맞는 질문만 묻는다 (피드백이 없던 발화에는 피드백 내용 질문 없음).

| 조건 | 봤음 (`seen`) | 못 봤음 (`unseen`) | 요청했지만 고칠 부분 없음 | 피드백 없음 |
|---|---|---|---|---|
| User Trigger | 내용 · 의도 · 본 것이 도움 됐나 | 내용 · 의도 · 봤다면 도움 됐을까 | 의도 · 피드백이 있어야 했나 | 의도 · 피드백이 있어야 했나 |
| AI Decision | 내용 · 의도 · 이 시점에 필요했나 | 내용 · 의도 · 대화 중에 보여줬어야 했나 | — | 의도 · 피드백이 있어야 했나 |
| Delayed | 내용 · 의도 · 실시간이었다면 유용했을까 | — | — | 의도 · 피드백이 있어야 했나 |

상태 규칙은 서버 `session_store.feedback_state()`와 화면 `annotation.js`에 똑같이 있어요.

### 세션 설문 (`survey.json`)
각 Task가 끝날 때마다, 진한 색 띠로 다른 단계와 구분된 화면(사이드바에도 '세션 설문' 표시):
리커트 1–5 (학습 도움 · 시점 적절성 · 부담감 · 흐름 방해) + 좋았던 점 / 아쉬운 점 / 그 밖에 하고 싶은 말. 예시 문구는 조건별로 다름.

---

## 4. Admin (`admin` 입력)
- **참가자 코드**: Task 순서(6가지) + Task별 주제 선택 → 6자리 코드 자동 생성(직접 지정도 가능), 메모, 삭제(로그 파일은 남음)
- **대시보드**: 조건 비교 표(세션 시간, 발화 수·길이, 고칠 부분 비율, 대화 중 노출 비율, 요청·개입 비율 등), 세션 설문 평균(조건별 점 그래프, 마우스를 올리면 점수 분포), Annotation 선택 비율(조건 × 피드백 상태 × 질문), AI Decision 개입 판단 요약. '완료한 참가자만' 필터, 요약 CSV
- **로그**: 참가자별 통계, Task별 대화·피드백(요청 여부·노출 여부·개입 점수/문턱/보정·Annotation 응답)·설문, 이벤트 타임라인. 코드를 지운 참가자도 `data/logs`에 기록이 있으면 목록에 나옴
- **CSV**: 참가자별 `turns`(대화·피드백) / `events` / `annotations` / `survey`, Task별 CSV, 참가자 전체 ZIP(원본 JSON 포함), 전체 참가자 통합 CSV. 엑셀용 UTF-8 BOM

### 기록 보존 · 다시 불러오기
- 모든 기록은 `data/` 폴더 파일에 바로 저장되고, 화면은 요청할 때마다 이 파일을 다시 읽어요. 서버를 껐다 켜도, 브라우저 세션이 초기화돼도 그대로 보여요
- 참가자는 같은 코드로 다시 들어오면 마지막 단계부터 이어서 진행 (대화 중이었다면 대화 기록과 타이머도 복원)
- 서버가 꺼지는 바람에 만들지 못한 피드백은, 그 발화를 요청하거나 세션을 종료할 때 파일의 대화 기록으로 다시 만들어요
- 관리자 로그인 토큰도 `data/admin_tokens.json`에 저장돼 서버를 다시 켜도 유지돼요 (14일 뒤 만료). `admin` 코드는 `settings.json`에서 바꿀 수 있어요
- 다른 PC로 옮기거나 백업하려면 `data/` 폴더를 통째로 복사하면 돼요

---

## 5. 로그 (`data/logs/{CODE}/events.jsonl`)
한 줄 = 한 이벤트: `ts`(서버 시각, ms), `client_ts`(브라우저 시각), `code`, `task`, `source`(server/client), `event`, `data`

| 구분 | event |
|---|---|
| 진행 | `login` `step_enter` `session_start` `session_resume` `session_end` `page_visibility` `restart_click` |
| 대화 | `ai_utterance` `user_utterance` `tts_start` `tts_end` `tts_replay` `mic_start` `mic_stop` `stt_error` `ai_error` |
| 피드백 | `mode_select` `mode_toggle` `feedback_generated`(전체 JSON·지연 ms) `feedback_error` `feedback_regenerate` `feedback_request_click` `feedback_requested` `intervention_decision`(점수·문턱·구간·보정) `feedback_shown` `feedback_displayed` |
| 종료 후 | `timer_expired` `session_end_click` `delayed_summary_generated` `delayed_summary_view` `delayed_tab_switch` `annotation_view` `annotation_click` `annotation_saved` `survey_view` `survey_submit` |

세션 파일(`{task}_session.json`)에는 턴마다 피드백 원문, 요청 여부(`requested`, `requested_at`, `request_count`), 노출 여부(`shown`, `shown_via`: request/ai/summary, `shown_at`, `mode_when_shown`), 개입 결정, Annotation, 설문이 함께 저장돼요.

---

## 6. 남은 일 · 참고
- 대화 주제 목록(`topics.json`)과 설문 문항(`survey.json`) 확정
- 실제 키로 파일럿 → 피드백 품질, 개입 빈도(2/3 목표), 한 턴 길이 확인 후 프롬프트·`intervention` 값 조정
- 모델 이름은 `.env`에서 변경 (지원하지 않는 `temperature`는 자동으로 빼고 재시도)
- Pretendard 글꼴: SIL Open Font License (`web/fonts/Pretendard-LICENSE.txt`)
