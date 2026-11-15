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

// 내 녹음 재생 버튼 (대화 화면 · Annotation 공용). onPlay(url, button) 은 재생이 끝나면 resolve.
export function playButton(url, onPlay, { label = '내 목소리 듣기' } = {}) {
  const btn = h('button', { type: 'button', class: 'play-btn', 'aria-label': label, title: label });
  const idle = () => { btn.classList.remove('is-playing'); btn.replaceChildren(icon('play', 13), h('span', {}, '듣기')); };
  idle();
  btn.addEventListener('click', async () => {
    btn.classList.add('is-playing');
    btn.replaceChildren(icon('stopSq', 13), h('span', {}, '멈춤'));
    try { await onPlay(url, btn); } finally { idle(); }
  });
  return btn;
}

export function userMessage(turn, { pending = false, onPlay = null } = {}) {
  const slot = h('div', { class: 'msg-extra', style: { display: 'contents' } });
  const meta = h('div', { class: 'msg-meta' }, h('b', {}, '나'), h('span', {}, fmtClock(turn.ts)),
    turn.recording_url && onPlay ? playButton(turn.recording_url, onPlay) : null);
  const bubble = h('p', { class: `bubble bubble-user${pending ? ' bubble-pending' : ''}`, lang: 'en' }, turn.text);
  const col = h('div', { class: 'msg-col' }, meta, bubble, slot);
  const el = h('div', { class: 'msg msg-user', 'data-turn': turn.id ?? '' }, col);
  return { el, slot, bubble };
}

// 녹음 중 실시간 전사 말풍선
export function liveMessage({ label = '듣고 있어요' } = {}) {
  const finals = h('span', {});
  const interim = h('span', { class: 'interim' });
  const bubble = h('p', { class: 'bubble bubble-user bubble-live', lang: 'en', 'aria-live': 'polite' }, finals, ' ', interim, h('span', { class: 'caret', 'aria-hidden': 'true' }));
  const el = h('div', { class: 'msg msg-user' },
    h('div', { class: 'msg-col' },
      h('div', { class: 'msg-meta' }, h('span', { class: 'rec-dot', 'aria-hidden': 'true' }), h('span', { class: 'live-label' }, label)),
      bubble));
  return {
    el,
    update({ finals: f, interim: i }) { finals.textContent = f; interim.textContent = i; },
  };
}
