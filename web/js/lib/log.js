// 브라우저 이벤트를 서버 로그(events.jsonl)로 보낸다. 실패해도 화면 흐름은 막지 않는다.
import { state, currentTask } from '../state.js';

export function logEvent(event, data = {}, task = undefined) {
  if (state.role !== 'participant' || !state.code) return;
  const body = {
    code: state.code,
    task: task === undefined ? currentTask() : task,
    event,
    data,
    client_ts: new Date().toISOString(),
  };
  try {
    fetch('/api/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      keepalive: true,
    }).catch(() => {});
  } catch { /* 무시 */ }
}
