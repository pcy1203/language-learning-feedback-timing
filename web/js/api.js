// 서버 API 호출 모음
import { state } from './state.js';

async function request(method, url, body, { admin = false } = {}) {
  const headers = {};
  const isForm = body instanceof FormData;
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json';
  if (admin && state.adminToken) headers['X-Admin-Token'] = state.adminToken;
  let res;
  try {
    res = await fetch(url, { method, headers, body: body === undefined ? undefined : isForm ? body : JSON.stringify(body) });
  } catch {
    const err = new Error('서버에 연결하지 못했어요. 네트워크를 확인해 주세요.');
    err.status = 0;
    throw err;
  }
  if (!res.ok) {
    let msg = `요청을 처리하지 못했어요 (${res.status})`;
    try {
      const j = await res.json();
      if (typeof j.detail === 'string') msg = j.detail;
    } catch { /* 무시 */ }
    const err = new Error(msg);
    err.status = res.status;
    throw err;
  }
  const type = res.headers.get('content-type') || '';
  return type.includes('application/json') ? res.json() : res;
}

const code = () => state.code;

export const api = {
  publicInfo: () => request('GET', '/api/public'),
  login: (c) => request('POST', '/api/login', { code: c }),
  progress: () => request('POST', '/api/progress', {
    code: code(), task_index: state.taskIndex, step: state.step, finished: state.finished, modes: state.modes,
  }),

  startSession: (task, mode) => request('POST', '/api/session/start', { code: code(), task, mode }),
  getSession: (task) => request('GET', `/api/session/${encodeURIComponent(code())}/${task}`),
  setMode: (task, mode) => request('POST', '/api/session/mode', { code: code(), task, mode }),
  endSession: (task, elapsed_s) => request('POST', '/api/session/end', { code: code(), task, elapsed_s }),

  // 발화 1개: 글자(브라우저 전사 또는 직접 입력) + 녹음 파일
  sendTurn: (task, { text = '', duration_s = null, input = 'speech', audio = null } = {}) => {
    const f = new FormData();
    f.append('code', code());
    f.append('task', task);
    f.append('text', text);
    f.append('input', input);
    if (duration_s !== null && duration_s !== undefined) f.append('duration_s', String(Math.round(duration_s * 100) / 100));
    if (audio) f.append('audio', audio, `utterance.${/mp4/.test(audio.type) ? 'm4a' : /ogg/.test(audio.type) ? 'ogg' : 'webm'}`);
    return request('POST', '/api/turn', f);
  },
  getReply: (task, turn_id) => request('POST', '/api/turn/reply', { code: code(), task, turn_id }),
  feedbackScores: (task, turn_id) => request('POST', '/api/feedback/scores', { code: code(), task, turn_id }),
  awaitFeedback: (task, turn_id) => request('POST', '/api/feedback/await', { code: code(), task, turn_id }),
  requestFeedback: (task, turn_id) => request('POST', '/api/feedback/request', { code: code(), task, turn_id }),

  saveAnnotation: (task, answers) => request('POST', '/api/annotation', { code: code(), task, answers }),
  submitSurvey: (task, likert, text) => request('POST', '/api/survey', { code: code(), task, likert, text }),

  admin: {
    meta: () => request('GET', '/api/admin/meta', undefined, { admin: true }),
    codes: () => request('GET', '/api/admin/codes', undefined, { admin: true }),
    createCode: (body) => request('POST', '/api/admin/codes', body, { admin: true }),
    deleteCode: (c) => request('DELETE', `/api/admin/codes/${encodeURIComponent(c)}`, undefined, { admin: true }),
    participant: (c) => request('GET', `/api/admin/participants/${encodeURIComponent(c)}`, undefined, { admin: true }),
    logIndex: () => request('GET', '/api/admin/log-index', undefined, { admin: true }),
    checkApi: () => request('POST', '/api/admin/check-api', {}, { admin: true }),
    dashboard: (onlyFinished) => request('GET', `/api/admin/dashboard?only_finished=${onlyFinished ? 'true' : 'false'}`, undefined, { admin: true }),
  },
};

// 다운로드 링크는 헤더를 못 붙이므로 토큰을 쿼리로 붙인다
export function adminUrl(path) {
  const sep = path.includes('?') ? '&' : '?';
  return `${path}${sep}token=${encodeURIComponent(state.adminToken || '')}`;
}
