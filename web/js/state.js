// 현재 참가자 · Task · 단계 상태. 새로고침해도 이어지도록 sessionStorage 에 보관한다.
const KEY = 'fts-state-v1';

const initial = () => ({
  role: null,            // 'participant' | 'admin'
  code: null,
  adminToken: null,
  participant: null,     // { code, order: ['user','ai','delayed'], topics, topic_labels }
  config: null,          // { study_title, settings, tasks, survey, annotation }
  taskIndex: 0,
  step: 'intro',
  finished: false,
  modes: {},             // { user: 'simple', ai: 'detailed', ... }
});

function load() {
  try { return JSON.parse(sessionStorage.getItem(KEY)) || {}; } catch { return {}; }
}

export const state = Object.assign(initial(), load());

// ?test=true 로 들어오면 테스트 모드 (대화 화면에서 발화 아래 L1·L2 점수 표시). ?test=false 로 끈다.
const testParam = new URLSearchParams(location.search).get('test');
if (testParam !== null) state.testMode = testParam === 'true' || testParam === '1';

export function save() {
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* 무시 */ }
}

export function resetState() {
  const keep = { testMode: state.testMode };
  for (const k of Object.keys(state)) delete state[k];
  Object.assign(state, initial(), keep);
  try { sessionStorage.removeItem(KEY); } catch { /* 무시 */ }
}

export function currentTask() {
  return state.participant?.order?.[state.taskIndex] ?? null;
}

export const STEP_LABELS = {
  intro: '설명',
  mode: '피드백 방식 선택',
  chat: '대화',
  summary: '종합 피드백',
  annotation: '평가',
  survey: '세션 설문',
};

export function stepsFor(task) {
  return task === 'delayed'
    ? ['intro', 'mode', 'chat', 'summary', 'annotation', 'survey']
    : ['intro', 'mode', 'chat', 'annotation', 'survey'];
}
