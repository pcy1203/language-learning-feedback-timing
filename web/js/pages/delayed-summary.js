// Delayed: 대화가 끝난 뒤 피드백을 모아서 보여준다 (간단한 / 자세한 탭)
import { api } from '../api.js';
import { state, currentTask } from '../state.js';
import { h, fmtClock } from '../lib/dom.js';
import { highlighted } from '../lib/diff.js';
import { logEvent } from '../lib/log.js';
import { feedbackItems } from '../components/feedback-card.js';
import { MODE_LABEL } from '../components/mode-toggle.js';
import { pageFooter } from '../components/page-footer.js';

export function render(main, ctx) {
  const task = currentTask();
  let tab = state.modes[task] || 'simple';
  let session = null;

  const tabs = h('div', { class: 'tabs', role: 'tablist', 'aria-label': '피드백 방식' });
  const content = h('div', { class: 'field', style: { gap: '20px' } }, h('p', { class: 'lead' }, '불러오는 중…'));
  const footer = pageFooter({ onClick: () => ctx.next() });

  main.append(
    h('div', { class: 'page' },
      h('div', { class: 'page-inner' },
        h('header', { class: 'page-head' },
          h('h1', { class: 'page-title' }, '대화 피드백 모아보기'),
          h('p', { class: 'lead' }, '종합 피드백과 피드백이 있었던 발화를 모아서 보여드려요. 천천히 읽어본 뒤 다음으로 넘어가 주세요.')),
        tabs, content)),
    footer.el,
  );

  function drawTabs() {
    tabs.replaceChildren(...Object.entries(MODE_LABEL).map(([key, label]) =>
      h('button', {
        type: 'button', class: 'tab', role: 'tab', 'aria-selected': String(key === tab),
        onclick: () => { if (key !== tab) { tab = key; logEvent('delayed_tab_switch', { to: key }); drawTabs(); drawContent(); } },
      }, label)));
  }

  function drawContent() {
    const summary = session.summary || { patterns: [], overview: '' };
    const turns = session.turns.filter((t) => t.role === 'user' && t.feedback?.has_issue);
    // 종합 피드백 (자주 나온 부분 + 규칙 단서 + 총평) — 두 탭 모두 맨 위에
    const patternBox = h('section', { class: 'soft-box field', 'aria-label': '종합 피드백', style: { gap: '14px' } },
      h('h2', { style: { fontSize: '14px', fontWeight: 700 } }, '종합 피드백'),
      summary.overview ? h('p', { style: { fontSize: '14px', lineHeight: 1.7, color: 'var(--ink-2)' } }, summary.overview) : null,
      summary.patterns.length
        ? h('ul', { class: 'pattern-list' }, summary.patterns.map((p) => h('li', {},
          h('span', { class: 'chip' }, p.label, h('strong', {}, String(p.count))),
          p.cue ? h('span', { class: 'cue' }, p.cue) : null)))
        : h('p', { style: { fontSize: '14px', color: 'var(--muted)' } }, '크게 반복된 실수는 없었어요.'));

    const items = turns.length
      ? h('ol', { class: 'list' }, turns.map((t) =>
        h('li', { class: 'summary-item' },
          h('span', { class: 'when' }, `${fmtClock(t.ts)} 발화`),
          h('p', { class: 'strike', lang: 'en', style: { fontSize: '14px' } }, t.text),
          h('p', { class: 'fb-text', lang: 'en' }, highlighted(t.text, t.feedback.revised)),
          tab === 'detailed' ? feedbackItems(t.feedback.items) : null)))
      : h('p', { class: 'lead' }, '피드백이 있었던 발화가 없어요.');

    content.replaceChildren(patternBox, items);
  }

  api.getSession(task).then((s) => {
    session = s;
    drawTabs();
    drawContent();
    logEvent('delayed_summary_view', { tab, items: s.turns.filter((t) => t.feedback?.has_issue).length });
  }).catch((err) => {
    content.replaceChildren(h('div', { class: 'error-box', role: 'alert' }, err.message));
  });
}
