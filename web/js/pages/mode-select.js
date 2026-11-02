// 피드백 방식 선택: 간단한 피드백 / 자세한 피드백
import { state, save, currentTask } from '../state.js';
import { h } from '../lib/dom.js';
import { logEvent } from '../lib/log.js';
import { pageFooter } from '../components/page-footer.js';

const ORIGINAL = 'The movie was very interesting and I liked it very much.';

function example(detailed) {
  const hl = (t) => h('mark', { class: 'hl' }, t);
  return h('span', { class: 'example', 'aria-hidden': 'true' },
    h('span', { class: 'example-label' }, '예시'),
    h('span', { class: 'strike', lang: 'en', style: { fontSize: '14px' } }, ORIGINAL),
    h('span', { lang: 'en' }, 'The movie was ', hl('really gripping'), '. ', hl('I couldn’t take my eyes off it.')),
    detailed ? h('span', { class: 'why' }, 'very interesting 대신 gripping처럼 구체적인 단어를 쓰면 느낌이 더 생생하게 전해져요. ‘눈을 뗄 수 없었다’로 얼마나 좋았는지도 보여줄 수 있어요.') : null);
}

export function render(main, ctx) {
  const task = currentTask();
  const conf = state.config.tasks[task];
  let mode = state.modes[task] || null;

  const footer = pageFooter({ label: '대화 시작', onClick: () => ctx.next(), enabled: !!mode, hint: '피드백 방식을 골라 주세요' });

  const options = [
    ['simple', '간단한 피드백', '더 나은 표현만 보여줘요'],
    ['detailed', '자세한 피드백', '더 나은 표현과 함께 이유를 설명해요'],
  ].map(([key, name, desc]) => {
    const input = h('input', { type: 'radio', name: 'mode', value: key, checked: mode === key });
    const label = h('label', { class: `choice${mode === key ? ' is-selected' : ''}` },
      h('span', { class: 'choice-top' }, input,
        h('span', {}, h('span', { class: 'choice-name' }, name), h('span', { class: 'choice-desc' }, desc))),
      example(key === 'detailed'));
    input.addEventListener('change', () => {
      mode = key;
      state.modes[task] = key;
      save();
      document.querySelectorAll('.choice').forEach((c) => c.classList.toggle('is-selected', c === label));
      footer.setEnabled(true);
      logEvent('mode_select', { mode: key });
    });
    return label;
  });

  main.append(
    h('div', { class: 'page' },
      h('div', { class: 'page-inner' },
        h('header', { class: 'page-head' },
          h('span', { class: 'eyebrow' }, `Task ${state.taskIndex + 1} / ${state.participant.order.length} · ${conf.name}`),
          h('h1', { class: 'page-title' }, '피드백을 어떻게 받을까요?'),
          h('p', { class: 'lead' }, task === 'delayed'
            ? '대화가 끝난 뒤 보여드릴 피드백의 기본 방식을 골라 주세요. 종합 피드백 화면에서 두 방식을 모두 볼 수 있어요.'
            : '원하는 방식을 골라 주세요. 대화 중에도 언제든 바꿀 수 있고, 바꾸면 이미 받은 피드백도 함께 바뀌어요.')),
        h('fieldset', { class: 'choice-grid', style: { border: 'none', margin: 0, padding: 0 } },
          h('legend', { class: 'sr-only' }, '피드백 방식'), options))),
    footer.el,
  );
}
