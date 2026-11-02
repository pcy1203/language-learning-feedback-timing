// 실험 종료
import { state } from '../state.js';
import { h, icon } from '../lib/dom.js';
import { logEvent } from '../lib/log.js';

export function render(root, ctx) {
  const names = state.participant.order.map((k) => state.config.tasks[k].name).join(' · ');
  root.append(h('div', { class: 'solo' },
    h('header', { class: 'solo-header' }, state.config.study_title),
    h('main', { class: 'solo-main' },
      h('div', { class: 'done-box' },
        h('span', { class: 'done-mark', 'aria-hidden': 'true' }, icon('check', 30)),
        h('div', { class: 'page-head', style: { alignItems: 'center' } },
          h('h1', { class: 'page-title', style: { fontSize: '30px' } }, '실험이 모두 끝났어요'),
          h('p', { class: 'lead' }, '참여해 주셔서 감사합니다. 정말 고생 많으셨어요.', h('br'), '응답은 안전하게 저장되었고, 이제 창을 닫으셔도 됩니다.')),
        h('dl', { class: 'done-summary' },
          h('dt', {}, '참가 코드'), h('dd', { style: { letterSpacing: '.08em' } }, state.participant.code),
          h('dt', {}, '완료한 대화'), h('dd', {}, names)),
        h('button', {
          type: 'button', class: 'btn btn-primary btn-lg',
          onclick: () => { logEvent('restart_click', {}, null); ctx.logout(); },
        }, '처음으로')))));
}
