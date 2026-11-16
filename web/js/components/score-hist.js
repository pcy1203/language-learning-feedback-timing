// 발화별 점수(1~10) 막대그래프. 묶음(series)이 둘 이상이면 점수마다 막대를 나란히 놓는다.
// 대시보드와 관리자 로그 화면에서 같이 쓴다.
import { h } from '../lib/dom.js';

// 세 점수 모두 10에 가까울수록 피드백이 필요한 쪽
export const SCORE_LABEL = { l1: 'L1 의미 미전달', l2: 'L2 부자연스러움', urgency: '시급성' };
export const SERIES_COLORS = ['#003458', '#D9A441', '#8FA7BC'];

const meanOf = (counts) => {
  const n = counts.reduce((a, b) => a + b, 0);
  return n ? counts.reduce((a, c, i) => a + c * (i + 1), 0) / n : null;
};

export function scoreLegend(series) {
  return h('div', { class: 'sh-legend' }, series.map((s, j) => h('span', {},
    h('i', { style: { background: s.color || SERIES_COLORS[j] } }), s.label,
    h('small', {}, `${s.counts ? s.counts.reduce((a, b) => a + b, 0) : s.n ?? 0}발화`))));
}

// series: [{ label, counts: [10], color? }]
export function scoreHist({ title, series, height = 110, compact = false }) {
  const max = Math.max(1, ...series.flatMap((s) => s.counts));
  const cols = Array.from({ length: 10 }, (_, i) => h('div', { class: 'sh-col' },
    series.map((s, j) => h('span', {
      class: 'sh-bar',
      style: { height: `${(s.counts[i] / max) * 100}%`, background: s.color || SERIES_COLORS[j] },
      title: `${s.label} · ${i + 1}점: ${s.counts[i]}발화`,
    }))));
  const axis = Array.from({ length: 10 }, (_, i) => h('span', {}, String(i + 1)));
  const means = series.map((s, j) => {
    const m = meanOf(s.counts);
    return h('span', { class: 'sh-mean' },
      series.length > 1 ? h('i', { style: { background: s.color || SERIES_COLORS[j] } }) : null,
      m == null ? '—' : `평균 ${m.toFixed(1)}`);
  });
  return h('div', { class: `sh${compact ? ' sh-compact' : ''}` },
    h('div', { class: 'sh-head' }, h('b', {}, title), h('span', { class: 'sh-means' }, means)),
    h('div', { class: 'sh-plot', style: { height: `${height}px` } }, cols),
    h('div', { class: 'sh-axis', 'aria-hidden': 'true' }, axis));
}

// 관리자 로그용: 한 세션의 발화를 조건별 묶음으로 나눠 점수 분포를 만든다 (서버 dashboard.score_group 과 같은 기준)
export const SCORE_GROUPS = {
  user: [['requested', '피드백 보기를 누른 발화'], ['not_requested', '누르지 않은 발화']],
  ai: [['shown', '피드백이 제시된 발화'], ['not_shown', '제시되지 않은 발화']],
  delayed: [['all', '전체 발화']],
};

export function groupOf(task, t) {
  if (task === 'user') return t.requested || t.shown_via === 'request' ? 'requested' : 'not_requested';
  if (task === 'ai') return t.shown ? 'shown' : 'not_shown';
  return 'all';
}

export function sessionScoreSeries(task, turns) {
  const groups = SCORE_GROUPS[task] || [['all', '전체 발화']];
  const out = Object.fromEntries(groups.map(([g]) => [g, { l1: Array(10).fill(0), l2: Array(10).fill(0), urgency: Array(10).fill(0) }]));
  for (const t of turns) {
    if (t.role !== 'user') continue;
    const sc = t.feedback?.scores || {};
    const g = out[groupOf(task, t)];
    for (const k of ['l1', 'l2', 'urgency']) if (Number.isInteger(sc[k]) && sc[k] >= 1 && sc[k] <= 10) g[k][sc[k] - 1] += 1;
  }
  return (k) => groups.map(([g, label]) => ({ label, counts: out[g][k] }));
}
