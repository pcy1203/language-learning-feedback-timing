// AI 발화 재생: Gemini Live 가 만든 음성 파일(audio_url)이 있으면 그걸 재생하고,
// 없거나 재생에 실패하면 브라우저 내장 음성(speechSynthesis)으로 읽는다.
let current = null; // { audio, resolve }

export function stopAudio() {
  if (current) {
    try { current.audio.pause(); } catch { /* 무시 */ }
    const r = current.resolve;
    current = null;
    r?.('stopped');
  }
  try { window.speechSynthesis?.cancel(); } catch { /* 무시 */ }
}

function speakBrowser(text) {
  return new Promise((resolve) => {
    const synth = window.speechSynthesis;
    if (!synth) { resolve('none'); return; }
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'en-US';
    u.rate = 0.95;
    const voice = synth.getVoices().find((v) => v.lang === 'en-US' && /Google|Samantha|Natural/i.test(v.name))
      || synth.getVoices().find((v) => v.lang?.startsWith('en'));
    if (voice) u.voice = voice;
    let settled = false;
    const finish = (how) => { if (!settled) { settled = true; clearTimeout(guard); resolve(how); } };
    // 일부 환경에서 onend 가 오지 않는 경우가 있어, 예상 길이가 지나면 끝난 것으로 본다
    const guard = setTimeout(() => finish('browser-timeout'), Math.min(30000, 2500 + text.split(/\s+/).length * 450));
    u.onend = () => finish('browser');
    u.onerror = () => finish('browser-error');
    synth.speak(u);
  });
}

function playFile(url) {
  return new Promise((resolve) => {
    const audio = new Audio(url);
    current = { audio, resolve, url };
    audio.onended = () => { current = null; resolve('live'); };
    audio.onerror = () => { current = null; resolve(null); };
    audio.play().catch(() => { current = null; resolve(null); });
  });
}

export async function speak(text, audioUrl) {
  stopAudio();
  if (audioUrl) {
    const via = await playFile(audioUrl);
    if (via) return via;
  }
  return speakBrowser(text);
}

// 내 녹음 다시 듣기. 같은 파일을 재생 중에 다시 누르면 멈춘다.
// 반환: 'ended' | 'stopped' | 'error'
export async function playClip(url) {
  if (current?.url === url) { stopAudio(); return 'stopped'; }
  stopAudio();
  const via = await playFile(url);
  return via === 'live' ? 'ended' : via === 'stopped' ? 'stopped' : 'error';
}

export function isPlaying(url) {
  return current?.url === url;
}
