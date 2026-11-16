// Task 설명 + 마이크 확인
import { state, currentTask } from '../state.js';
import { h, icon, fill } from '../lib/dom.js';
import { sttSupported } from '../lib/stt.js';
import { recorderSupported } from '../lib/recorder.js';
import { pageFooter } from '../components/page-footer.js';

export function render(main, ctx) {
  const task = currentTask();
  const { tasks, settings } = state.config;
  const conf = tasks[task];
  const topic = state.participant.topic_labels[task];
  const minutes = Math.round(settings.session_seconds / 60);
  const [rMin, rMax] = settings.recommended_speech_seconds;
  // whisper 전사는 녹음만 되면 되고, 브라우저 전사는 음성 인식이 있어야 한다
  const canSpeak = state.config.stt?.engine === 'whisper' ? recorderSupported() : sttSupported();

  // 세 방식은 이 참가자에게 배정된 진행 순서대로 보여준다
  const order = state.participant.order?.length === 3 ? state.participant.order : ['user', 'ai', 'delayed'];
  const fixed = order.map((k) =>
    h('div', { class: `mode-card${k === task ? ' is-current' : ''}` },
      h('strong', {}, tasks[k].name), h('span', {}, tasks[k].summary)));

  const rules = tasks.rules.map((r, i) =>
    h('li', {}, h('b', {}, String(i + 1)), h('span', {}, fill(r, { minutes, min: rMin, max: rMax }))));

  // 마이크 확인 (입력 크기 막대)
  const bars = Array.from({ length: 5 }, () => h('i'));
  const status = h('span', { class: 'mic-status' }, '마이크를 확인하고 있어요…');
  let stream = null, raf = null, audioCtx = null;
  async function checkMic() {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 512;
      audioCtx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.fftSize);
      let heard = false;
      const loop = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
        const level = Math.min(1, peak / 50);
        bars.forEach((b, i) => {
          const on = level > (i + 1) / 6;
          b.classList.toggle('on', on);
          b.style.height = `${on ? 6 + i * 3 : 4}px`;
        });
        if (level > 0.25 && !heard) {
          heard = true;
          status.textContent = '소리가 잘 들어오고 있어요';
          status.className = 'mic-status ok';
        }
        raf = requestAnimationFrame(loop);
      };
      status.textContent = '말해 보세요. 막대가 움직이면 정상이에요.';
      loop();
    } catch {
      status.textContent = '마이크를 사용할 수 없어요. 브라우저의 마이크 권한을 허용해 주세요.';
      status.className = 'mic-status bad';
    }
  }
  checkMic();

  main.append(
    h('div', { class: 'page' },
      h('div', { class: 'page-inner narrow' },
        h('header', { class: 'page-head' },
          h('span', { class: 'eyebrow' }, `Task ${state.taskIndex + 1} / ${state.participant.order.length}`),
          h('h1', { class: 'page-title', style: { fontSize: '36px' } }, conf.name),
          h('p', { class: 'lead', style: { fontSize: '17px' } }, conf.intro)),
        h('section', { class: 'field', 'aria-labelledby': 'modes-h' },
          h('h2', { id: 'modes-h', class: 'field-label', style: { color: 'var(--muted)' } }, `이번 Task는 ${conf.name} 방식으로 진행해요`),
          h('div', { class: 'mode-grid' }, fixed)),
        h('section', { class: 'card', 'aria-labelledby': 'task-h' },
          h('div', { class: 'card-head' },
            h('h2', { id: 'task-h', class: 'card-title' }, '이번 대화'),
            h('div', { style: { display: 'flex', gap: '8px', flexWrap: 'wrap' } },
              h('span', { class: 'pill' }, h('span', {}, '주제'), h('strong', {}, topic)),
              h('span', { class: 'pill' }, h('span', {}, '시간'), h('strong', {}, `${minutes}분`)))),
          h('div', { class: 'card-body' }, h('ol', { class: 'rules' }, rules))),
        !canSpeak ? h('p', { class: 'notice' }, '이 브라우저는 음성 입력을 지원하지 않아요. Chrome으로 접속해 주세요.') : null,
        h('div', { class: 'soft-box mic-check' },
          h('div', { class: 'mic-check-left' }, icon('mic', 20), '마이크 확인', h('span', { class: 'level', 'aria-hidden': 'true' }, bars)),
          status))),
    pageFooter({ onClick: () => ctx.next() }).el,
  );

  return () => {
    cancelAnimationFrame(raf);
    stream?.getTracks().forEach((t) => t.stop());
    audioCtx?.close().catch(() => {});
  };
}
