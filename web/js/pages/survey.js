// 세션(Task)이 끝날 때마다 받는 설문: 리커트 + 좋았던 점 / 아쉬운 점 / 그 밖에 하고 싶은 말
// 다른 단계와 헷갈리지 않도록 상단에 진한 색 띠(survey-hero)로 따로 표시한다.
import { api } from '../api.js';
import { state, currentTask } from '../state.js';
import { h, icon } from '../lib/dom.js';
import { logEvent } from '../lib/log.js';
import { toast } from '../lib/toast.js';
import { pageFooter } from '../components/page-footer.js';

export function render(main, ctx) {
  const task = currentTask();
  const conf = state.config.survey;
  const tconf = state.config.tasks[task];
  const total = state.participant.order.length;
  const isLast = state.taskIndex === total - 1;
  const likert = {};
  const texts = {};
  const items = conf.likert.items;

  const footer = pageFooter({
    label: isLast ? '제출하고 마치기' : '제출하고 다음 Task로',
    enabled: false, hint: '모든 문항에 답해 주세요', onClick: submit,
  });
  const progress = h('span', { class: 'survey-progress' });

  function refresh() {
    const answered = items.filter((it) => likert[it.key]).length;
    progress.textContent = `${answered} / ${items.length} 문항`;
    footer.setEnabled(answered === items.length, '모든 문항에 답해 주세요');
  }

  const rows = items.map((it, idx) =>
    h('div', { class: 'likert-row', role: 'radiogroup', 'aria-label': it.text },
      h('span', { class: 'q' }, h('b', { class: 'q-num' }, String(idx + 1)), it.text),
      h('div', { class: 'likert-scale' },
        Array.from({ length: conf.likert.scale }, (_, i) => {
          const v = i + 1;
          const input = h('input', { type: 'radio', name: `lk-${it.key}`, value: String(v) });
          input.addEventListener('change', () => { likert[it.key] = v; refresh(); });
          return h('label', {}, input, String(v));
        }))));

  const ph = conf.placeholders[task] || {};
  const textField = (f) => {
    const id = `ft-${f.key}`;
    const ta = h('textarea', { id, class: 'input', rows: f.key === 'memo' ? '3' : '4', placeholder: f.key === 'memo' ? conf.placeholders.memo : ph[f.key] || '' });
    ta.addEventListener('input', () => { texts[f.key] = ta.value; });
    return h('div', { class: 'field' },
      h('label', { for: id, class: 'field-label' }, f.label, f.optional_label ? h('span', { class: 'optional' }, ' (선택)') : null),
      ta);
  };
  const fields = conf.free_text.filter((f) => f.key !== 'memo').map(textField);
  const memo = conf.free_text.find((f) => f.key === 'memo');

  async function submit() {
    footer.setBusy(true);
    try {
      await api.submitSurvey(task, likert, texts);
      ctx.next();
    } catch (err) {
      toast(err.message);
      footer.setBusy(false);
    }
  }

  const hero = h('section', { class: 'survey-hero', 'aria-labelledby': 'survey-title' },
    h('div', { class: 'survey-hero-inner' },
      h('span', { class: 'survey-badge' }, icon('clipboard', 15), `세션 설문 · Task ${state.taskIndex + 1} / ${total}`),
      h('h1', { id: 'survey-title', class: 'survey-title' }, `${tconf.name} 방식은 어땠나요?`),
      h('p', { class: 'survey-sub' }, `방금 경험한 방식(${tconf.summary})에 대해서만 답해 주세요. 대화 주제는 '${state.participant.topic_labels[task]}'였어요.`)));

  main.append(
    hero,
    h('div', { class: 'page', style: { paddingTop: '40px' } },
      h('form', { class: 'page-inner', onsubmit: (e) => e.preventDefault() },
        h('section', { class: 'field', style: { gap: '12px' } },
          h('div', { class: 'section-head' },
            h('h2', {}, '평가 문항'),
            progress),
          h('p', { class: 'section-note' }, `1(${conf.likert.low_label})부터 ${conf.likert.scale}(${conf.likert.high_label})까지 골라 주세요.`),
          h('fieldset', { class: 'likert' },
            h('legend', { class: 'sr-only' }, `${tconf.name} 평가`),
            h('div', { class: 'likert-head', 'aria-hidden': 'true' },
              h('span', { class: 'q' }, '문항'),
              h('span', { class: 'ends' }, h('span', {}, conf.likert.low_label), h('span', {}, conf.likert.high_label))),
            rows)),
        h('section', { class: 'field', style: { gap: '12px' } },
          h('div', { class: 'section-head' }, h('h2', {}, '자유롭게 적어 주세요')),
          h('div', { class: 'free-grid' }, fields),
          memo ? h('div', { class: 'free-block' }, textField(memo)) : null))),
    footer.el,
  );
  refresh();
  logEvent('survey_view', {});
}
