// Annotation: 모든 발화와 피드백(본 것은 컬러, 못 본 것은 회색)을 보고 조건별 질문에 답한다.
// 발화의 피드백 상태(feedbackState)에 따라 질문이 달라진다 (config/annotation.json → rules).
//   seen              고칠 부분이 있었고 피드백을 봤음
//   unseen            고칠 부분이 있었지만 대화 중에 보지 않았음
//   checked_no_issue  (User Trigger) 피드백을 요청했지만 고칠 부분이 없었음
//   no_feedback       고칠 부분이 없어 피드백이 없었음 → 피드백 내용에 대한 질문은 묻지 않음
// 같은 규칙이 서버의 session_store.feedback_state() 에도 있다.
import { api } from '../api.js';
import { state, currentTask } from '../state.js';
import { h } from '../lib/dom.js';
import { highlighted } from '../lib/diff.js';
import { logEvent } from '../lib/log.js';
import { toast } from '../lib/toast.js';
import { pageFooter } from '../components/page-footer.js';
import { playButton } from '../components/message-bubble.js';
import { playClip, stopAudio } from '../lib/audio-player.js';

export function feedbackState(task, turn) {
  const fb = turn.feedback;
  if (!fb) return null;
  if (fb.has_issue) return turn.shown ? 'seen' : 'unseen';
  if (task === 'user' && (turn.requested || turn.shown_via === 'request')) return 'checked_no_issue';
  return 'no_feedback';
}

export function render(main, ctx) {
  const task = currentTask();
  const conf = state.config.annotation;
  const answers = new Map(); // "turnId:key" → answer
  const required = new Set();

  const footer = pageFooter({
    label: '저장하고 설문으로', enabled: false, hint: '모든 항목에 답하면 저장할 수 있어요', onClick: saveAll,
  });
  const listEl = h('ol', { class: 'list', style: { gap: '16px' } }, h('li', { class: 'lead' }, '불러오는 중…'));
  const legend = h('div', { class: 'legend' },
    h('span', {}, h('i', { class: 'seen' }), conf.labels.seen[task]),
    task !== 'delayed' ? h('span', {}, h('i', { class: 'unseen' }), conf.labels.unseen[task]) : null,
    h('span', {}, h('i', { class: 'none' }), '피드백 없음'));

  main.append(
    h('div', { class: 'page' },
      h('div', { class: 'page-inner' },
        h('header', { class: 'page-head' },
          h('h1', { class: 'page-title' }, '대화 돌아보기'),
          h('p', { class: 'lead' }, conf.intro[task])),
        legend, listEl)),
    footer.el,
  );

  function refreshFooter() {
    const done = [...required].every((k) => answers.has(k));
    footer.setEnabled(done, '모든 항목에 답하면 저장할 수 있어요');
  }

  function questionRow(turn, key, fbState) {
    const q = conf.questions[key];
    const id = `${turn.id}:${key}`;
    required.add(id);
    const buttons = q.options.map((label, i) =>
      h('button', { type: 'button', class: 'opt', 'aria-pressed': 'false', 'data-i': String(i) }, label));
    buttons.forEach((b, i) => b.addEventListener('click', () => {
      answers.set(id, { turn_id: turn.id, key, value: i, label: q.options[i], feedback_state: fbState, answered_at: new Date().toISOString() });
      buttons.forEach((x, j) => x.setAttribute('aria-pressed', String(j === i)));
      logEvent('annotation_click', { turn_id: turn.id, key, value: i, label: q.options[i], feedback_state: fbState });
      refreshFooter();
    }));
    return h('div', { class: 'ann-q', role: 'group', 'aria-label': q.label }, h('span', {}, q.label), h('div', { class: 'opts' }, buttons));
  }

  async function onPlay(url) {
    logEvent('recording_play', { url, where: 'annotation' });
    const r = await playClip(url);
    logEvent('recording_play_end', { url, where: 'annotation', result: r });
  }

  function userCard(turn) {
    const fb = turn.feedback;
    const body = h('div', { class: 'ann-body' },
      h('div', { class: 'ann-said' },
        h('div', { class: 'who' }, h('b', {}, '나'), turn.recording_url ? playButton(turn.recording_url, onPlay) : null),
        h('div', { class: 'col' },
          h('p', { lang: 'en' }, turn.text),
          fb?.intended_meaning ? h('p', { class: 'ann-intent' }, h('b', {}, 'AI가 이해한 의도'), ' · ', fb.intended_meaning) : null)));

    const fbState = feedbackState(task, turn);
    if (!fbState) {
      body.append(h('div', { class: 'ann-nofb' }, '이 발화는 피드백을 만들지 못했어요'));
      return h('li', { class: 'ann-turn' }, body);
    }
    if (fbState === 'seen' || fbState === 'unseen') {
      const unseen = fbState === 'unseen';
      const summary = fb.items.map((it) => (it.original ? `${it.original} → ${it.revised}` : it.revised)).join(' · ');
      body.append(h('div', { class: `ann-fb${unseen ? ' is-unseen' : ''}` },
        h('span', { class: 'title' }, conf.labels[fbState][task]),
        h('p', { class: 'fb-text', lang: 'en' }, highlighted(turn.text, fb.revised, { muted: unseen })),
        summary ? h('p', { class: 'summary', lang: 'en' }, summary) : null));
    } else {
      body.append(h('div', { class: 'ann-nofb' }, conf.labels[fbState]));
    }
    const keys = (conf.rules[task] || {})[fbState] || [];
    return h('li', { class: 'ann-turn' }, body,
      keys.length ? h('div', { class: 'ann-qs' }, keys.map((k) => questionRow(turn, k, fbState))) : null);
  }

  async function saveAll() {
    footer.setBusy(true);
    try {
      await api.saveAnnotation(task, [...answers.values()]);
      ctx.next();
    } catch (err) {
      toast(err.message);
      footer.setBusy(false);
    }
  }

  api.getSession(task).then((s) => {
    const items = s.turns.map((t) => (t.role === 'ai'
      ? h('li', { class: 'ann-ai' }, h('b', {}, 'AI'), h('span', { lang: 'en' }, t.text))
      : userCard(t)));
    listEl.replaceChildren(...items);
    refreshFooter();
    logEvent('annotation_view', { questions: required.size, recordings: s.turns.filter((t) => t.recording_url).length });
  }).catch((err) => {
    listEl.replaceChildren(h('li', { class: 'error-box', role: 'alert' }, err.message));
  });

  return () => stopAudio();
}
