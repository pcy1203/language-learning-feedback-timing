// 화면 전환: 로그인 → (Admin) / (참가자: Task별 설명 → 방식 선택 → 대화 → [종합 피드백] → 평가 → 설문) → 종료
import { api } from './api.js';
import { state, save, resetState, currentTask, stepsFor } from './state.js';
import { h, clear } from './lib/dom.js';
import { logEvent } from './lib/log.js';
import { renderSidebar } from './components/sidebar.js';
import * as login from './pages/login.js';
import * as admin from './pages/admin.js';
import * as taskIntro from './pages/task-intro.js';
import * as modeSelect from './pages/mode-select.js';
import * as chat from './pages/chat.js';
import * as delayedSummary from './pages/delayed-summary.js';
import * as annotation from './pages/annotation.js';
import * as survey from './pages/survey.js';
import * as done from './pages/done.js';

const PAGES = { intro: taskIntro, mode: modeSelect, chat, summary: delayedSummary, annotation, survey };
const root = document.getElementById('app');
let cleanup = null;

function render() {
  if (cleanup) { try { cleanup(); } catch { /* 무시 */ } cleanup = null; }
  clear(root);
  window.scrollTo(0, 0);

  if (!state.role) { cleanup = login.render(root, ctx); return; }
  if (state.role === 'admin') { cleanup = admin.render(root, ctx); return; }
  if (state.finished) { cleanup = done.render(root, ctx); return; }

  const page = PAGES[state.step] || taskIntro;
  const aside = h('aside', { class: 'sidebar' });
  const main = h('main', { class: 'main', id: 'main' });
  root.append(h('div', { class: 'shell' }, aside, main));
  renderSidebar(aside, { onExit: exit });
  cleanup = page.render(main, ctx);
}

function persistProgress() {
  save();
  api.progress().catch(() => {});
}

function goStep(step) {
  state.step = step;
  persistProgress();
  render();
}

function next() {
  const steps = stepsFor(currentTask());
  const i = steps.indexOf(state.step);
  if (i >= 0 && i < steps.length - 1) {
    goStep(steps[i + 1]);
    return;
  }
  if (state.taskIndex < state.participant.order.length - 1) {
    state.taskIndex += 1;
    state.step = 'intro';
  } else {
    state.finished = true;
  }
  persistProgress();
  render();
}

function logout() {
  resetState();
  render();
}

// 참가자 '나가기': 진행 상황은 서버에 저장돼 있으므로, 같은 코드를 다시 입력하면 이어서 진행된다
function exit() {
  const msg = state.step === 'chat'
    ? '대화 중에 나가면 지금 녹음 중인 발화는 저장되지 않아요. 정말로 나갈까요?'
    : '지금까지 진행한 내용은 저장되었으며, 같은 코드를 다시 입력하면 이어서 할 수 있어요. 나갈까요?';
  if (!window.confirm(msg)) return;
  logEvent('exit_click', { task_index: state.taskIndex, step: state.step });
  api.progress().catch(() => {});
  resetState();
  render();
}

const ctx = { render, next, goStep, logout, persistProgress, exit };

document.addEventListener('visibilitychange', () => {
  logEvent('page_visibility', { state: document.visibilityState, step: state.step });
});

// 새로고침하면 참가자는 코드 입력 화면부터 시작한다.
// 진행 상태는 서버에 저장돼 있어서, 코드를 입력하면 하던 단계로 이어서 들어간다 (코드는 미리 채워 둠).
if (state.role === 'participant') {
  state.resumeCode = state.code;
  state.role = null;
}
save();
render();
