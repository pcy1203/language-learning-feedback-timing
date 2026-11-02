// Admin 대시보드: 조건(User Trigger / AI Decision / Delayed) 비교, 세션 설문 평균, Annotation 선택 비율, AI 개입 판단
import { api, adminUrl } from '../api.js';
import { h, icon, clear } from '../lib/dom.js';

const ZONE_LABEL = {
  warmup: '초반 (이력 부족)',
  on_target: '목표 비율 근처',
  too_many: '개입 많음 → 엄격',
  too_few: '개입 적음 → 완화',
};

const pct = (x) => (x == null ? '—' : `${Math.round(x * 100)}%`);
const num = (x, d = 1) => (x == null ? '—' : Number(x).toFixed(d).replace(/\.0+$/, ''));
const mmss = (s) => (s == null ? '—' : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`);

// ── 호버 툴팁 (모든 차트 공용) ──
let tipEl = null;
function attachTip(el, text) {
  el.setAttribute('tabindex', '0');
  el.setAttribute('aria-label', text.replace(/\n/g, ', '));
  const show = (x, y) => {
    if (!tipEl) { tipEl = h('div', { class: 'chart-tip', role: 'tooltip' }); document.body.append(tipEl); }
    tipEl.textContent = text;
    tipEl.hidden = false;
    const r = tipEl.getBoundingClientRect();
    tipEl.style.left = `${Math.min(window.innerWidth - r.width - 8, x + 12)}px`;
    tipEl.style.top = `${Math.max(8, y - r.height - 10)}px`;
  };
  const hide = () => { if (tipEl) tipEl.hidden = true; };
  el.addEventListener('mousemove', (e) => show(e.clientX, e.clientY));
  el.addEventListener('mouseleave', hide);
  el.addEventListener('focus', () => { const r = el.getBoundingClientRect(); show(r.left + r.width / 2, r.top); });
  el.addEventListener('blur', hide);
}

export function renderDashboard(container, { onError }) {
  let onlyFinished = false;
  const body = h('div', { class: 'dash' });
  container.append(body);
  load();

  async function load() {
    clear(body).append(h('p', { class: 'empty' }, '불러오는 중…'));
    try {
      const d = await api.admin.dashboard(onlyFinished);
      draw(d);
    } catch (err) {
      clear(body).append(h('p', { class: 'empty' }, err.message));
      onError(err);
    }
  }

  function draw(d) {
    const conds = d.conditions;
    const totalTurns = conds.reduce((a, c) => a + c.user_turns, 0);

    const finishedBox = h('input', { type: 'checkbox', checked: onlyFinished });
    finishedBox.addEventListener('change', () => { onlyFinished = finishedBox.checked; load(); });

    const bar = h('div', { class: 'dash-bar' },
      h('div', { class: 'field', style: { gap: '4px' } },
        h('h1', {}, '대시보드'),
        h('span', { style: { fontSize: '13px', color: 'var(--muted)' } }, `data/ 폴더의 기록으로 계산했어요 · 참가자 ${d.included}명 포함 (시작 전 코드는 제외)`)),
      h('div', { class: 'controls' },
        h('label', {}, finishedBox, '완료한 참가자만'),
        h('button', { type: 'button', class: 'btn btn-outline btn-sm', onclick: load }, icon('refresh', 14), '새로고침'),
        h('a', { class: 'btn btn-outline btn-sm', href: adminUrl(`/api/admin/export-dashboard.csv?only_finished=${onlyFinished}`), download: '' }, icon('download', 14), '요약 CSV')));

    const kpis = h('div', { class: 'kpis' }, [
      ['등록된 참가자', d.participants.total],
      ['완료', d.participants.done],
      ['진행 중', d.participants.progress],
      ['시작 전', d.participants.new],
      ['집계한 발화', totalTurns],
    ].map(([k, v]) => h('div', { class: 'stat' }, h('span', {}, k), h('b', {}, String(v)))));

    if (!d.included) {
      clear(body).append(bar, kpis, h('div', { class: 'table-wrap' }, h('p', { class: 'empty' }, '아직 집계할 기록이 없어요. 참가자가 세션을 시작하면 여기에 쌓여요.')));
      return;
    }

    clear(body).append(bar, kpis, compareSection(conds), likertSection(d.likert, conds), annotationSection(d.annotation, conds), interventionSection(conds.find((c) => c.key === 'ai')));
  }

  // ── 조건 비교 표 ──
  function compareSection(conds) {
    const row = (label, fn, opts = {}) => h('tr', {}, h('td', {}, label), conds.map((c) => {
      const v = fn(c);
      return h('td', { class: v === '—' || v == null ? 'na' : '' }, v ?? '—');
    }));
    const group = (label) => h('tr', { class: 'group' }, h('td', { colspan: String(conds.length + 1) }, label));
    const only = (key, fn) => (c) => (c.key === key ? fn(c) : '—');
    const withN = (main, n) => h('span', {}, main, h('small', {}, n));

    return h('section', { class: 'dash-section', 'aria-labelledby': 'cmp-h' },
      h('h2', { id: 'cmp-h' }, '조건 비교'),
      h('p', { class: 'note' }, '평균은 세션(또는 발화) 단위예요. 비율 옆 괄호는 분모가 되는 개수예요.'),
      h('div', { class: 'table-wrap' }, h('table', { class: 'cmp-table' },
        h('thead', {}, h('tr', {}, h('th', { scope: 'col' }, '지표'),
          conds.map((c) => h('th', { scope: 'col' }, c.name, h('span', {}, c.summary))))),
        h('tbody', {},
          group('진행'),
          row('세션 (종료 / 시작)', (c) => `${c.ended} / ${c.sessions}`),
          row('진행 순서 (1·2·3번째)', (c) => c.order_counts.join(' · ')),
          row('평균 세션 시간', (c) => mmss(c.avg_elapsed_s)),
          row('세션당 발화 수', (c) => num(c.avg_user_turns)),
          row('평균 발화 길이', (c) => (c.avg_duration_s == null ? '—' : `${num(c.avg_duration_s)}초`)),
          group('피드백'),
          row('고칠 부분이 있던 발화', (c) => withN(pct(c.issue_rate), `(${c.user_turns})`)),
          row('평균 심각도 (0–3)', (c) => num(c.avg_severity, 2)),
          row('대화 중 피드백을 본 비율', (c) => (c.key === 'delayed' ? '종료 후 일괄' : withN(pct(c.shown_live_rate), `(${c.issue_turns})`))),
          row('자세한 피드백으로 시작', (c) => pct(c.detailed_start_rate)),
          row('세션당 방식 전환 횟수', (c) => (c.key === 'delayed' ? '—' : num(c.avg_mode_toggles))),
          group('조건별 지표'),
          row('피드백 보기를 누른 발화', only('user', (c) => withN(pct(c.request_rate), `(${c.user_turns})`))),
          row('세션당 피드백 요청 수', only('user', (c) => num(c.avg_requests_per_session))),
          row('요청한 발화 중 고칠 부분 있음', only('user', (c) => withN(pct(c.requested_with_issue_rate), `(${c.requested_turns})`))),
          row('AI가 피드백을 보여준 발화', only('ai', (c) => withN(pct(c.intervention?.show_rate_all_turns), `(${c.user_turns})`))),
          row('개입 판정 점수 평균 (0–100)', only('ai', (c) => num(c.intervention?.avg_score)))))));
  }

  // ── 세션 설문: 문항별, 조건별 평균 (점 그래프, 1~5 눈금) ──
  function likertSection(lk, conds) {
    const scale = lk.scale;
    const pos = (v) => `${((v - 1) / (scale - 1)) * 100}%`;
    const cards = lk.items.map((it) => {
      const rows = conds.map((c) => {
        const st = lk.by_condition[c.key]?.[it.key] || { n: 0, mean: null, dist: [] };
        const track = h('div', { class: 'dot-track' },
          Array.from({ length: scale }, (_, i) => h('span', { class: 'tick', style: { left: pos(i + 1) } })),
          st.mean != null ? h('span', { class: 'dot', style: { left: pos(st.mean) } }) : null);
        const dist = st.dist.map((n, i) => `${i + 1}점 ${n}명`).join(' · ');
        attachTip(track, `${c.name}\n평균 ${num(st.mean, 2)}${st.sd != null ? ` (SD ${num(st.sd, 2)})` : ''} · 응답 ${st.n}명\n${dist}`);
        return h('div', { class: 'dot-row' },
          h('span', { class: 'name' }, c.name),
          track,
          h('span', { class: 'val' }, num(st.mean, 2), h('small', {}, `n=${st.n}`)));
      });
      return h('div', { class: 'chart-card' },
        h('h3', {}, it.text),
        rows,
        h('div', { class: 'dot-axis', 'aria-hidden': 'true' }, h('span'), h('span', { class: 'ends' }, h('span', {}, `1 ${lk.low_label}`), h('span', {}, `${scale} ${lk.high_label}`)), h('span')));
    });
    return h('section', { class: 'dash-section', 'aria-labelledby': 'lk-h' },
      h('h2', { id: 'lk-h' }, '세션 설문 평균'),
      h('p', { class: 'note' }, '점은 평균이에요. 점 위에 마우스를 올리면 점수별 응답 수가 보여요.'),
      h('div', { class: 'likert-grid' }, cards));
  }

  // ── Annotation: 조건 · 피드백 상태 · 질문별 선택 비율 ──
  function ratioBar(q) {
    const total = q.n;
    const bar = h('div', { class: 'ratio-bar' });
    if (!total) bar.append(h('span', { class: 'empty-bar' }));
    else q.counts.forEach((n, i) => { if (n) bar.append(h('span', { class: i === 0 ? 'a' : 'b', style: { flex: String(n) } })); });
    attachTip(bar, q.options.map((o, i) => `${o}: ${q.counts[i]}명 (${total ? Math.round((q.counts[i] / total) * 100) : 0}%)`).join('\n'));
    const p = (i) => (total ? `${Math.round((q.counts[i] / total) * 100)}%` : '—');
    return h('div', { class: 'ratio' },
      h('div', { class: 'q' }, h('span', {}, q.label), h('small', {}, `n=${total}`)),
      bar,
      h('div', { class: 'labels' },
        h('span', {}, h('b', {}, q.options[0]), ` ${p(0)}`),
        h('span', {}, `${q.options[1]} `, h('b', {}, p(1)))));
  }

  function annotationSection(ann, conds) {
    const cards = conds.map((c) => h('div', { class: 'chart-card' },
      h('h3', {}, c.name),
      (ann[c.key] || []).map((g) => h('div', { class: 'ann-group' },
        h('span', { class: 'state' }, h('b', {}, g.state_label), ` · 발화 ${g.n}개`),
        g.questions.map(ratioBar)))));
    return h('section', { class: 'dash-section', 'aria-labelledby': 'ann-h' },
      h('h2', { id: 'ann-h' }, 'Annotation 선택 비율'),
      h('p', { class: 'note' }, '발화의 피드백 상태(봤음 / 못 봤음 / 피드백 없음)별로 나눠 보여줘요. 진한 색이 첫 번째 선택지예요.'),
      h('div', { class: 'ann-cols' }, cards));
  }

  // ── AI Decision 개입 판단 ──
  function interventionSection(ai) {
    if (!ai?.intervention) return null;
    const iv = ai.intervention;
    const zones = Object.entries(ZONE_LABEL).map(([k, label]) => [label, iv.zones[k] || 0]);
    const maxZ = Math.max(1, ...zones.map((z) => z[1]));
    return h('section', { class: 'dash-section', 'aria-labelledby': 'iv-h' },
      h('h2', { id: 'iv-h' }, `${ai.name} 개입 판단`),
      h('p', { class: 'note' }, 'LLM이 점수(0–100)와 보여줄지를 판정하고, 최근 3턴의 노출 비율이 목표(약 2/3)에서 벗어나면 문턱값으로 보정해요.'),
      h('div', { class: 'iv-grid' },
        h('div', { class: 'kpis', style: { gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' } }, [
          ['판정한 발화', iv.judged],
          ['평균 점수', num(iv.avg_score)],
          ['LLM이 보여주자고 함', pct(iv.judge_show_rate)],
          ['최종으로 보여줌', pct(iv.show_rate_judged)],
          ['보정으로 보여줌', iv.overridden_to_show],
          ['보정으로 숨김', iv.overridden_to_hide],
        ].map(([k, v]) => h('div', { class: 'stat' }, h('span', {}, k), h('b', {}, String(v))))),
        h('div', { class: 'chart-card' },
          h('h3', {}, '판정 당시 상황'),
          h('div', { class: 'iv-zones' }, zones.map(([label, n]) => {
            const b = h('span', { class: 'bar', style: { width: `${(n / maxZ) * 100}%` } });
            attachTip(b, `${label}: ${n}번`);
            return h('div', {}, h('span', { class: 'name' }, label), h('span', {}, b), h('span', { class: 'n' }, String(n)));
          })))));
  }
}
