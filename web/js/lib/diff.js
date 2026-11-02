// 원래 문장과 고친 문장을 단어 단위로 비교해, 고친 문장에서 바뀐 부분을 표시한다.
const norm = (w) => w.toLowerCase().replace(/[^\p{L}\p{N}']/gu, '').replace(/’/g, "'");

export function diffSegments(original = '', revised = '') {
  const a = original.split(/\s+/).filter(Boolean).map(norm);
  const bRaw = revised.split(/\s+/).filter(Boolean);
  const b = bRaw.map(norm);
  const n = a.length, m = b.length;
  // LCS 테이블
  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] && a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const same = new Array(m).fill(false);
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] && a[i] === b[j]) { same[j] = true; i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) i++;
    else j++;
  }
  // 연속된 같은 상태끼리 묶기
  const segs = [];
  bRaw.forEach((word, k) => {
    const changed = !same[k] && b[k] !== '';
    const last = segs[segs.length - 1];
    if (last && last.changed === changed) last.text += ' ' + word;
    else segs.push({ text: (segs.length ? ' ' : '') + word, changed, lead: segs.length > 0 });
  });
  return segs;
}

// 강조 구간을 <mark>로 감싼 노드 배열을 돌려준다
export function highlighted(original, revised, { muted = false } = {}) {
  const out = [];
  for (const s of diffSegments(original, revised)) {
    if (!s.changed) { out.push(document.createTextNode(s.text)); continue; }
    const text = s.text.replace(/^ /, '');
    if (s.text.startsWith(' ')) out.push(document.createTextNode(' '));
    const mark = document.createElement('mark');
    mark.className = muted ? 'hl muted' : 'hl';
    mark.textContent = text;
    out.push(mark);
  }
  return out;
}
