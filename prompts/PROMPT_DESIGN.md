# 피드백 프롬프트 구성 논리

세 조건은 **같은 피드백 대상·형식**을 쓰고, **언제 만들고 누가 필요성을 판단하느냐**만 다르다.
프롬프트에는 연구 이름을 쓰지 않고 지시로만 녹였다. 형식은 참고한 LLM 학습 시스템 연구들의 부록 프롬프트처럼 `# Role → # Conversation → # Feedback targets → # Task → # Scores → # Output` 섹션으로 짧게 썼다.

## 공통 (네 파일 모두)

| 요소 | 내용 | 근거 |
|---|---|---|
| 피드백 대상 2가지 | ① Meaning: 의미 전달을 막거나 왜곡하는 오류 ② Naturalness: 이해는 되지만 원어민이라면 더 자연스럽게 말할 표현. 어휘·문법·화용에 집중 | 연구팀 기준 |
| 피드백 형식 | 간단한 피드백 = 발화 전체를 최소한으로 고친 문장(재구성·명시적 교정), 자세한 피드백·Delayed 종합 = 규칙이나 이유를 설명하는 메타언어적 단서 | Lyster & Ranta (1997); Ellis (2009) |
| 최소 수정 | 학습자의 의미·말투·수준 유지, 한 발화에 최대 3곳 | Ellis (2009) |
| 점수 | L1 의미 미전달 · L2 부자연스러움 · 시급성 1–10 (높을수록 피드백이 필요한 쪽). 저장용으로만 기록하고 피드백 결정에는 쓰지 않음 | 연구팀 기준 |
| 입력 표시 | 발화가 음성 인식 결과이고 문장부호가 없을 수 있다고 알려 줌 | — |

## User Trigger — `feedback_user_trigger.txt`
- 학습자가 버튼을 누른 순간 생성. **학습자가 무엇이 궁금했을지** 생각하고 그에 답하도록 함 (`likely_concern`).
- 학습자가 이미 요청했으므로 필요 여부 판단 단계(`needs_feedback`)는 두지 않음. 고칠 부분이 있으면 고치고, 없으면 원문 그대로 → 화면에 "고칠 부분 없음".
- 요청하지 않은 발화는 세션 후 같은 프롬프트로 만들어 Annotation에서만 회색으로 보여준다 ("요청했다면 봤을 피드백").

참고
1. Ellis, Basturkmen & Loewen (2001a). Learner uptake in communicative ESL lessons. *Language Learning*, 51(2), 281–318. — 학습자가 시작한 형태 초점 에피소드에서 uptake가 더 높음
2. Ellis, Basturkmen & Loewen (2001b). Preemptive focus on form in the ESL classroom. *TESOL Quarterly*, 35(3), 407–432. — 학습자가 먼저 묻는 형태 질문은 주로 어휘
3. Schmidt (1990). The role of consciousness in second language learning. *Applied Linguistics*, 11(2), 129–158. — 요청 = 학습자가 스스로 차이를 알아차린 신호 (noticing)
4. Lyster & Ranta (1997). Corrective feedback and learner uptake. *Studies in Second Language Acquisition*, 19(1), 37–66.

## AI Decision — `feedback_ai_decision.txt`
- 매 발화 직후 생성(최근 8턴 참고). 대화를 끊는 비용을 명시하고, **지금 꼭 필요할 때만, 필요한 만큼만** 피드백하도록 함.
- 필요 판단: ①은 항상, ②는 분명히 비원어민스럽거나 최근 대화에서 반복될 때. 사소한 실수는 넘김.
- 판단 근거 `rationale` (한국어 1–2문장)를 남겨 Annotation에서 보여준 발화·보여주지 않은 발화 모두에 표시.
- 피드백이 먼저 나오고 그다음 대화 상대가 말한다.

참고
1. Aljaafreh & Lantolf (1994). Negative feedback as regulation and second language learning in the zone of proximal development. *The Modern Language Journal*, 78(4), 465–483. — 도움은 필요한 만큼(graduated), 필요할 때만(contingent)
2. Nassaji & Swain (2000). A Vygotskian perspective on corrective feedback in L2. *Language Awareness*, 9(1), 34–51. — 학습자 수준에 맞춘 협상된 도움이 무작위 도움보다 효과적
3. Ellis (2009). Corrective feedback and teacher development. *L2 Journal*, 1(1), 3–18. — 무엇을·언제·어떻게 교정할지, 선택적 교정
4. Lyster, Saito & Sato (2013). Oral corrective feedback in second language classrooms. *Language Teaching*, 46(1), 1–40. — 교정과 의사소통 흐름의 균형

## Delayed — `feedback_delayed_turn.txt` + `feedback_delayed_summary.txt`
- 매 발화 뒤에서 필요 여부를 판단해 만들어 두고(대화 중 표시 안 함), 종료 후 **종합 피드백을 맨 위에**, 발화별 피드백을 아래에 나열.
- 종합은 반복 패턴마다 짧은 이름·개수·**규칙 단서(cue)** 한 문장 + 총평. 개별 교정을 반복하지 않고 다음에 적용할 규칙으로 정리 (메타언어적).
- 고칠 부분이 없던 발화는 마지막 화면에 넣지 않음.

참고
1. Li, Zhu & Ellis (2016). The effects of the timing of corrective feedback on the acquisition of a new linguistic structure. *The Modern Language Journal*, 100(1), 276–295.
2. Fu & Li (2022). The effects of immediate and delayed corrective feedback on L2 development. *Studies in Second Language Acquisition*, 44(1), 2–34.
3. Li, Ou & Lee (2025). The timing of corrective feedback in second language learning (Research timeline). *Language Teaching*.
4. Ellis (2009). Corrective feedback and teacher development. *L2 Journal*, 1(1), 3–18.
5. Lyster & Ranta (1997). — 메타언어적 피드백의 정의

## 프롬프트 형식 참고 (LLM 기반 말하기 학습 시스템)
- Cha, Han, Yoo & Oh (2024). CHOP: Integrating ChatGPT into EFL oral presentation practice. arXiv:2407.07393 — 루브릭·출력 예시를 분리한 짧은 템플릿
- Park, Ma, Lee & Yoon (2026). AI Twin: Enhancing ESL speaking practice through AI self-clones of a better me. CHI '26, arXiv:2601.11103 — "필요할 때만 고쳐 말하기", 의미·말투 유지
- Fernández-Espinosa et al. (2025). Practicing a second language without fear: Mixed reality agents for interactive group conversation. arXiv:2510.08227 — 교정 전략 블록을 기본 대화 프롬프트에서 분리
