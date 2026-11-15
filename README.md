# AI 활용 외국어 말하기 학습에서 교정적 피드백의 시점 연구 — 실험 시스템

교정적 피드백 **제시 시점**(User Trigger / AI Decision / Delayed)을 비교하는 Formative Study용 웹 시스템.

- 서버: FastAPI (Python 3.11+) · 화면: Vanilla JS (ES modules) · 글꼴: Pretendard
- **대화 상대 AI: Gemini 3.8 Live** (`gemini-3.8-live`, Live API) — 음성으로 답하고, 글자는 받아쓰기로 받음
- **피드백 · 점수 · Delayed 요약: GPT-5.5** (`gpt-5.5`, OpenAI Responses API)
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
│   ├── settings.json              # 연구명, admin 코드, 세션 시간, 권장 발화 길이, ★ 피드백 기준값 N, 응답 지연, 테스트 모드 허용
│   ├── topics.json                # 대화 주제 8개 (Admin 드롭다운) — label: 화면 표시, hint: AI용 설명, legacy_topics: 예전 주제 이름
│   ├── tasks.json                 # 세 조건 이름·설명 문구, Task 안내 규칙
│   ├── annotation.json            # Annotation 질문과 조건별 적용 규칙
│   └── survey.json                # 세션 설문 문항, 자유 응답 예시(placeholder)
├── prompts/                       # 모든 프롬프트 ({{변수}} 치환, 수정 즉시 반영)
│   ├── conversation_system.txt    # 대화 상대 AI의 응답 구성 (Gemini Live 시스템 지시)
│   ├── conversation_opening.txt   # 첫 인사·첫 질문
│   ├── feedback_turn.txt          # ★ 문장 분리 + L1·L2 채점 + 고친 문장/이유 (GPT-5.5, JSON)
│   ├── delayed_summary.txt        # Delayed 종합 피드백 (패턴 + 총평)
│   ├── stt_cleanup.txt            # 브라우저 전사의 오인식 다듬기 (STT_CLEANUP=1)
│   └── stt_whisper_prompt.txt     # Whisper에 주는 말투 예시 (오류·필러를 고치지 않고 받아 적도록)
├── tools/
│   ├── score_csv.py               # ★ CSV 발화 일괄 채점 (같은 로직)
│   └── learner_sentence.example.csv
├── server/
│   ├── main.py · config.py · auth.py
│   ├── routes/      session.py (로그인·진행·세션·AI 음성) · turn.py (발화·녹음·전사·피드백·테스트 점수) · annotation.py
│   │                survey.py · log.py (브라우저 이벤트) · admin.py (코드·대시보드·로그·CSV·연결 확인) · common.py
│   ├── services/    gemini_live.py (Live API) · conversation_agent.py · llm.py (OpenAI) · feedback_agent.py (채점·기준값)
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

## 4. 피드백 로직 (GPT-5.5, `feedback_turn.txt` + `feedback_agent.py`)

**대상**: 어휘(표현)·문법·화용만. 발음·내용·유창성은 다루지 않아요. 음성 인식의 문장부호·대소문자·필러는 오류로 보지 않아요.

**채점** — 발화를 문장으로 나누고, 문장마다 두 기준을 1~10점으로:

| 기준 | 판단 방법 | 점수 기준 (요약) |
|---|---|---|
| **L1 의미 전달 영향** | ① 청자 직역(오류를 고치지 않고, 이해 불가면 "이해 불가") + 확인 질문 2개(다른 해석이 정말 가능? 멈추고 다시 생각해야 이해?) ② 화자 의도 번역(맥락 반영) ③ 비교 → 점수 (가장 심각한 문제 하나 기준, 작은 문제를 합쳐 올리지 않음) | 1–2 뜻이 온전히 전달(작은 실수 포함) · 3–4 오류가 보이지만 바로 이해 · 5–6 멈추거나 추측해야 이해 · 7–8 해석이 실제로 둘 이상 · 9–10 다른 의미/복원 불가 |
| **L2 표현의 자연스러움** | ① 최소 수정본(구어 기준 문법적) ② 자연스러움 수정본(원어민처럼, 의미 보존) ③ 비교 → 점수 (쉬운·평이한 표현은 감점 안 함) | 1–2 그대로 괜찮음 · 3–4 대화에서 무난(더 자연스러운 대안·작은 실수) · 5–6 분명히 비원어민스러운 표현 · 7–8 확연히 어색 · 9–10 화용적으로 부적절 |

점수는 엄격한 시험관이 아니라 대화 상대 입장에서 매기고, 중급 학습자의 문장은 대부분 1~4점에 오도록, 두 구간 사이에서 애매하면 **낮은 쪽**을 고르도록 안내해요.

