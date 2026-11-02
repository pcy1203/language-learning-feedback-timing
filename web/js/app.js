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
  renderSidebar(aside);
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

const ctx = { render, next, goStep, logout, persistProgress };

document.addEventListener('visibilitychange', () => {
  logEvent('page_visibility', { state: document.visibilityState, step: state.step });
});

render();
