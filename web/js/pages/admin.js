// 관리자: 참가자 코드 생성·삭제 / 대시보드 / 참가자별 로그 조회 / CSV·ZIP 내려받기
// 모든 화면은 서버가 data/ 폴더의 파일을 읽어 보내주는 값으로 그린다.
import { api, adminUrl } from '../api.js';
import { h, icon, clear, fmtClock } from '../lib/dom.js';
import { toast } from '../lib/toast.js';
import { highlighted } from '../lib/diff.js';
import { renderDashboard } from './admin-dashboard.js';
import { apiStatus } from '../components/api-status.js';
import { scoreHist, scoreLegend, sessionScoreSeries, SCORE_LABEL } from '../components/score-hist.js';
import { playButton } from '../components/message-bubble.js';
import { playClip } from '../lib/audio-player.js';

const KIND_LABEL = { turns: '대화·피드백', events: '이벤트', annotations: 'Annotation', survey: '설문' };
const VIA_LABEL = { request: '요청해서 확인', ai: 'AI가 보여줌', summary: '종합 피드백에서 확인' };
const STATE_LABEL = { seen: '봤음', unseen: '못 봤음', checked_no_issue: '요청 · 고칠 부분 없음', no_feedback: '피드백 없음' };
// Annotation 질문: 참가자 화면과 같은 순서 (의도 → 내용 → 시점)
const Q_ORDER = ['intent', 'content', 'seen_help', 'unseen_help', 'need', 'hidden_need', 'realtime', 'should_have'];
const Q_LABEL = { intent: 'AI가 이해한 의도가', content: '피드백 내용이', seen_help: '이 피드백을 본 것은', unseen_help: '이 피드백을 봤다면', need: '이 시점에 피드백이', hidden_need: '이 피드백을 대화 중에', realtime: '대화 중에 바로 받았다면', should_have: '이 발화에 피드백이' };

function feedbackState(task, t) {
  const fb = t.feedback;
  if (!fb) return null;
  if (fb.has_issue) return t.shown ? 'seen' : 'unseen';
  if (task === 'user' && (t.requested || t.shown_via === 'request')) return 'checked_no_issue';
  return 'no_feedback';
}

const PURPOSE_LABEL = { live: '발화 직후 생성', request: '요청 시 생성', annotation: '세션 후 생성 (Annotation용)' };

// 점수 한 칸: 이름 + 1~10 막대 + 숫자
function scoreMeter(label, v) {
  return h('div', { class: 'meter' },
    h('span', { class: 'meter-label' }, label),
    h('span', { class: 'meter-track' }, h('span', { class: 'meter-fill', style: { width: `${((v || 0) / 10) * 100}%` } })),
    h('b', {}, v ?? '—'));
}

// 점수(기록용) · 피드백 필요 판단 · 생성 시점 · 근거
function scoreBox(fb, t) {
  const sc = fb.scores || {};
  const meta = [
    t.feedback_purpose ? PURPOSE_LABEL[t.feedback_purpose] || t.feedback_purpose : null,
    t.feedback_latency_ms ? `생성 ${(t.feedback_latency_ms / 1000).toFixed(1)}초` : null,
  ].filter(Boolean).join(' · ');
  return h('div', { class: 'score-box' },
    h('div', { class: 'score-top' },
      h('span', { class: `need-badge${fb.has_issue ? ' on' : ''}` }, fb.has_issue ? '피드백 있음' : '피드백 없음'),
      meta ? h('span', { class: 'muted' }, meta) : null),
    h('div', { class: 'meters' }, scoreMeter('L1 의미 미전달', sc.l1), scoreMeter('L2 부자연스러움', sc.l2), scoreMeter('시급성', sc.urgency)),
    fb.rationale ? h('p', { class: 'why' }, h('b', {}, 'AI 판단 근거'), fb.rationale) : null,
    fb.likely_concern ? h('p', { class: 'why' }, h('b', {}, '추정한 궁금증'), fb.likely_concern) : null);
}

// Annotation 응답: 상태 + 질문별 답 (의도 → 내용 → 시점 순)
function annotationBox(state, answers) {
  if (!state && !answers.length) return null;
  const rows = [...answers].sort((a, b) => Q_ORDER.indexOf(a.key) - Q_ORDER.indexOf(b.key)).map((a) =>
    h('div', { class: 'ann-row' }, h('span', {}, Q_LABEL[a.key] || a.key), h('b', { class: a.value === 0 ? 'good' : 'bad' }, a.label)));
  return h('div', { class: 'ann-box' },
    h('div', { class: 'ann-box-head' }, h('b', {}, 'Annotation'), state ? h('span', {}, STATE_LABEL[state]) : null),
    rows.length ? rows : h('span', { class: 'muted' }, '응답 없음'));
}