**제시 기준 N** (`config/settings.json → feedback_threshold`, 기본 L1 5 · L2 5): 문장의 **L1 ≥ N 또는 L2 ≥ N**이고 실제로 고친 부분이 있으면 그 문장은 피드백 대상이에요. 발화에 피드백 대상 문장이 하나라도 있으면 그 발화는 "피드백 있음"이에요. 기준값은 서버를 다시 켜지 않아도 다음 발화부터 적용되고, 발화마다 그때 쓴 기준값이 함께 저장돼요.

**피드백 형태** (원문은 최소한으로 바꾸고 학습자의 의미·말투·수준 유지)
- 간단한 피드백: 발화 전체에서 피드백 대상 문장만 고친 문장 (바뀐 부분은 노란색 강조)
- 자세한 피드백: 간단한 피드백 + 바뀐 부분마다 유형(의미 전달/더 나은 표현 · 어휘/문법/화용)과 한국어 이유

점수와 상관없이 모든 문장을 고친 결과(`revised_all`, `items_all`)와 문장별 채점 근거(직역·의도·최소/자연 수정본)도 함께 저장돼요.

**세 조건 모두 같은 로직으로 미리 만들어 두고, 보여주는 시점만 달라요**

| 조건 (내부 키) | 대화 중 피드백 |
|---|---|
| User Trigger (`user`) | 내 발화 아래 **피드백 보기**를 누르면 표시. 기준 미만이면 "이 말에는 피드백이 없어요". 누른 사실은 `requested`, `requested_at`, `request_count`로 기록. 대화 상대는 응답이 준비된 뒤 **2.5초 더 기다렸다가** 말해요 (피드백 보기를 누를 여유) |
| AI Decision (`ai`) | 기준 이상인 발화만 자동 표시 (노출 비율 보정 없음). **피드백이 먼저 나오고 1초 뒤 대화 상대가 말해요**. 기다리는 동안 대화 아래에 작게 "피드백 생성 중…". 60초 안에 피드백이 안 나오면 대화를 먼저 이어가고 피드백은 나오는 대로 표시 |
| Delayed (`delayed`) | 표시 안 함 → 종료 후 기준 이상 발화만 **종합 피드백**(간단/자세한 탭)으로 한 번에 |

**CSV 일괄 채점** (`tools/score_csv.py`) — 같은 프롬프트·기준으로 CSV의 발화를 채점해 오른쪽 열에 붙여요.
```bash
python tools/score_csv.py learner_sentence.csv               # → learner_sentence_scored.csv
python tools/score_csv.py learner_sentence.csv --column 발화 --topic 여행 --concurrency 4
```
추가 열: `l1_score` `l2_score`(문장 중 최고점) · `feedback_shown`(기준 이상 Y/N) · `l1_scores` `l2_scores`(문장별) · `simple_feedback` `detailed_feedback`(점수와 상관없이) · `intended_ko` `literal_ko` · `sentences_json` · `error`. 발화 열은 `sentence/utterance/text/발화/문장` 중 있는 것, 없으면 첫 열을 써요.

---

## 5. 참가자 흐름

```
코드 입력 → [Task 1 → Task 2 → Task 3] → 종료 화면(처음으로)
각 Task: 설명 → 피드백 방식 선택 → 10분 대화 → (Delayed만: 종합 피드백) → 평가(Annotation) → 세션 설문
```

- 좌측 사이드바에 Task 진행과 세부 단계, 아래쪽에 **나가기**(확인 후 코드 입력 화면으로). **다음** 버튼은 본문 우측 하단
- **새로고침하면 코드 입력 화면**이 나오고 코드가 미리 채워져 있어요. **이어서 하기**를 누르면 서버에 저장된 마지막 단계부터 이어져요 (다른 PC에서 같은 코드로 들어와도 동일). 대화 중 나갔다 와도 타이머는 세션 시작 시각 기준으로 계속 흘러요
- 대화: AI가 먼저 말함(음성 + 왼쪽 말풍선) → 마이크 버튼을 누른 순간부터 다시 누른 순간까지 **녹음**, 오른쪽에 실시간 전사 → 전사(옵션: 다듬기/Whisper) 뒤 대화 AI 응답과 피드백 생성
- 내 말풍선의 **듣기** 버튼으로 녹음을 다시 들을 수 있어요 (대화 화면 · Annotation · 관리자 화면)
- 타이머는 경과 시간. 10:00이 넘으면 빨간색 + 안내. **세션 종료**는 항상 노출
- 간단한/자세한 피드백은 대화 중 언제든 전환 (이미 나온 피드백도 바뀜)

### Annotation (`annotation.json`)
모든 발화(녹음 **듣기** 버튼) + AI가 이해한 의도 + 피드백. **본 피드백은 컬러, 만들어졌지만 못 본 피드백은 회색·점선**. 상태에 맞는 질문만 물어요.

