// AI 발화 재생: 서버 TTS(OpenAI) → 실패하면 브라우저 내장 음성으로 대체
let current = null; // { audio, url, resolve }

export function stopAudio() {
  if (current) {
    try { current.audio.pause(); } catch { /* 무시 */ }
    URL.revokeObjectURL(current.url);
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

export async function speak(text) {
  stopAudio();
  try {
    const res = await fetch('/api/tts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    if (res.status === 200) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      return await new Promise((resolve) => {
        current = { audio, url, resolve };
        audio.onended = () => { URL.revokeObjectURL(url); current = null; resolve('tts'); };
        audio.onerror = () => { current = null; speakBrowser(text).then(resolve); };
        audio.play().catch(() => { current = null; speakBrowser(text).then(resolve); });
      });
    }
  } catch { /* 아래에서 브라우저 음성으로 */ }
  return speakBrowser(text);
}
