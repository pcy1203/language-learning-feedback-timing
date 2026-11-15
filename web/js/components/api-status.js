// API 연결 상태 표시 (로그인 화면 아래쪽, 관리자 화면 위쪽)
// 서버는 키가 있는지만 알려주고 키 값은 보내지 않는다. 실제 호출 확인은 관리자 화면의 '연결 확인'.
import { h } from '../lib/dom.js';

function badge(label, s) {
  const state = s.mock ? (s.key ? 'mock' : 'nokey') : 'ok';
  const text = { ok: 'API 키 연결됨', mock: 'MOCK (MOCK_LLM=1)', nokey: 'MOCK · 키 없음' }[state];
  return h('span', { class: `api-badge ${state}`, title: `${s.provider} · ${s.model}` },
    h('i', { 'aria-hidden': 'true' }),
    h('b', {}, label),
    h('span', { class: 'model' }, s.model),
    h('span', { class: 'state' }, text));
}

export function apiStatus(api, { compact = false } = {}) {
  if (!api) return h('span');
  return h('div', { class: `api-status${compact ? ' compact' : ''}`, role: 'status', 'aria-label': 'API 연결 상태' },
    badge('대화 AI', api.chat),
    badge('피드백', api.feedback),
    compact ? null : h('span', { class: 'api-voice' }, `AI 음성: ${api.voice}`),
    compact || !api.stt ? null : h('span', { class: 'api-voice' },
      `전사: ${api.stt.label}${api.stt.cleanup ? ` + 다듬기(${api.stt.cleanup_model})` : ''}${api.stt.mock ? ' · MOCK' : ''}`));
}