function dlLink(href, label, { primary = false, small = false } = {}) {
  return h('a', { href: adminUrl(href), class: `btn ${primary ? 'btn-primary' : 'btn-outline'} btn-sm`, download: '', style: small ? { height: '30px', fontSize: '12px' } : null },
    icon('download', 14), label);
}

export function render(root, ctx) {
  let tab = 'codes';
  let selected = null;
  let meta = null;
  let codes = [];
  let lastCreated = null;

  const brand = h('span', {}, '관리자');
  const navCodes = h('button', { type: 'button', onclick: () => switchTab('codes') }, '참가자 코드');
  const navDash = h('button', { type: 'button', onclick: () => switchTab('dashboard') }, '대시보드');
  const navLogs = h('button', { type: 'button', onclick: () => switchTab('logs') }, '로그');
  const body = h('div');
  // API 연결 상태 줄: 키 연결 여부 + '연결 확인'(실제로 짧게 호출해 봄)
  const statusSlot = h('div', { class: 'api-status-slot' });
  const checkResult = h('span', { class: 'api-check-result', role: 'status' });
  const checkBtn = h('button', { type: 'button', class: 'btn btn-outline btn-sm' }, icon('refresh', 14), '연결 확인');
  checkBtn.addEventListener('click', async () => {
    checkBtn.disabled = true;
    checkResult.textContent = '두 API에 짧게 호출해 보는 중…';
    try {
      const r = await api.admin.checkApi();
      const fmt = (name, x) => (x.ok === null ? `${name}: 확인 안 함 (${x.detail})` : x.ok ? `${name}: 정상 (${x.ms}ms)` : `${name}: 실패 · ${x.detail}`);
      checkResult.textContent = `${fmt('대화 AI', r.chat)}  ·  ${fmt('피드백', r.feedback)}  ·  ${fmt('전사', r.stt)}`;
      checkResult.className = `api-check-result ${[r.chat.ok, r.feedback.ok, r.stt?.ok].includes(false) ? 'bad' : 'good'}`;
    } catch (err) {
      handleError(err);
      checkResult.textContent = '';
    }
    checkBtn.disabled = false;
  });
  root.append(
    h('header', { class: 'admin-header' },
      h('div', { class: 'admin-left' },
        h('div', { class: 'admin-brand' }, brand, h('span', { class: 'badge-admin' }, 'ADMIN')),
        h('nav', { class: 'admin-nav', 'aria-label': '관리자 메뉴' }, navCodes, navDash, navLogs)),
      h('button', { type: 'button', class: 'btn btn-ghost btn-sm', onclick: () => ctx.logout() }, '나가기')),
    h('div', { class: 'admin-apibar' }, statusSlot, h('div', { class: 'api-check' }, checkResult, checkBtn)),
    body);
  api.publicInfo().then((p) => {
    brand.textContent = p.study_title;
    statusSlot.replaceChildren(apiStatus(p.api));
  }).catch(() => {});

  function handleError(err) {
    if (err.status === 401) {
      toast('관리자 로그인이 필요해요. 다시 로그인해 주세요.');
      ctx.logout();
      return;
    }
    toast(err.message);
  }

  async function loadCodes() {
    try {
      if (!meta) meta = await api.admin.meta();
      codes = await api.admin.codes();
      return true;
    } catch (err) {
      handleError(err);
      return false;
    }
  }

  function switchTab(t, code) {
    tab = t;
    if (code) selected = code;
    draw();
  }

  async function draw() {
    navCodes.setAttribute('aria-current', tab === 'codes' ? 'page' : 'false');
    navDash.setAttribute('aria-current', tab === 'dashboard' ? 'page' : 'false');
    navLogs.setAttribute('aria-current', tab === 'logs' ? 'page' : 'false');
    clear(body).append(h('p', { class: 'empty' }, '불러오는 중…'));
    if (!(await loadCodes())) return;
    clear(body);
    if (tab === 'codes') body.append(codesView());
    else if (tab === 'dashboard') renderDashboard(body, { onError: (err) => { if (err.status === 401) handleError(err); } });
    else body.append(await logsView());
  }

  const topicLabel = (id) => meta.topics.find((t) => t.id === id)?.label || id;
  const orderLabel = (o) => o.map((k) => meta.tasks[k].short).join('  →  ');

  // ───────── 참가자 코드 ─────────
  function codesView() {
    let order = meta.orders[0];
    const orderSel = h('select', { class: 'input', id: 'order' },
      meta.orders.map((o, i) => h('option', { value: String(i) }, orderLabel(o))));
    const topicSel = {};
    ['user', 'ai', 'delayed'].forEach((k, i) => {
      topicSel[k] = h('select', { class: 'input', id: `topic-${k}`, style: { height: '40px' } },
        meta.topics.map((t) => h('option', { value: t.id }, t.label)));
      topicSel[k].value = meta.topics[Math.min(i + 1, meta.topics.length - 1)].id;
    });
    const topicRows = h('div', { class: 'field', style: { gap: '12px' } });
    function drawTopicRows() {
      clear(topicRows).append(h('span', { class: 'field-label', style: { color: 'var(--muted)' } }, 'Task별 대화 주제'));
      order.forEach((k, i) => topicRows.append(
        h('div', { class: 'topic-row' }, h('label', { for: `topic-${k}` }, h('b', {}, String(i + 1)), meta.tasks[k].name), topicSel[k])));
    }
    orderSel.addEventListener('change', () => { order = meta.orders[Number(orderSel.value)]; drawTopicRows(); });
    drawTopicRows();

    const customCode = h('input', { class: 'input', id: 'custom-code', placeholder: '비워 두면 자동으로 만들어요', maxlength: '6', autocomplete: 'off' });
    customCode.addEventListener('input', () => { customCode.value = customCode.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 6); });
    const memo = h('input', { class: 'input', id: 'memo', placeholder: '예: 1차 파일럿 P01', autocomplete: 'off' });
    const createBtn = h('button', { type: 'button', class: 'btn btn-primary' }, '코드 생성');
    createBtn.addEventListener('click', async () => {
      createBtn.disabled = true;
      try {
        const rec = await api.admin.createCode({
          order,
          topics: { user: topicSel.user.value, ai: topicSel.ai.value, delayed: topicSel.delayed.value },
          memo: memo.value.trim(),
          code: customCode.value.trim() || null,
        });
        lastCreated = rec.code;
        toast(`코드 ${rec.code}를 만들었어요`);
        draw();
      } catch (err) {
        handleError(err);
        createBtn.disabled = false;
      }
    });

    const panel = h('section', { class: 'panel', 'aria-labelledby': 'new-h' },
      h('div', { class: 'field', style: { gap: '6px' } },
        h('h2', { id: 'new-h' }, '새 참가자 코드'),
        h('p', { class: 'sub' }, 'Task 순서와 각 Task의 대화 주제를 정하면 6자리 코드가 만들어져요.')),
      lastCreated ? h('div', { class: 'soft-box', style: { fontSize: '13px' } }, '방금 만든 코드 ',
        h('strong', { style: { fontSize: '20px', letterSpacing: '.18em', marginLeft: '6px' } }, lastCreated)) : null,
      h('div', { class: 'field' }, h('label', { for: 'order', class: 'field-label', style: { color: 'var(--muted)' } }, 'Task 순서'), orderSel),
      topicRows,
      h('div', { class: 'field' }, h('label', { for: 'custom-code', class: 'field-label', style: { color: 'var(--muted)' } }, '코드 직접 지정 (선택)'), customCode),
      h('div', { class: 'field' }, h('label', { for: 'memo', class: 'field-label', style: { color: 'var(--muted)' } }, '메모 (선택)'), memo),
      createBtn);

    const counts = { done: 0, progress: 0, new: 0 };
    codes.forEach((c) => { counts[c.status.key] = (counts[c.status.key] || 0) + 1; });

    const rows = codes.map((c) => h('tr', { class: c.code === lastCreated ? 'is-new' : '' },
      h('td', { class: 'code-cell' }, c.code, c.memo ? h('div', { style: { fontSize: '12px', fontWeight: 400, letterSpacing: 0, color: 'var(--muted)', marginTop: '4px' } }, c.memo) : null),
      h('td', {}, h('div', { class: 'task-chips' }, c.order.map((k, i) =>
        h('span', { class: 'task-chip' }, h('b', {}, String(i + 1)), h('strong', {}, meta.tasks[k].short), h('span', {}, topicLabel(c.topics[k])))))),
      h('td', {}, h('span', { class: `status ${c.status.key}` }, c.status.label)),
      h('td', { class: 'tabular', style: { fontSize: '13px', color: 'var(--muted)', whiteSpace: 'nowrap' } }, (c.created_at || '').slice(5, 16).replace('T', ' ')),
      h('td', { class: 'row-actions' },
        h('button', { type: 'button', class: 'btn btn-outline btn-sm', onclick: () => switchTab('logs', c.code) }, '로그 보기'),
        h('button', {
          type: 'button', class: 'icon-btn', 'aria-label': `${c.code} 삭제`, style: { marginLeft: '6px' },
          onclick: async () => {
            if (!window.confirm(`${c.code} 코드를 삭제할까요?\n(로그 파일은 data/logs 에 그대로 남아요)`)) return;
            try { await api.admin.deleteCode(c.code); toast('삭제했어요'); draw(); } catch (err) { handleError(err); }
          },
        }, icon('trash', 16)))));

    const table = codes.length
      ? h('div', { class: 'table-wrap' }, h('table', { class: 'table' },
        h('thead', {}, h('tr', {},
          h('th', { scope: 'col' }, '코드'), h('th', { scope: 'col' }, 'Task 순서 · 주제'), h('th', { scope: 'col' }, '진행'),
          h('th', { scope: 'col' }, '생성'), h('th', { scope: 'col' }, h('span', { class: 'sr-only' }, '관리')))),
        h('tbody', {}, rows)))
      : h('div', { class: 'table-wrap' }, h('p', { class: 'empty' }, '아직 만든 코드가 없어요. 왼쪽에서 첫 코드를 만들어 보세요.'));

    return h('div', { class: 'admin-main' },
      panel,
      h('section', { class: 'codes-col', 'aria-labelledby': 'codes-h' },
        h('div', { class: 'codes-head' },
          h('div', { style: { display: 'flex', alignItems: 'baseline', gap: '12px', flexWrap: 'wrap' } },
            h('h2', { id: 'codes-h' }, '참가자 ', h('span', { class: 'count' }, String(codes.length))),
            h('span', { style: { fontSize: '13px', color: 'var(--muted-2)' } }, `완료 ${counts.done} · 진행 중 ${counts.progress} · 시작 전 ${counts.new}`)),
          h('div', { class: 'dl-buttons' },
            h('span', { style: { fontSize: '12px', color: 'var(--muted)', alignSelf: 'center' } }, '전체 참가자 CSV'),
            Object.entries(KIND_LABEL).map(([k, label]) => dlLink(`/api/admin/export-all/${k}.csv`, label)))),
        table));
  }

  // ───────── 로그 ─────────
  async function logsView() {
    // 등록된 코드 + 코드는 지워졌지만 data/logs 에 기록이 남은 참가자
    let index = codes.map((c) => ({ code: c.code, status: c.status }));
    try { index = await api.admin.logIndex(); } catch (err) { handleError(err); }
    if (!selected && index.length) selected = index[0].code;
    const detail = h('section', { class: 'log-detail' });
    const buttons = index.map((c) => h('button', {
      type: 'button', 'aria-current': String(c.code === selected),
      onclick: () => { selected = c.code; buttons.forEach((b) => b.setAttribute('aria-current', String(b.dataset.code === selected))); loadDetail(); },
      'data-code': c.code,
    }, h('span', { class: 'c' }, c.code), h('span', { class: 's' }, c.status.label)));

    async function loadDetail() {
      clear(detail).append(h('p', { class: 'empty' }, '불러오는 중…'));
      if (!selected) { clear(detail).append(h('p', { class: 'empty' }, '참가자가 없어요.')); return; }
      try {
        const d = await api.admin.participant(selected);
        clear(detail).append(...participantDetail(d));
      } catch (err) {
        clear(detail).append(h('p', { class: 'empty' }, err.message));
        if (err.status === 401) handleError(err);
      }
    }
    loadDetail();

    return h('div', { class: 'log-layout' },
      h('aside', { class: 'log-list', 'aria-label': '참가자 목록' }, h('span', { class: 'cap' }, '참가자'), buttons),
      detail);
  }

  function participantDetail(d) {
    const p = d.participant || { code: selected, order: Object.keys(d.sessions), topics: {} };
    const code = p.code;
    const order = p.order || [];
    let curTask = order.find((k) => d.sessions[k]) || order[0];

    const stats = d.stats;
    const totalSec = Object.values(stats.per_task).reduce((a, t) => a + (t.elapsed_s || 0), 0);
    const statEl = h('div', { class: 'stats' }, [
      ['사용자 발화', stats.user_turns],
      ['평균 발화 길이', stats.avg_duration_s != null ? `${stats.avg_duration_s}초` : '—'],
      ['피드백 생성', stats.feedback_ready],
      ['피드백 확인', stats.feedback_shown],
      ['세션 시간 합계', totalSec ? `${Math.floor(totalSec / 60)}:${String(Math.round(totalSec % 60)).padStart(2, '0')}` : '—'],
    ].map(([k, v]) => h('div', { class: 'stat' }, h('span', {}, k), h('b', {}, String(v)))));

    const tabsEl = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Task' });
    const panel = h('div');
    function drawTabs() {
      tabsEl.replaceChildren(...order.map((k, i) => h('button', {
        type: 'button', class: 'tab', role: 'tab', 'aria-selected': String(k === curTask),
        onclick: () => { curTask = k; drawTabs(); drawPanel(); },
      }, `Task ${i + 1} · ${meta.tasks[k].name}`)));
    }
    function drawPanel() {
      clear(panel).append(taskPanel(code, curTask, d.sessions[curTask], d.events));
    }
    drawTabs();
    drawPanel();

    return [
      h('div', { class: 'field', style: { gap: '6px' } },
        h('h1', {}, code),
        h('p', { class: 'meta' }, [
          order.map((k) => meta.tasks[k].short).join(' → '),
          p.memo,
          p.created_at ? `생성 ${p.created_at.slice(0, 16).replace('T', ' ')}` : null,
          d.status.label,
        ].filter(Boolean).join(' · '))),
      h('section', { class: 'dl-bar', 'aria-labelledby': 'dl-h' },
        h('div', {}, h('h2', { id: 'dl-h' }, 'CSV 내려받기'), h('span', { class: 'sub' }, '이 참가자의 전체 Task 기준 · 파일마다 따로 받을 수 있어요')),
        h('div', { class: 'dl-buttons' },
          Object.entries(KIND_LABEL).map(([k, label]) => dlLink(`/api/admin/export/${code}/${k}.csv`, label)),
          dlLink(`/api/admin/export/${code}.zip`, '전체 (ZIP)', { primary: true }))),
      statEl,
      tabsEl,
      panel,
    ];
  }

  // 이 참가자 · 이 Task의 발화별 점수 분포 (조건별 묶음: 누름/안 누름, 제시/미제시, 전체)
  function scorePanel(task, session) {
    const series = sessionScoreSeries(task, session.turns);
    return h('div', { class: 'score-panel' },
      h('div', { class: 'log-col-head' }, h('h2', {}, '발화별 점수 분포'), scoreLegend(series('l1'))),
      ['l1', 'l2', 'urgency'].map((k) => scoreHist({ title: SCORE_LABEL[k], series: series(k), height: 56, compact: true })));
  }

  function taskPanel(code, task, session, events) {
    if (!session) return h('p', { class: 'empty' }, '아직 시작하지 않은 Task예요.');
    const answers = session.annotation?.answers || [];

    const turnCards = session.turns.map((t) => {
      if (t.role === 'ai') {
        return h('div', { class: 'turn-card ai' },
          h('div', { class: 'head' }, h('span', {}, `#${t.id}`), h('b', {}, 'AI'), h('span', {}, fmtClock(t.ts))),
          h('p', { lang: 'en' }, t.text));
      }
      const fb = t.feedback;
      const st = feedbackState(task, t);
      // 피드백 진행 상황: 요청 · 노출 경로 · AI 결정
      const tags = [];
      if (!fb) tags.push(h('span', {}, t.feedback_status === 'error' ? '피드백 오류' : t.feedback_status === 'not_requested' ? '요청 안 함' : '피드백 대기'));
      else if (fb.has_issue && t.shown) tags.push(h('span', { class: 'seen' }, VIA_LABEL[t.shown_via] || '확인함'));
      else if (fb.has_issue) tags.push(h('span', {}, '확인 안 함'));
      if (task === 'user' && (t.requested || t.shown_via === 'request')) {
        tags.push(h('span', { class: 'seen' }, `피드백 보기 누름${t.request_count > 1 ? ` ×${t.request_count}` : ''} · ${fmtClock(t.requested_at || t.shown_at)}`));
      } else if (task === 'user') {
        tags.push(h('span', {}, '피드백 보기 안 누름'));
      }
      if (t.intervention) tags.push(h('span', { class: t.intervention.show ? 'seen' : '' }, `AI 결정: ${t.intervention.show ? '보여줌' : '안 보여줌'}`));
      return h('div', { class: 'turn-card' },
        h('div', { class: 'head' },
          h('span', {}, `#${t.id}`), h('b', {}, '참가자'), h('span', {}, fmtClock(t.ts)),
          t.duration_s ? h('span', {}, `${t.duration_s}초`) : null,
          t.input === 'typed' ? h('span', {}, '직접 입력') : null,
          t.stt_engine && t.stt_engine !== 'typed' ? h('span', {}, t.stt_engine === 'whisper' ? 'Whisper 전사' : (t.stt_cleaned ? '브라우저 전사 · 다듬음' : '브라우저 전사')) : null),
        h('p', { lang: 'en' }, t.text),
        fb?.has_issue ? h('p', { class: 'revised', lang: 'en' }, highlighted(t.text, fb.revised)) : null,
        h('div', { class: 'tags' }, tags),
        fb ? scoreBox(fb, t) : null,
        annotationBox(st, answers.filter((a) => a.turn_id === t.id)),
        // 전사 원문 · 녹음은 아래에 작게
        (t.stt_raw && t.stt_raw !== t.text) || (t.stt_preview && t.stt_preview !== t.text) || t.recording_url
          ? h('div', { class: 'turn-foot' },
            t.stt_raw && t.stt_raw !== t.text ? h('p', { class: 'stt-raw', lang: 'en' }, h('b', {}, '다듬기 전 '), t.stt_raw) : null,
            t.stt_preview && t.stt_preview !== t.text ? h('p', { class: 'stt-raw', lang: 'en' }, h('b', {}, '브라우저 미리보기 '), t.stt_preview) : null,
            t.recording_url ? h('div', { class: 'rec-row' },
              playButton(t.recording_url, (url) => playClip(url), { label: '녹음 듣기' }),
              h('a', { href: t.recording_url, download: t.recording?.name || '' }, t.recording?.name || '내려받기'),
              t.recording?.seconds ? h('span', {}, `${t.recording.seconds}초`) : null) : null)
          : null);
    });

    const sv = session.survey;
    const surveyBox = sv
      ? h('div', { class: 'survey-box' },
        h('b', {}, `세션 설문 · ${(sv.submitted_at || '').slice(11, 19)}`),
        h('div', { class: 'tags' }, Object.entries(sv.likert || {}).map(([k, v]) => h('span', {}, `${k}: ${v}`))),
        Object.entries(sv.text || {}).filter(([, v]) => v).map(([k, v]) => h('p', {}, h('b', {}, `${k} `), v)))
      : h('div', { class: 'survey-box' }, h('span', { style: { color: 'var(--muted)' } }, '설문 응답 없음'));

    const evs = events.filter((e) => e.task === task);
    const evRows = evs.map((e) => h('div', { class: 'event-row' },
      h('span', { class: 'ts' }, (e.ts || '').slice(11, 23)),
      h('span', { class: `ev${e.source === 'client' ? ' client' : ''}` }, e.event),
      h('span', { class: 'data' }, JSON.stringify(e.data).slice(0, 280))));

    return h('div', { class: 'log-cols' },
      h('section', { class: 'log-col', 'aria-label': '대화 기록' },
        h('div', { class: 'log-col-head' },
          h('h2', {}, '대화 · 피드백 · Annotation ', h('span', {}, `피드백 방식 ${session.mode === 'detailed' ? '자세한' : '간단한'} (종료 시)`)),
          dlLink(`/api/admin/export/${code}/turns.csv?task=${task}`, '이 Task CSV', { small: true })),
        turnCards,
        surveyBox),
      h('section', { class: 'log-col events-col', 'aria-label': '점수 분포와 이벤트 로그' },
        scorePanel(task, session),
        h('div', { class: 'log-col-head' },
          h('h2', {}, '이벤트 ', h('span', {}, `${evs.length}건`)),
          dlLink(`/api/admin/export/${code}/events.csv?task=${task}`, '이 Task CSV', { small: true })),
        h('div', { class: 'events' }, evRows.length ? evRows : h('p', { class: 'empty' }, '이벤트 없음'))));
  }

  draw();
}
