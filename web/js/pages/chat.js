// 대화 세션: AI가 먼저 말하고(음성 + 왼쪽 말풍선), 참가자는 마이크로 말한다(실시간 전사 + 오른쪽 말풍선).
// 조건별 피드백 노출
//   user    : 내 발화 아래 '피드백 보기' 버튼 → 누르면 그때 피드백을 만들어 표시 (고칠 게 없으면 '고칠 부분이 없어요')
//   ai      : 매 발화마다 피드백 AI가 지금 꼭 필요하다고 판단한 경우에만 자동 표시
//   delayed : 대화 중에는 표시하지 않음 (매 발화 뒤에서 만들어 두고, 종료 후 종합 피드백과 함께)
// AI 음성은 Gemini Live 가 만든 음성 파일(audio_url)을 재생하고, 없으면 브라우저 음성으로 읽는다.
// 녹음: 마이크 버튼을 누른 순간부터 다시 누른 순간까지 녹음해 서버에 함께 보낸다 (data/recordings).
// 전사: .env STT_ENGINE=browser 면 브라우저 인식 결과를, whisper 면 서버에서 Whisper 로 전사한 글자를 쓴다.
// 응답 순서: 내 발화를 먼저 받고(POST /api/turn) 대화 상대의 답은 따로 받는다(POST /api/turn/reply).
//   AI Decision : 피드백이 먼저 나온 뒤 대화 상대가 말한다.
//   User Trigger: 내 말이 나온 뒤 최소 2초 지나야 대화 상대가 말한다. '피드백 보기'를 누르면 그때 피드백을 만들고,
//                 만드는 동안에도 대화는 이어진다.
import { api } from '../api.js';
import { state, save, currentTask } from '../state.js';
import { h, icon, fmtClock } from '../lib/dom.js';
import { logEvent } from '../lib/log.js';
import { toast, overlay } from '../lib/toast.js';
import { SpeechInput, sttSupported } from '../lib/stt.js';
import { speak, stopAudio, playClip } from '../lib/audio-player.js';
import { Recorder, recorderSupported } from '../lib/recorder.js';
import { createTimer } from '../components/timer.js';
import { createMicButton } from '../components/mic-button.js';
import { createModeToggle } from '../components/mode-toggle.js';
import { aiMessage, userMessage, liveMessage, typingMessage } from '../components/message-bubble.js';
import { feedbackCard, loadingCard } from '../components/feedback-card.js';

