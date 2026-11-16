# AI 활용 외국어 말하기 학습에서 교정적 피드백의 제시 방식 연구 — 실험 시스템

교정적 피드백 **제시 방식**(User Trigger / AI Decision / Delayed)을 비교하는 Formative Study용 웹 시스템.

- 서버: FastAPI (Python 3.11+) · 화면: Vanilla JS (ES modules) · 글꼴: Pretendard
- **대화 상대 AI: Gemini 3.8 Live** (`gemini-3.8-live`, Live API) — 음성으로 답하고, 글자는 받아쓰기로 받음
- **피드백 · 점수 · Delayed 종합: GPT-5.5** (`gpt-5.5`, OpenAI Responses API) — 조건마다 프롬프트가 따로 있음
- AI 음성: Gemini Live가 만든 음성을 그대로 재생 (실패하면 브라우저 내장 음성)
- 참가자 발화: **녹음 파일로 저장** + 전사는 `.env`에서 선택 — 브라우저 내장 음성 인식(기본, **Chrome 필수**, 선택적으로 gpt-4o-mini로 오인식 다듬기) 또는 **Whisper**
- 로그: 로컬 `data/` 폴더 (JSONL + JSON + AI 음성 wav + 참가자 녹음), Admin 화면에서 CSV/ZIP 내려받기

---

