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

export function save() {
  try { sessionStorage.setItem(KEY, JSON.stringify(state)); } catch { /* 무시 */ }
}

export function resetState() {
  Object.assign(state, initial());
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