export function render(main, ctx) {
  const task = currentTask();
  const S = state.config.settings;
  const limit = S.session_seconds;
  const [rMin, rMax] = S.recommended_speech_seconds;
  const barMax = S.speech_bar_max_seconds || 60;
  const sttConf = state.config.stt || { engine: 'browser', cleanup: false };
  const whisper = sttConf.engine === 'whisper';
  const delays = state.config.reply_delay_seconds || {};
  const browserStt = sttSupported();
  // whisper 는 녹음만 되면 되고, browser 는 브라우저 음성 인식이 있어야 한다
  const canSpeak = whisper ? recorderSupported() : browserStt;
  const allowTyping = !canSpeak || new URLSearchParams(location.search).has('typing');
  const testMode = !!state.testMode && state.config.test_mode_enabled !== false;

  let mode = state.modes[task] || 'simple';
  let alive = true;
  let ended = false;
  let busy = false;          // AI 응답 대기 또는 음성 재생 중
  let recording = false;
  let stt = null;
  let live = null;
  let recStart = 0;
  let recTick = null;
  const recorder = recorderSupported() ? new Recorder() : null;
  let recordingOn = false;   // 이번 발화를 녹음 중인지
  let sessionStartMs = Date.now();
  const entries = new Map(); // turn_id → { slot, text, fb, meta }
  const aiViews = new Map();

  // ── 상단 ──
  const banner = h('div', { class: 'overtime-banner', role: 'status', hidden: true },
    `${Math.round(limit / 60)}분이 지났어요. 지금 하던 발화를 마친 뒤 세션 종료를 눌러 주세요.`);
  const endBtn = h('button', { type: 'button', class: 'btn btn-dark-outline btn-end', style: { height: '40px' }, onclick: () => endSession() }, '세션 종료');
  const timer = createTimer({
    limitSec: limit,
    onExpire: (sec) => {
      banner.hidden = false;
      endBtn.classList.add('is-over');
      logEvent('timer_expired', { elapsed_s: Math.round(sec) });
    },
  });
  const header = h('header', { class: 'chat-header' },
    h('h1', { class: 'chat-topic' }, state.participant.topic_labels[task]),
    h('div', { class: 'chat-header-right' }, timer.el, endBtn));

  const list = h('div', { class: 'chat-list' });
  const scroller = h('div', { class: 'chat-scroll' }, list);

  // ── 하단 ──
  const mic = createMicButton({ onClick: () => onMic() });
  const meterVal = h('b', {}, '0초');
  const meterFill = h('span', { class: 'fill', style: { width: '0%' } });
  const meter = h('div', { class: 'speech-meter', hidden: true },
    h('div', { class: 'row' }, h('span', {}, '지금 말한 시간'), meterVal),
    h('div', { class: 'speech-bar', role: 'img', 'aria-label': `권장 ${rMin}~${rMax}초` },
      h('span', { class: 'band', style: { left: `${(rMin / barMax) * 100}%`, width: `${((rMax - rMin) / barMax) * 100}%` } }),
      meterFill),
    h('span', { class: 'cap' }, `권장 ${rMin}–${rMax}초`));
  const hint = h('span', {}, '한 번에 ', h('strong', {}, `${rMin}–${rMax}초`), ' 정도 말해 보세요');
  const left = h('div', { class: 'left' }, hint, meter);

  let right;
  if (task === 'delayed') {
    right = h('div', { class: 'right' },
      h('div', { class: 'delayed-note' }, icon('message', 16), h('span', {}, '피드백은 대화가 끝난 뒤', h('br'), '한 번에 보여드려요')));
  } else {
    const toggle = createModeToggle(mode, onModeChange);
    right = h('div', { class: 'right' }, h('span', { class: 'cap' }, '피드백 표시'), toggle.el);
  }

  let typedRow = null;
  let typedInput = null;
  if (allowTyping) {
    typedInput = h('input', { class: 'input', placeholder: canSpeak ? '직접 입력 (테스트용)' : '음성 인식을 쓸 수 없어 직접 입력해요 (영어)', 'aria-label': '직접 입력' });
    const sendBtn = h('button', { type: 'button', class: 'btn btn-outline', onclick: sendTyped }, '보내기');
    typedInput.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.isComposing) sendTyped(); });
    typedRow = h('div', { class: 'typed-row' }, typedInput, sendBtn);
  }

  const footer = h('footer', { class: 'chat-footer' }, left, mic.el, right, typedRow);
  main.append(h('div', { class: 'chat' }, header, banner, scroller, footer));

  // ── 도우미 ──
  function scrollDown() {
    requestAnimationFrame(() => { scroller.scrollTop = scroller.scrollHeight; });
  }

  function setMic(kind) {
    const map = {
      idle: ['idle', '눌러서 말하기'],
      rec: ['rec', '녹음 중 · 눌러서 발화 마무리하기'],
      sending: ['busy', whisper ? '말한 내용을 받아 적고 있어요' : 'AI가 답을 준비하고 있어요'],
      ai: ['busy', 'AI가 말을 마치면 말할 수 있어요'],
      loading: ['busy', '대화를 준비하고 있어요'],
      ended: ['busy', '세션이 종료됐어요'],
      nospeech: ['busy', 'Chrome에서만 음성으로 말할 수 있어요'],
    };
    const [k, text] = kind === 'idle' && !canSpeak ? map.nospeech : map[kind];
    mic.set(k, text);
    if (typedInput) typedInput.disabled = kind !== 'idle';
  }

  function cardTitle() { return task === 'ai' ? 'AI가 피드백을 건넸어요' : '피드백'; }

  function drawCard(id) {
    const e = entries.get(id);
    if (!e || !e.fb) return;
    const card = feedbackCard(e.fb, e.text, mode, { title: cardTitle(), meta: e.meta });
    e.slot.replaceChildren(card);
    return card;
  }

  function showFeedback(id, fb, meta = '') {
    const e = entries.get(id);
    if (!e) return;
    e.fb = fb;
    e.meta = meta;
    const card = drawCard(id);
    card?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    logEvent('feedback_displayed', { turn_id: id, mode });
  }

  function addAi(turn) {
    const view = aiMessage(turn, { onReplay: replay });
    aiViews.set(turn.id, view);
    list.append(view.el);
    scrollDown();
  }

  // 테스트 모드(?test=true): 내 발화 아래에 L1·L2·시급성 점수와 피드백 필요 여부 표시 (User Trigger 는 요청한 뒤)
  const scoreBoxes = new Map();
  function addScores(id) {
    const e = entries.get(id);
    if (!testMode || !e) return;
    let box = scoreBoxes.get(id);
    if (!box) {
      box = h('div', { class: 'test-scores' });
      e.bubble.after(box);
      scoreBoxes.set(id, box);
    }
    box.textContent = '점수 계산 중…';
    api.feedbackScores(task, id).then((r) => {
      if (r.status === 'not_requested') { box.textContent = 'TEST · 피드백을 요청하면 점수가 나와요'; return; }
      if (!r.scores) { box.textContent = `점수 없음 (${r.status || '오류'})`; return; }
      const sc = r.scores;
      box.replaceChildren(
        h('span', { class: 'th' }, `TEST · ${r.has_issue ? '피드백 있음' : '피드백 없음'} (점수는 기록용)`),
        h('span', { class: 'row' }, h('span', {}, `L1 의미 ${sc.l1 ?? '—'}`), h('span', {}, `L2 자연스러움 ${sc.l2 ?? '—'}`), h('span', {}, `시급성 ${sc.urgency ?? '—'}`)));
    }).catch((err) => { box.textContent = `점수를 불러오지 못했어요 · ${err.message}`; });
  }

  // 내 녹음 다시 듣기 (녹음·AI 발화 중에는 막음)
  async function onPlayClip(url) {
    if (recording || busy) { toast('지금은 들을 수 없어요. 잠시 후 다시 눌러 주세요.'); return; }
    logEvent('recording_play', { url });
    const r = await playClip(url);
    logEvent('recording_play_end', { url, result: r });
  }

  function addUser(turn, { watch = true } = {}) {
    const view = userMessage(turn, { onPlay: onPlayClip });
    list.append(view.el);
    entries.set(turn.id, { slot: view.slot, bubble: view.bubble, text: turn.text, fb: null, meta: '' });
    addScores(turn.id);
    if (turn.shown && turn.feedback) {
      const e = entries.get(turn.id);
      e.fb = turn.feedback;
      e.meta = task === 'user' ? `${fmtClock(turn.shown_at)}에 요청` : '';
      drawCard(turn.id);
    } else if (task === 'user') {
      addRequestButton(turn.id);
    } else if (task === 'ai' && watch && turn.feedback_status !== 'error' && !turn.intervention) {
      watchAi(turn.id);
    }
    scrollDown();
  }

  function addRequestButton(id) {
    const e = entries.get(id);
    const btn = h('button', { type: 'button', class: 'btn btn-sm btn-accent-outline' }, icon('message', 15), '피드백 보기');
    btn.addEventListener('click', async () => {
      // 누르는 순간 피드백을 만들기 시작한다. 만드는 동안에도 대화는 그대로 이어진다.
      const requestedAt = new Date().toISOString();
      logEvent('feedback_request_click', { turn_id: id, mode });
      e.slot.replaceChildren(loadingCard('피드백을 만들고 있어요…'));
      try {
        const r = await api.requestFeedback(task, id);
        if (!alive) return;
        if (r.status === 'ready' && r.feedback) {
          showFeedback(id, r.feedback, `${fmtClock(requestedAt)}에 요청`);
          addScores(id);
        } else {
          throw new Error('피드백을 만들지 못했어요. 잠시 후 다시 눌러 주세요.');
        }
      } catch (err) {
        if (!alive) return;
        toast(err.message);
        e.slot.replaceChildren(btn);
      }
    });
    e.slot.replaceChildren(btn);
  }

  async function watchAi(id) {
    try {
      const r = await api.awaitFeedback(task, id);
      if (alive && r.show && r.feedback) showFeedback(id, r.feedback);
    } catch { /* 피드백이 없어도 대화는 계속 */ }
  }

  async function playAi(turn) {
    const view = aiViews.get(turn.id);
    busy = true;
    setMic('ai');
    view?.setSpeaking(true);
    logEvent('tts_start', { turn_id: turn.id, audio: !!turn.audio_url });
    const via = await speak(turn.text, turn.audio_url);
    logEvent('tts_end', { turn_id: turn.id, via });
    view?.setSpeaking(false);
    busy = false;
    if (alive && !ended && !recording) setMic('idle');
  }

  function replay(turn) {
    if (recording || busy || ended) return;
    logEvent('tts_replay', { turn_id: turn.id });
    playAi(turn);
  }

  function onModeChange(m) {
    mode = m;
    state.modes[task] = m;
    save();
    api.setMode(task, m).catch(() => {});
    for (const id of entries.keys()) drawCard(id);
  }

  // ── 녹음 ──
  let starting = false;
  function onMic() {
    if (ended || starting) return;
    if (!recording) { starting = true; startRec().finally(() => { starting = false; }); }
    else stopRec();
  }

  async function startRec() {
    if (busy || !canSpeak || recording) return;
    stopAudio();
    recording = true; // 녹음 준비 중 두 번 눌리지 않게
    // 1) 녹음 시작 (버튼을 누른 순간부터 저장)
    recordingOn = false;
    if (recorder) {
      try { await recorder.start(); recordingOn = true; } catch (err) {
        logEvent('recording_error', { message: String(err?.message || err) });
        if (whisper) { toast('마이크로 녹음할 수 없어요. 마이크 권한을 확인해 주세요.'); recording = false; return; }
      }
    }
    // 2) 실시간 전사 (browser: 실제 전사 / whisper: 미리보기)
    live = liveMessage({ label: whisper ? '녹음 중 · 미리보기' : '듣고 있어요' });
    list.append(live.el);
    scrollDown();
    stt = null;
    if (browserStt) {
      stt = new SpeechInput({
        lang: S.stt_lang || 'en-US',
        onUpdate: (u) => { live?.update(u); scrollDown(); },
        onError: (msg) => { toast(msg); logEvent('stt_error', { message: msg }); },
      });
      try {
        stt.start();
      } catch (err) {
        stt = null;
        if (!whisper) {
          toast(err.message);
          recorder?.abort();
          live.el.remove();
          live = null;
          recording = false;
          return;
        }
      }
    }
    if (!stt) live.update({ finals: '', interim: '말하는 중… (버튼을 다시 누르면 받아 적어요)' });
    recStart = performance.now();
    hint.hidden = true;
    meter.hidden = false;
    updateMeter();
    recTick = setInterval(updateMeter, 250);
    setMic('rec');
    logEvent('mic_start', { recording: recordingOn, stt: whisper ? 'whisper' : 'browser' });
  }

  function updateMeter() {
    const sec = (performance.now() - recStart) / 1000;
    meterVal.textContent = `${Math.floor(sec)}초`;
    meterFill.style.width = `${Math.min(100, (sec / barMax) * 100)}%`;
  }

  function resetMeter() {
    clearInterval(recTick);
    meter.hidden = true;
    hint.hidden = false;
  }

  async function stopRec() {
    recording = false;
    resetMeter();
    setMic('sending');
    const duration = (performance.now() - recStart) / 1000;
    const [text, blob] = await Promise.all([stt ? stt.stop() : Promise.resolve(''), recorder && recordingOn ? recorder.stop() : Promise.resolve(null)]);
    recordingOn = false;
    live?.el.remove();
    live = null;
    logEvent('mic_stop', { duration_s: Math.round(duration * 10) / 10, chars: text.length, audio_bytes: blob?.size || 0 });
    if (!text && !blob) {
      toast('말소리가 인식되지 않았어요. 다시 말해 주세요.');
      setMic('idle');
      return;
    }
    await sendUtterance({ text, duration, input: 'speech', audio: blob });
  }

  function sendTyped() {
    const text = typedInput.value.trim();
    if (!text || busy || recording || ended) return;
    typedInput.value = '';
    sendUtterance({ text, duration: null, input: 'typed', audio: null });
  }

  const wait = (sec) => new Promise((r) => setTimeout(r, Math.max(0, sec) * 1000));

  // 하단의 작은 상태 문구 (예: AI Decision 의 '피드백 생성 중…')
  function bottomStatus(text) {
    const el = h('div', { class: 'chat-status', role: 'status' }, h('span', { class: 'dot', 'aria-hidden': 'true' }), text);
    list.append(el);
    scrollDown();
    return el;
  }

  async function sendUtterance({ text, duration, input, audio }) {
    busy = true;
    setMic('sending');
    const temp = userMessage({ id: null, text: text || ' ', ts: new Date().toISOString() }, { pending: true });
    // 전사 방식에 따라 보내는 동안 보여줄 작은 안내
    if (input === 'speech' && whisper) temp.slot.replaceChildren(h('span', { class: 'stt-note' }, '받아 적는 중…'));
    else if (input === 'speech' && sttConf.cleanup) temp.slot.replaceChildren(h('span', { class: 'stt-note' }, '전사 다듬는 중…'));
    list.append(temp.el);
    // AI Decision 은 피드백이 먼저 나오므로, 하단에 작게 '피드백 생성 중…'
    const status = task === 'ai' ? bottomStatus('피드백 생성 중…') : null;
    scrollDown();
    let r;
    try {
      r = await api.sendTurn(task, { text, duration_s: duration, input, audio });
    } catch (err) {
      status?.remove();
      busy = false;
      if (err.status === 422) {
        temp.el.remove();
        toast(err.message);
      } else {
        temp.slot.replaceChildren(h('span', { class: 'send-error' }, `보내지 못했어요 · ${err.message}`));
      }
      if (alive && !ended) setMic('idle');
      return;
    }
    if (!alive) return;
    temp.el.remove();
    status?.remove();
    addUser(r.user_turn, { watch: false });
    const shownAt = performance.now();
    const replyP = api.getReply(task, r.user_turn.id); // 대화 상대의 답 (서버에서 이미 만드는 중)

    if (task === 'ai') {
      const d = r.ai_decision || {};
      if (d.ready && d.show && d.feedback) {
        showFeedback(r.user_turn.id, d.feedback);
        await wait(delays.ai_after_feedback ?? 1.0);
      } else if (!d.ready) {
        watchAi(r.user_turn.id); // 피드백이 늦으면 대화는 먼저 이어가고, 준비되면 보여준다
      }
    }
    await deliverReply(replyP, task === 'user' ? (delays.user ?? 0) - (performance.now() - shownAt) / 1000 : 0);
  }

  // 대화 상대의 답을 받아 보여주고 읽는다 (minWait 초만큼은 기다렸다가)
  async function deliverReply(replyP, minWait = 0) {
    if (!alive) return;
    const typing = typingMessage();
    list.append(typing);
    scrollDown();
    try {
      const [rr] = await Promise.all([replyP, wait(minWait)]);
      typing.remove();
      if (!alive || ended) return;
      addAi(rr.ai_turn);
      await playAi(rr.ai_turn);
    } catch (err) {
      typing.remove();
      busy = false;
      if (!alive || ended) return;
      toast(`대화 상대의 답을 받지 못했어요 · ${err.message}`);
      setMic('idle');
    }
  }

  // ── 종료 ──
  async function endSession() {
    if (ended) return;
    const elapsed = timer.elapsed();
    if (elapsed < limit && !window.confirm(`아직 ${Math.round(limit / 60)}분이 지나지 않았어요. 세션을 종료할까요?`)) return;
    if (recording) {
      stt?.abort();
      recorder?.abort();
      recordingOn = false;
      recording = false;
      resetMeter();
      live?.el.remove();
      logEvent('mic_discarded_on_end');
    }
    ended = true;
    stopAudio();
    timer.stop();
    setMic('ended');
    endBtn.disabled = true;
    logEvent('session_end_click', { elapsed_s: Math.round(elapsed), overtime: timer.isOver() });
    const close = overlay(task === 'delayed' ? '피드백을 모아서 정리하고 있어요…' : '대화를 저장하고 있어요…');
    try {
      await api.endSession(task, Math.round(elapsed));
      close();
      ctx.next();
    } catch (err) {
      close();
      toast(err.message);
      ended = false;
      endBtn.disabled = false;
      timer.start(sessionStartMs);
      setMic('idle');
    }
  }

  // ── 시작 ──
  async function init() {
    setMic('loading');
    try {
      const s = await api.startSession(task, mode);
      if (!alive) return;
      if (s.ended_at) { ctx.next(); return; }
      sessionStartMs = Date.parse(s.started_at) || Date.now();
      timer.start(sessionStartMs);
      recorder?.open().catch(() => {}); // 첫 녹음이 바로 시작되도록 마이크를 미리 연다
      for (const t of s.turns) (t.role === 'ai' ? addAi(t) : addUser(t));
      const last = s.turns[s.turns.length - 1];
      if (s.turns.length === 1 && last?.role === 'ai') await playAi(last);
      else if (last?.role === 'user') {
        // 내 말을 보낸 직후 새로고침된 경우: 대화 상대의 답을 마저 받는다
        busy = true;
        setMic('sending');
        await deliverReply(api.getReply(task, last.id));
      } else setMic('idle');
    } catch (err) {
      list.replaceChildren(h('div', { class: 'error-box', role: 'alert' },
        h('span', {}, err.message),
        h('button', { type: 'button', class: 'btn btn-outline btn-sm', onclick: () => { list.replaceChildren(); init(); } }, '다시 시도')));
    }
  }
  init();

  return () => {
    alive = false;
    stt?.abort();
    recorder?.close();
    stopAudio();
    timer.stop();
    clearInterval(recTick);
  };
}
