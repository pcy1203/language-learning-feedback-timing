// 마이크 버튼: idle(누르면 녹음) / rec(녹음 중, 누르면 보내기) / 비활성(AI 말하는 중 등)
import { h, icon } from '../lib/dom.js';

export function createMicButton({ onClick }) {
  const ring = h('span', { class: 'mic-ring', 'aria-hidden': 'true', hidden: true });
  const btn = h('button', { type: 'button', class: 'mic', onclick: () => onClick() });
  const label = h('span', { class: 'mic-label' });
  const el = h('div', { class: 'mic-wrap' }, h('span', { class: 'mic-holder' }, ring, btn), label);

  function set(stateName, text) {
    btn.replaceChildren();
    btn.classList.toggle('is-rec', stateName === 'rec');
    label.classList.toggle('is-rec', stateName === 'rec');
    ring.hidden = stateName !== 'rec';
    if (stateName === 'rec') {
      btn.append(h('span', { class: 'stop', 'aria-hidden': 'true' }));
      btn.setAttribute('aria-label', '발화 마무리하기');
      btn.disabled = false;
    } else {
      btn.append(icon('mic', 26));
      btn.setAttribute('aria-label', stateName === 'idle' ? '눌러서 말하기' : text);
      btn.disabled = stateName !== 'idle';
    }
    label.textContent = text;
  }

  return { el, set };
}