## 1. 실행

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                   # GEMINI_API_KEY, OPENAI_API_KEY 입력
python run.py                                          # → http://127.0.0.1:8000
```

`.env` 주요 값

| 값 | 기본 | 설명 |
|---|---|---|
| `GEMINI_API_KEY` | — | Google AI Studio 키. 없으면 **대화 AI만** MOCK |
| `CHAT_MODEL` | `gemini-3.8-live` | 대화 상대 AI (Live API 모델) |
| `AI_VOICE` | `live` | `live` = Gemini 음성 재생 / `browser` = 브라우저 내장 음성만 |
| `LIVE_VOICE` | (비움) | Gemini 음성 이름. 비우면 기본 음성 |
| `OPENAI_API_KEY` | — | OpenAI 키. 없으면 **피드백만** MOCK |
| `FEEDBACK_MODEL` | `gpt-5.5` | 피드백·채점·요약 모델 |
| `FEEDBACK_REASONING_EFFORT` | `low` | `none`~`xhigh`. 높을수록 정확하지만 느리고 비쌈 |
| `STT_ENGINE` | `browser` | `browser` = 브라우저 내장 음성 인식 / `whisper` = 녹음 파일을 OpenAI Whisper로 전사 (말하는 동안 브라우저 인식은 미리보기로만) |
| `WHISPER_MODEL` | `whisper-1` | `STT_ENGINE=whisper`일 때 모델 |
| `STT_CLEANUP` | `0` | `browser`일 때 `1`이면 음성 인식이 **잘못 받아 적은 단어만** 다듬어 그 글자로 화면 표시·저장·피드백 (학습자 오류는 그대로, 원문은 `stt_raw`로 저장) |
| `STT_CLEANUP_MODEL` | `gpt-4o-mini` | 다듬기 모델 |
| `MOCK_LLM` | `0` | `1`이면 키가 있어도 둘 다 가짜 응답 |

- 터미널과 화면(로그인 화면 아래, 관리자 화면 위)에 **API 키 연결 상태**와 전사 방식이 보여요. 관리자 화면의 **연결 확인** 버튼은 대화 AI·피드백·전사(Whisper 또는 다듬기를 쓸 때) API에 아주 짧게 실제 호출을 보내 정상인지 확인해요 (키 값은 화면에 나오지 않음)
- `.env`를 바꾸면 서버를 다시 켜야 적용돼요. `config/*.json`·`prompts/*.txt`는 바로 적용
- 코드 입력란에 `admin` → 관리자 화면 (참가자 코드 생성 → 참가자는 그 코드로 입장)
- 주소 뒤 옵션: `?test=true` 테스트 모드(발화 아래 L1·L2 점수 표시, `?test=false`로 끔) · `?typing=1` 직접 입력칸
- 다른 PC에서 접속하려면 `.env`의 `HOST=0.0.0.0`. 단, 마이크는 `localhost` 또는 HTTPS에서만 허용됨

---

## 2. 파일 구조

```
feedback-timing-study/
├── run.py · requirements.txt · .env.example
├── config/                        # 코드 수정 없이 바꾸는 값 (매 요청마다 다시 읽음)
│   ├── settings.json              # 연구명, admin 코드, 세션 시간, 권장 발화 길이(20–40초), 피드백 맥락 턴 수(8), 응답 지연, 테스트 모드 허용
│   ├── topics.json                # 대화 주제 8개 (Admin 드롭다운) — label: 화면 표시, hint: AI용 설명, legacy_topics: 예전 주제 이름
│   ├── tasks.json                 # 세 조건 이름·설명 문구, Task 안내 규칙
│   ├── annotation.json            # Annotation 질문과 조건별 적용 규칙
│   └── survey.json                # 세션 설문 문항, 자유 응답 예시(placeholder)
├── prompts/                       # 모든 프롬프트 ({{변수}} 치환, 수정 즉시 반영)
│   ├── conversation_system.txt    # 대화 상대 AI의 응답 구성 (Gemini Live 시스템 지시)
│   ├── conversation_opening.txt   # 첫 인사·첫 질문
│   ├── feedback_user_trigger.txt  # ★ User Trigger: 요청 시 생성 (학습자가 궁금했을 점 추론)
│   ├── feedback_ai_decision.txt   # ★ AI Decision: 지금 꼭 필요한지 판단 + 근거(rationale)
│   ├── feedback_delayed_turn.txt  # ★ Delayed: 발화별 피드백 필요 여부 판단
│   ├── feedback_delayed_summary.txt # ★ Delayed: 종료 후 종합 피드백 (패턴 + 규칙 단서 + 총평)
│   ├── PROMPT_DESIGN.md           # 프롬프트 구성 논리와 참고 문헌 (조건별)
│   ├── stt_cleanup.txt            # 브라우저 전사의 오인식 다듬기 (STT_CLEANUP=1)
│   └── stt_whisper_prompt.txt     # Whisper에 주는 말투 예시 (오류·필러를 고치지 않고 받아 적도록)
├── tools/
│   ├── score_csv.py               # ★ CSV 발화 일괄 채점 (같은 로직)
│   └── learner_sentence.example.csv
├── server/
│   ├── main.py · config.py · auth.py
│   ├── routes/      session.py (로그인·진행·세션·AI 음성) · turn.py (발화·녹음·전사·피드백·테스트 점수) · annotation.py
│   │                survey.py · log.py (브라우저 이벤트) · admin.py (코드·대시보드·로그·CSV·연결 확인) · common.py
│   ├── services/    gemini_live.py (Live API) · conversation_agent.py · llm.py (OpenAI) · feedback_agent.py (조건별 프롬프트·정리)
│   │                feedback_jobs.py (백그라운드 피드백) · intervention_policy.py · delayed_summary.py · transcription.py (Whisper·다듬기)
│   │                dashboard.py · prompt_loader.py · mock.py
│   └── storage/     codes_store.py · session_store.py · event_logger.py · csv_export.py · audio_store.py · recording_store.py
├── web/
│   ├── index.html · fonts/ · css/ (base · layout · components)
│   └── js/
│       ├── app.js (화면 전환) · api.js · state.js
│       ├── pages/       login · admin · admin-dashboard · task-intro · mode-select · chat · delayed-summary · annotation · survey · done
│       ├── components/  sidebar · timer · message-bubble · feedback-card · mic-button · mode-toggle · page-footer · api-status
│       └── lib/         stt.js · recorder.js (녹음) · audio-player.js · diff.js (바뀐 부분 강조) · log.js · dom.js · icons.js · toast.js
└── data/  (자동 생성, .gitignore)
    ├── codes.json · admin_events.jsonl · admin_tokens.json
    ├── logs/{CODE}/   events.jsonl · state.json · user_session.json · ai_session.json · delayed_session.json
    ├── audio/{CODE}/  {task}_{turn}.wav  (Gemini Live가 만든 AI 발화 음성)
    └── recordings/{CODE}/  {CODE}_{User_Trigger|AI_Decision|Delayed}_{001}.webm  (참가자 녹음, 번호 = Task 안에서 말한 순서)
                       discarded/  (전사가 비어 발화가 되지 못한 녹음)
```

---

## 3. 대화 상대 AI (Gemini 3.8 Live)

응답 구성 (`conversation_system.txt`)
1. **길이**: 발화 한 번에 1~3문장, 45단어 이하
2. **반응과 질문**: 학습자 말에 짧게 반응한 뒤 개방형 질문 하나 (Yes/No 질문 피함)
3. **수준**: CEFR B1~B2 수준의 구어체 영어
4. **교정 금지**: 학습자의 오류를 지적하지도, 고친 형태로 되받아 말하지도(recast) 않음

동작 (`gemini_live.py`): 발화마다 짧은 Live 세션을 열어 지금까지의 대화 전체를 보내고(`send_client_content`), 음성 + 받아쓰기 글자로 답 하나를 받은 뒤 닫아요. 대화 기록은 우리 세션 파일에 있으므로 서버를 다시 켜도 이어져요. 음성은 `data/audio`에 wav로 저장돼 재생·기록에 쓰여요.

---

## 4. 피드백 로직 (GPT-5.5, `prompts/feedback_*.txt` + `feedback_agent.py`)

구성 논리와 참고 문헌은 `prompts/PROMPT_DESIGN.md`에 정리돼 있어요.

**피드백 대상 (세 조건 공통)** — ① 의미 전달을 막거나 왜곡하는 오류 ② 이해는 되지만 원어민이라면 더 자연스럽게 말할 표현. 어휘·문법·화용만 다루고 발음·유창성·내용, 음성 인식의 문장부호·필러·오인식은 제외해요.

**피드백 형식** — 간단한 피드백 = 발화 전체를 최소한으로 고친 문장(재구성·명시적 교정, 바뀐 부분 노란색). 자세한 피드백 = 그 위에 바뀐 곳마다 규칙·이유를 한국어로 설명(메타언어적 단서). Delayed 종합 피드백도 메타언어적 단서(반복 패턴 + 규칙 한 문장 + 총평).

**피드백을 줄지**는 AI Decision·Delayed는 피드백 AI의 `needs_feedback` 판단으로, User Trigger는 (이미 요청했으므로) 고친 부분이 있는지로 정해요 (없으면 "고칠 부분이 없어요"). **점수**(L1 의미 미전달 · L2 부자연스러움 · 시급성, 1–10, **높을수록 피드백이 필요한 쪽**)는 발화마다 기록만 하고 결정에는 쓰지 않아요. 피드백 AI에게는 그 발화 앞의 최근 8턴(`context_turns`)을 함께 줘요.

| 조건 | 언제 만드나 | 프롬프트 | 대화 중 표시 |
|---|---|---|---|
| User Trigger (`user`) | **피드백 보기를 누른 순간** (대화는 그동안에도 이어짐). 요청하지 않은 발화는 세션 종료 때 같은 프롬프트로 만들어 Annotation에서만 회색으로 | `feedback_user_trigger.txt` — 학습자가 무엇이 궁금했을지 먼저 추론(`likely_concern`) | 누른 발화에만. 고칠 게 없으면 "이 말에는 고칠 부분이 없어요". 누른 사실은 `requested`, `requested_at`, `request_count`. 내 말이 화면에 나온 뒤 **최소 2초** 지나야 대화 상대가 말함 |
| AI Decision (`ai`) | 매 발화 직후 | `feedback_ai_decision.txt` — 대화를 끊을 만큼 **지금 꼭 필요한지** 판단, 필요한 만큼만 교정, 판단 근거 `rationale` | 필요할 때만 자동 표시. **피드백이 먼저 나오고 1초 뒤 대화 상대가 말함** (기다리는 동안 하단에 작게 "피드백 생성 중…"). 근거는 Annotation에서 보여준/안 보여준 발화 모두에 표시 |
| Delayed (`delayed`) | 매 발화 직후 (뒤에서) | `feedback_delayed_turn.txt` + 종료 후 `feedback_delayed_summary.txt` | 표시 안 함 → 종료 후 **종합 피드백을 맨 위에**, 피드백이 있었던 발화를 아래에 나열 (고칠 게 없던 발화는 제외) |

**대화 응답 분리** — `POST /api/turn`은 내 발화를 저장하고 바로 돌려주고, 대화 상대의 답은 그 순간부터 뒤에서 만들어 `POST /api/turn/reply`로 받아요. 그래서 User Trigger에서 답을 기다리는 동안에도 피드백을 요청할 수 있어요.

**CSV 일괄 처리** (`tools/score_csv.py`) — 실험과 같은 프롬프트로 CSV의 발화를 처리해 오른쪽 열에 붙여요.
```bash
python tools/score_csv.py learner_sentence.csv                       # User Trigger 프롬프트 (기본)
python tools/score_csv.py learner_sentence.csv --condition ai --column 발화 --topic 여행
```
추가 열: `l1_meaning_breakdown` `l2_unnaturalness` `urgency` · `needs_feedback`(Y/N) · `simple_feedback` `detailed_feedback`(필요할 때만) · `intended_ko` · `rationale`(ai) · `likely_concern`(user) · `error`. 결과 파일은 `입력파일명_scored_{condition}.csv`.

---

## 5. 참가자 흐름

```
코드 입력 → [Task 1 → Task 2 → Task 3] → 종료 화면(처음으로)
코드를 입력하면 **연구 소개** 화면이 가장 먼저 나와요 (첫 세션을 시작하기 전까지는 다시 들어와도 여기부터) (전체 진행: 사전 인터뷰 → 튜토리얼 → Session 1~3 → 사후 인터뷰, 세션 흐름: 설명 1분 → 대화 9분 → 피드백 Annotation 3분 → 설문 2분, 실제 화면 사진은 `web/img/overview/`, 누르면 크게 보기).

각 Task: 설명 → 피드백 방식 선택 → 9분 대화 → (Delayed만: 종합 피드백) → 평가(Annotation) → 세션 설문
```

- 좌측 사이드바에 Task 진행과 세부 단계, 아래쪽에 **나가기**(확인 후 코드 입력 화면으로). **다음** 버튼은 본문 우측 하단
- **새로고침하면 코드 입력 화면**이 나오고 코드가 미리 채워져 있어요. **이어서 하기**를 누르면 서버에 저장된 마지막 단계부터 이어져요 (다른 PC에서 같은 코드로 들어와도 동일). 대화 중 나갔다 와도 타이머는 세션 시작 시각 기준으로 계속 흘러요
- 대화: AI가 먼저 말함(음성 + 왼쪽 말풍선) → 마이크 버튼을 누른 순간부터 다시 누른 순간까지 **녹음**, 오른쪽에 실시간 전사 → 전사(옵션: 다듬기/Whisper) 뒤 내 말풍선이 먼저 나오고, 대화 상대의 답과 피드백은 조건별 순서로
- 첫 Task 설명 화면의 세 방식 상자는 그 참가자에게 배정된 진행 순서대로 나와요. 권장 발화 길이는 한 번에 20–40초
- 내 말풍선의 **듣기** 버튼으로 녹음을 다시 들을 수 있어요 (대화 화면 · Annotation · 관리자 화면)
- 타이머는 경과 시간. 9:00이 넘으면 빨간색 + 안내. **세션 종료**는 항상 노출
- 간단한/자세한 피드백은 대화 중 언제든 전환 (이미 나온 피드백도 바뀜)

### Annotation (`annotation.json`)
모든 발화(녹음 **듣기** 버튼) + AI가 이해한 의도 + 피드백. **본 피드백은 컬러, 못 본 피드백은 회색·점선**. AI Decision은 **AI가 피드백을 보여준 / 보여주지 않은 이유**도 함께 보여줘요. 상태에 맞는 질문만 물어요.

| 조건 | 봤음 | 못 봤음 | 요청했지만 피드백 없음 | 피드백 없음 |
|---|---|---|---|---|
| User Trigger | 의도 · 내용 · 본 것이 도움 됐나 | (요청하지 않은 발화, 세션 후 생성) 의도 · 내용 · 봤다면 도움 됐을까 | 의도 · 피드백이 있어야 했나 | 의도 · 피드백이 있어야 했나 |
| AI Decision | 의도 · 내용 · 이 시점에 필요했나 | (세션 종료 뒤 늦게 생성된 경우만) | — | 의도 · 피드백이 있어야 했나 |
| Delayed | 의도 · 내용 · 실시간이었다면 유용했을까 | — | — | 의도 · 피드백이 있어야 했나 |

### 세션 설문 (`survey.json`)
각 Task가 끝날 때마다(진한 색 띠로 구분): 리커트 1–5 (학습 도움 · 시점 적절성 · 부담감 · 흐름 방해) + 좋았던 점 / 아쉬운 점 / 그 밖에 하고 싶은 말.

---

## 6. Admin (`admin` 입력)
- **API 상태 줄**: 대화 AI·피드백 모델과 키 연결 여부, AI 음성 방식, **연결 확인**(실제 호출 테스트)
- **참가자 코드**: Task 순서(6가지) + Task별 주제 → 6자리 코드 생성, 메모, 삭제(로그 파일은 남음)
- **대시보드**: 조건 비교 표(세션 시간, 발화 수·길이, 피드백 필요 판단 비율, 평균 L1·L2·시급성, 생성 시간, 노출·요청 비율, 방식 전환 간단→자세한 / 자세한→간단, 요청하기까지 걸린 시간), 세션 설문 평균, **발화별 점수 분포**(전체 + 조건별 묶음: User Trigger 누름/안 누름 · AI Decision 제시/미제시 · Delayed 전체), **AI Decision 판단과 학습자 판단 일치표**, Annotation 선택 비율(의도 → 내용 → 시점 순). '완료한 참가자만' 필터, 요약 CSV
- **로그**: Task별 대화 · 피드백 · 점수 막대(L1·L2·시급성) · 필요 판단과 근거(AI Decision) · 추정한 궁금증(User Trigger) · 생성 시점 · 요청/노출 여부 · Annotation 응답(질문 순서대로) · 전사 원문과 녹음(카드 아래 작게) · 설문. 오른쪽에 **이 참가자의 발화별 점수 분포**와 이벤트 타임라인
- **CSV**: 참가자별 `turns`(대화·피드백·점수·판단 근거·전사 방식·녹음 파일 이름) / `events` / `annotations` / `survey`, Task별, 참가자 ZIP(녹음 파일 포함), 전체 참가자 통합. 엑셀용 UTF-8 BOM

**기록 보존**: 모든 기록은 `data/` 파일에 바로 저장되고, 화면은 요청마다 파일을 다시 읽어요. 서버를 껐다 켜도 그대로 보이고, 만들지 못한 피드백은 요청하거나 세션을 종료할 때 다시 만들어요. 관리자 로그인도 `data/admin_tokens.json`에 저장돼 유지돼요(14일). 백업은 `data/` 폴더 통째로.

---

## 7. 로그 (`data/logs/{CODE}/events.jsonl`)
한 줄 = 한 이벤트: `ts`(서버 시각, ms), `client_ts`(브라우저 시각), `code`, `task`, `source`(server/client), `event`, `data`

| 구분 | event |
|---|---|
| 진행 | `login` `step_enter` `session_start`(사용 모델 기록) `session_resume` `session_end` `page_visibility` `restart_click` `exit_click` |
| 대화 | `ai_utterance`(음성 파일·길이) `user_utterance`(전사 방식·원문·다듬은 단어·녹음 파일) `utterance_empty` `tts_start` `tts_end`(live/browser) `tts_replay` `mic_start` `mic_stop` `recording_play` `recording_error` `stt_error` `ai_error` |
| 피드백 | `mode_select` `mode_toggle` `feedback_generated`(생성 시점 purpose, 필요 판단, L1·L2·시급성, 전체 JSON, 지연 ms) `feedback_error` `feedback_regenerate` `feedback_request_click` `feedback_requested` `intervention_decision` `feedback_shown` `feedback_displayed` |
| 종료 후 | `timer_expired` `session_end_click` `delayed_summary_generated` `delayed_summary_view` `delayed_tab_switch` `annotation_view` `annotation_click` `annotation_saved` `survey_view` `survey_submit` |

---

## 8. 남은 일 · 참고
- 실제 키로 파일럿: Gemini Live 응답 속도·음성, GPT-5.5 채점 품질과 지연(`FEEDBACK_REASONING_EFFORT`) 확인
- 실제 키로 조건별 프롬프트 출력 검토 (`tools/score_csv.py --condition user|ai|delayed`로 같은 발화를 비교)
- 설문 문항(`survey.json`) 확정
- 녹음은 브라우저 기본 형식(Chrome: webm/Opus)으로 저장돼요. wav가 필요하면 `ffmpeg -i in.webm out.wav`로 변환
- Pretendard 글꼴: SIL Open Font License (`web/fonts/Pretendard-LICENSE.txt`)