| 조건 | 봤음 | 못 봤음 | 요청했지만 피드백 없음 | 피드백 없음 |
|---|---|---|---|---|
| User Trigger | 내용 · 의도 · 본 것이 도움 됐나 | 내용 · 의도 · 봤다면 도움 됐을까 | 의도 · 피드백이 있어야 했나 | 의도 · 피드백이 있어야 했나 |
| AI Decision | 내용 · 의도 · 이 시점에 필요했나 | (세션 종료 뒤 늦게 생성된 경우만) | — | 의도 · 피드백이 있어야 했나 |
| Delayed | 내용 · 의도 · 실시간이었다면 유용했을까 | — | — | 의도 · 피드백이 있어야 했나 |

### 세션 설문 (`survey.json`)
각 Task가 끝날 때마다(진한 색 띠로 구분): 리커트 1–5 (학습 도움 · 시점 적절성 · 부담감 · 흐름 방해) + 좋았던 점 / 아쉬운 점 / 그 밖에 하고 싶은 말.

---

## 6. Admin (`admin` 입력)
- **API 상태 줄**: 대화 AI·피드백 모델과 키 연결 여부, AI 음성 방식, **연결 확인**(실제 호출 테스트)
- **참가자 코드**: Task 순서(6가지) + Task별 주제 → 6자리 코드 생성, 메모, 삭제(로그 파일은 남음)
- **대시보드**: 조건 비교 표(세션 시간, 발화 수·길이, 피드백 대상 비율, 평균 L1·L2, 노출·요청 비율), 세션 설문 평균, **문장별 L1·L2 점수 분포**(기준 N 표시), Annotation 선택 비율. '완료한 참가자만' 필터, 요약 CSV
- **로그**: Task별 대화·**참가자 녹음 재생**·전사 원문(다듬기 전/Whisper 미리보기)·피드백·**문장별 점수와 채점 근거**·요청/노출 여부·Annotation 응답·설문, 이벤트 타임라인
- **CSV**: 참가자별 `turns`(대화·피드백·전사 방식·녹음 파일 이름) / `sentences`(문장별 점수·근거 — 기준값 N 검토용) / `events` / `annotations` / `survey`, Task별, 참가자 ZIP(녹음 파일 포함), 전체 참가자 통합. 엑셀용 UTF-8 BOM

**기록 보존**: 모든 기록은 `data/` 파일에 바로 저장되고, 화면은 요청마다 파일을 다시 읽어요. 서버를 껐다 켜도 그대로 보이고, 만들지 못한 피드백은 요청하거나 세션을 종료할 때 다시 만들어요. 관리자 로그인도 `data/admin_tokens.json`에 저장돼 유지돼요(14일). 백업은 `data/` 폴더 통째로.

---

## 7. 로그 (`data/logs/{CODE}/events.jsonl`)
한 줄 = 한 이벤트: `ts`(서버 시각, ms), `client_ts`(브라우저 시각), `code`, `task`, `source`(server/client), `event`, `data`

| 구분 | event |
|---|---|
| 진행 | `login` `step_enter` `session_start`(사용 모델 기록) `session_resume` `session_end` `page_visibility` `restart_click` `exit_click` |
| 대화 | `ai_utterance`(음성 파일·길이) `user_utterance`(전사 방식·원문·다듬은 단어·녹음 파일) `utterance_empty` `tts_start` `tts_end`(live/browser) `tts_replay` `mic_start` `mic_stop` `recording_play` `recording_error` `stt_error` `ai_error` |
| 피드백 | `mode_select` `mode_toggle` `feedback_generated`(문장별 L1·L2 점수, 기준값, 전체 JSON, 지연 ms) `feedback_error` `feedback_regenerate` `feedback_request_click` `feedback_requested` `intervention_decision` `feedback_shown` `feedback_displayed` |
| 종료 후 | `timer_expired` `session_end_click` `delayed_summary_generated` `delayed_summary_view` `delayed_tab_switch` `annotation_view` `annotation_click` `annotation_saved` `survey_view` `survey_submit` |

---

## 8. 남은 일 · 참고
- 실제 키로 파일럿: Gemini Live 응답 속도·음성, GPT-5.5 채점 품질과 지연(`FEEDBACK_REASONING_EFFORT`) 확인
- 발화–점수 쌍을 검토해 기준값 N 합의 (`sentences` CSV, 대시보드 점수 분포, `tools/score_csv.py`)
- 설문 문항(`survey.json`) 확정
- 녹음은 브라우저 기본 형식(Chrome: webm/Opus)으로 저장돼요. wav가 필요하면 `ffmpeg -i in.webm out.wav`로 변환
- Pretendard 글꼴: SIL Open Font License (`web/fonts/Pretendard-LICENSE.txt`)
