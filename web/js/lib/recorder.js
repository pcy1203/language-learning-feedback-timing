// 학습자 녹음 (MediaRecorder). 마이크 버튼을 누른 순간부터 그만 버튼을 누른 순간까지를 파일 하나로 만든다.
// 마이크 스트림은 대화 화면에 있는 동안 열어 두어, 버튼을 누르자마자 녹음이 시작되게 한다.
const TYPES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];

export function recorderSupported() {
  return !!(window.MediaRecorder && navigator.mediaDevices?.getUserMedia);
}

export class Recorder {
  constructor() {
    this.stream = null;
    this.rec = null;
    this.chunks = [];
    this.mime = TYPES.find((t) => window.MediaRecorder?.isTypeSupported?.(t)) || '';
  }

  async open() {
    if (this.stream || !recorderSupported()) return;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  }

  async start() {
    await this.open();
    if (!this.stream) throw new Error('이 브라우저에서는 녹음할 수 없어요. Chrome을 사용해 주세요.');
    this.chunks = [];
    this.rec = new MediaRecorder(this.stream, this.mime ? { mimeType: this.mime } : undefined);
    this.rec.ondataavailable = (e) => { if (e.data?.size) this.chunks.push(e.data); };
    this.rec.start(250);
  }

  // 녹음을 끝내고 Blob 을 돌려준다 (녹음 중이 아니면 null)
  stop() {
    const rec = this.rec;
    this.rec = null;
    if (!rec || rec.state === 'inactive') return Promise.resolve(null);
    return new Promise((resolve) => {
      rec.onstop = () => {
        const type = rec.mimeType || this.mime || 'audio/webm';
        resolve(this.chunks.length ? new Blob(this.chunks, { type }) : null);
      };
      try { rec.stop(); } catch { resolve(null); }
    });
  }

  abort() {
    const rec = this.rec;
    this.rec = null;
    try { if (rec && rec.state !== 'inactive') rec.stop(); } catch { /* 무시 */ }
    this.chunks = [];
  }

  close() {
    this.abort();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }
}
