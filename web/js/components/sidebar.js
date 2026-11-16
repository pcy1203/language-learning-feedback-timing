// 좌측 진행 사이드바: 1 Task → 2 Task → 3 Task, 현재 Task 안의 세부 단계
import { h, icon } from '../lib/dom.js';
import { state, stepsFor, STEP_LABELS } from '../state.js';

export function renderSidebar(aside, { onExit } = {}) {
  const { participant, config } = state;
  const steps = participant.order.map((task, i) => {
    const done = state.finished || i < state.taskIndex;
    const now = !state.finished && i === state.taskIndex;
    const cls = ['sb-step', done && 'is-done', now && 'is-current'].filter(Boolean).join(' ');
    let subs = null;
    if (now) {
      const list = stepsFor(task);
      const cur = list.indexOf(state.step);
      subs = h('ul', { class: 'sb-subs' }, list.map((s, j) => {
        const cls = ['sb-sub', j < cur && 'is-done', j === cur && 'is-now', s === 'survey' && 'is-survey'].filter(Boolean).join(' ');
        return h('li', { class: cls },
          j < cur ? icon('check', 12) : j === cur ? icon('arrow', 12) : h('span'),
          // 세션 설문은 다른 단계와 구분되도록 따로 표시
          s === 'survey' ? h('span', { class: 'sb-survey-tag' }, icon('clipboard', 12), '세션 설문') : h('span', {}, STEP_LABELS[s]));
      }));
    }
    return h('li', { class: cls, 'aria-current': now ? 'step' : null },
      h('span', { class: 'sb-num' }, String(i + 1)),
      h('div', { class: 'sb-body' },
        h('div', { class: 'sb-row' },
          h('span', { class: 'sb-name' }, config.tasks[task].name),
          h('span', { class: 'sb-status' }, done ? '완료' : now ? '진행 중' : '')),
        h('span', { class: 'sb-topic' }, participant.topic_labels[task]),
        subs));
  });

  aside.append(
    h('div', { class: 'sb-head' },
      h('span', { class: 'sb-title' }, config.study_title),
      h('span', { class: 'sb-code' }, '참가 코드 ', h('strong', {}, participant.code))),
    h('ol', { class: 'sb-steps', 'aria-label': '진행 단계' }, steps),
    onExit ? h('div', { class: 'sb-foot' },
      h('button', { type: 'button', class: 'sb-exit', onclick: onExit }, icon('exit', 15), '나가기'),
) : null,
  );
}
