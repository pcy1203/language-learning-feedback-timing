// 간단한 피드백 / 자세한 피드백 전환
import { h } from '../lib/dom.js';

export const MODE_LABEL = { simple: '간단한 피드백', detailed: '자세한 피드백' };

export function createModeToggle(mode, onChange) {
  let current = mode;
  const buttons = Object.entries(MODE_LABEL).map(([key, label]) =>
    h('button', { type: 'button', 'data-mode': key, 'aria-pressed': String(key === current), onclick: () => select(key) }, label));
  function select(key) {
    if (key === current) return;
    current = key;
    buttons.forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === key)));
    onChange(key);
  }
  const el = h('div', { class: 'seg', role: 'group', 'aria-label': '피드백 표시 방식' }, buttons);
  return { el, get: () => current };
}
