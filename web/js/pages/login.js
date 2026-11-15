// 참가 코드 입력 (admin 입력 시 관리자 화면)
import { api } from '../api.js';
import { state, save } from '../state.js';
import { h, icon } from '../lib/dom.js';
import { sttSupported } from '../lib/stt.js';
import { recorderSupported } from '../lib/recorder.js';
import { apiStatus } from '../components/api-status.js';

export function render(root, ctx) {
  const titleEl = h('header', { class: 'solo-header' }, 'AI 활용 외국어 말하기 학습에서 교정적 피드백의 시점 연구');
  const statusSlot = h('div', { class: 'login-status' });
  // 음성 입력이 안 되는 브라우저 안내 (whisper 전사는 녹음만 되면 된다)
  const sttWarn = h('p', { class: 'notice', hidden: true }, '이 브라우저는 음성 인식을 지원하지 않아요. Chrome으로 접속해 주세요.');
  api.publicInfo().then((p) => {
    if (p.study_title) titleEl.textContent = p.study_title;
    statusSlot.replaceChildren(apiStatus(p.api));
    const whisper = p.api?.stt?.engine === 'whisper';
    sttWarn.hidden = whisper ? recorderSupported() : sttSupported();
  }).catch(() => { sttWarn.hidden = sttSupported(); });

  const input = h('input', {
    id: 'code', class: 'code-input', name: 'code', autocomplete: 'off', autocapitalize: 'characters',
    spellcheck: 'false', maxlength: '6', placeholder: 'ABC123', 'aria-describedby': 'login-error',
  });
  const error = h('p', { id: 'login-error', class: 'form-error', role: 'alert' });
  const submit = h('button', { type: 'submit', class: 'btn btn-primary btn-lg btn-block' }, '시작하기');
  // 새로고침으로 돌아온 경우: 코드를 미리 채우고 '이어서 하기'로 안내
  const resume = state.resumeCode || '';
  const resumeNote = h('p', { class: 'resume-note', hidden: !resume }, '진행 중이던 코드예요. 누르면 하던 곳부터 이어서 진행해요.');
  function syncResume() {
    const same = !!resume && input.value === resume;
    submit.textContent = same ? '이어서 하기' : '시작하기';
    resumeNote.hidden = !same;
  }
  if (resume) input.value = resume;
  input.addEventListener('input', () => {
    input.value = input.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6);
    syncResume();
  });
  syncResume();

  async function onSubmit(e) {
    e.preventDefault();
    error.textContent = '';
    const code = input.value.trim();
    if (!code) { error.textContent = '코드를 입력해 주세요.'; input.focus(); return; }
    submit.disabled = true;
    try {
      const res = await api.login(code);
      if (res.role === 'admin') {
        Object.assign(state, { role: 'admin', adminToken: res.token });
      } else {
        Object.assign(state, {
          role: 'participant',
          code: res.participant.code,
          participant: res.participant,
          config: res.config,
          taskIndex: res.state.task_index || 0,
          step: res.state.step || 'intro',
          finished: !!res.state.finished,
          modes: res.state.modes || {},
        });
      }
      state.resumeCode = null;
      save();
      ctx.render();
    } catch (err) {
      error.textContent = err.message;
      submit.disabled = false;
    }
  }

  const notes = [
    h('li', {}, icon('chrome', 16), 'Chrome 브라우저에서 진행해 주세요.'),
    h('li', {}, icon('mic', 16), '마이크 사용 권한을 허용해 주세요.'),
  ];

  root.append(h('div', { class: 'solo' },
    titleEl,
    h('main', { class: 'solo-main' },
      h('div', { class: 'login-box' },
        h('div', { class: 'page-head' },
          h('h1', { class: 'page-title', style: { fontSize: '28px' } }, '참가 코드를 입력해 주세요'),
          h('p', { class: 'lead', style: { fontSize: '15px', color: 'var(--muted)' } }, '연구자에게 받은 6자리 코드를 입력하면 실험이 시작됩니다.')),
        h('form', { class: 'field', onsubmit: onSubmit, novalidate: true },
          h('label', { for: 'code', class: 'field-label' }, '참가 코드'),
          input, resumeNote, error, submit),
        sttWarn,
        h('ul', { class: 'notes' }, notes),
        state.testMode ? h('p', { class: 'notice', style: { background: 'var(--accent-soft)', color: 'var(--accent)', borderColor: 'var(--accent-line)' } }, '테스트 모드 · 대화 화면에서 발화 아래에 L1·L2 점수가 보여요') : null,
        statusSlot))));
  input.focus();
}
