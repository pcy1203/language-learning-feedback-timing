// 대화 말풍선: AI는 왼쪽, 나는 오른쪽
import { h, icon, fmtClock } from '../lib/dom.js';

export function aiMessage(turn, { onReplay } = {}) {
  const bubble = h('p', { class: 'bubble bubble-ai', lang: 'en' }, turn.text);
  const meta = h('div', { class: 'msg-meta' },
    h('b', {}, 'AI 파트너'),
    h('span', {}, fmtClock(turn.ts)),
    onReplay ? h('button', { type: 'button', class: 'icon-btn', 'aria-label': '다시 듣기', onclick: () => onReplay(turn) }, icon('speaker', 15)) : null);
  const el = h('div', { class: 'msg msg-ai', 'data-turn': turn.id }, h('div', { class: 'msg-col' }, meta, bubble));
  return {
    el,
    setSpeaking(on) {
      bubble.classList.toggle('is-speaking', on);
      const label = meta.querySelector('b');
      label.textContent = on ? 'AI 파트너 · 말하는 중' : 'AI 파트너';
    },
  };
}

export function typingMessage() {
  return h('div', { class: 'msg msg-ai' },
    h('div', { class: 'msg-col' },
      h('div', { class: 'msg-meta' }, h('b', {}, 'AI 파트너')),
      h('div', { class: 'bubble bubble-ai typing', 'aria-label': 'AI가 답을 준비하고 있어요' }, h('i'), h('i'), h('i'))));
}

export function userMessage(turn, { pending = false } = {}) {
  const slot = h('div', { class: 'msg-extra', style: { display: 'contents' } });
  const col = h('div', { class: 'msg-col' },
    h('div', { class: 'msg-meta' }, h('b', {}, '나'), h('span', {}, fmtClock(turn.ts))),
    h('p', { class: `bubble bubble-user${pending ? ' bubble-pending' : ''}`, lang: 'en' }, turn.text),
    slot);
  const el = h('div', { class: 'msg msg-user', 'data-turn': turn.id ?? '' }, col);
  return { el, slot };
}

// 녹음 중 실시간 전사 말풍선
export function liveMessage() {
  const finals = h('span', {});
  const interim = h('span', { class: 'interim' });
  const bubble = h('p', { class: 'bubble bubble-user bubble-live', lang: 'en', 'aria-live': 'polite' }, finals, ' ', interim, h('span', { class: 'caret', 'aria-hidden': 'true' }));
  const el = h('div', { class: 'msg msg-user' },
    h('div', { class: 'msg-col' },
      h('div', { class: 'msg-meta' }, h('span', { class: 'rec-dot', 'aria-hidden': 'true' }), h('span', { class: 'live-label' }, '듣고 있어요')),
      bubble));
  return {
    el,
    update({ finals: f, interim: i }) { finals.textContent = f; interim.textContent = i; },
  };
}
