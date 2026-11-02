// 경과 시간 타이머 (00:00 부터 증가). 제한 시간을 넘으면 빨간색으로 바뀐다.
import { h, icon, fmtMMSS } from '../lib/dom.js';

export function createTimer({ limitSec, onExpire }) {
  const t = h('span', { class: 't' }, '00:00');
  const el = h('div', { class: 'timer', role: 'timer', 'aria-live': 'off' },
    icon('clock', 16), t, h('span', { class: 'limit' }, `/ ${fmtMMSS(limitSec)}`));
  let startMs = Date.now();
  let handle = null;
  let expired = false;

  function tick() {
    const sec = (Date.now() - startMs) / 1000;
    t.textContent = fmtMMSS(sec);
    el.setAttribute('aria-label', `경과 시간 ${Math.floor(sec / 60)}분 ${Math.floor(sec % 60)}초`);
    if (!expired && sec >= limitSec) {
      expired = true;
      el.classList.add('is-over');
      onExpire?.(sec);
    }
  }

  return {
    el,
    start(fromMs) {
      startMs = fromMs || Date.now();
      tick();
      handle = setInterval(tick, 500);
    },
    elapsed() { return (Date.now() - startMs) / 1000; },
    isOver() { return expired; },
    stop() { clearInterval(handle); },
  };
}
