// 본문 우측 하단의 다음 버튼 바
import { h, icon } from '../lib/dom.js';

export function pageFooter({ label = '다음', onClick, enabled = true, hint = '', arrow = true }) {
  const hintEl = h('span', { class: 'hint' }, hint);
  const btn = h('button', { type: 'button', class: 'btn btn-primary btn-lg', onclick: () => onClick() }, label, arrow ? icon('arrow', 16) : null);
  const el = h('div', { class: 'page-footer' }, hintEl, btn);
  function setEnabled(on, newHint = '') {
    btn.disabled = !on;
    hintEl.textContent = on ? '' : newHint;
  }
  setEnabled(enabled, hint);
  return { el, btn, setEnabled, setBusy(b) { btn.disabled = b; } };
}
