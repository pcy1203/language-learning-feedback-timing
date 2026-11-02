// 브라우저 내장 음성 인식 (Web Speech API, Chrome 권장).
// 말하는 동안 실시간 전사(onUpdate)를 주고, stop() 하면 최종 문장을 돌려준다.
// Chrome 은 조용하면 인식을 스스로 끝내므로, 녹음 중이면 자동으로 다시 시작한다.
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;

export function sttSupported() {
  return !!SR;
}

export class SpeechInput {
  constructor({ lang = 'en-US', onUpdate = () => {}, onError = () => {} } = {}) {
    this.lang = lang;
    this.onUpdate = onUpdate;
    this.onError = onError;
    this.active = false;
    this.rec = null;
    this.finals = '';
    this.interim = '';
    this._stopResolve = null;
  }

  start() {
    if (!SR) throw new Error('이 브라우저는 음성 인식을 지원하지 않아요. Chrome을 사용해 주세요.');
    this.finals = '';
    this.interim = '';
    this.active = true;
    this._begin();
  }

  _begin() {
    const rec = new SR();
    rec.lang = this.lang;
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    rec.onresult = (e) => {
      let interim = '';
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const text = e.results[i][0].transcript;
        if (e.results[i].isFinal) this.finals += text.trim() + ' ';
        else interim += text;
      }
      this.interim = interim;
      this.onUpdate({ finals: this.finals.trim(), interim: this.interim.trim() });
    };
    rec.onerror = (e) => {
      if (e.error === 'no-speech' || e.error === 'aborted') return;
      if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
        this.active = false;
        this.onError('마이크 사용이 허용되지 않았어요. 주소창의 마이크 권한을 확인해 주세요.');
      } else if (e.error === 'network') {
        this.onError('음성 인식 서버에 연결하지 못했어요. 인터넷 연결을 확인해 주세요.');
      }
    };
    rec.onend = () => {
      // 아직 끝난 게 아니면(침묵 등으로 끊긴 경우) 이어서 다시 듣는다
      if (this.active) {
        if (this.interim) { this.finals += this.interim.trim() + ' '; this.interim = ''; }
        try { this._begin(); } catch { /* 무시 */ }
        return;
      }
      this._finish();
    };
    this.rec = rec;
    rec.start();
  }

  _finish() {
    if (this._stopResolve) {
      const text = `${this.finals} ${this.interim}`.replace(/\s+/g, ' ').trim();
      const resolve = this._stopResolve;
      this._stopResolve = null;
      resolve(text);
    }
  }

  stop() {
    this.active = false;
    return new Promise((resolve) => {
      this._stopResolve = resolve;
      try { this.rec?.stop(); } catch { this._finish(); }
      // onend 가 오지 않는 경우를 대비
      setTimeout(() => this._finish(), 1500);
    });
  }

  abort() {
    this.active = false;
    this._stopResolve = null;
    try { this.rec?.abort(); } catch { /* 무시 */ }
  }
}
