import { h } from './dom.js';

export function toast(message, ms = 3200) {
  const root = document.getElementById('toast-root');
  if (!root) return;
  const el = h('div', { class: 'toast', role: 'status' }, message);
  root.append(el);
  setTimeout(() => el.remove(), ms);
}

export function overlay(message) {
  const el = h('div', { class: 'overlay', role: 'status' }, h('div', { class: 'spinner', 'aria-hidden': 'true' }), message);
  document.body.append(el);
  return () => el.remove();
}
