// 피드백 카드: 간단한 피드백(고친 문장 + 강조) / 자세한 피드백(+ 항목별 이유)
import { h } from '../lib/dom.js';
import { highlighted } from '../lib/diff.js';

const TYPE_LABEL = { meaning: '의미 전달', expression: '더 나은 표현' };
const CATEGORY_LABEL = { vocabulary: '어휘', grammar: '문법', pragmatics: '화용' };

export function itemTag(type, category) {
  const cat = CATEGORY_LABEL[category];
  return h('span', { class: `tag tag-${type}` }, TYPE_LABEL[type] || type, cat ? ` · ${cat}` : '');
}

export function feedbackItems(items) {
  return h('ul', { class: 'fb-items' }, items.map((it) =>
    h('li', { class: 'fb-item' },
      h('span', { class: 'fb-change' },
        itemTag(it.type, it.category),
        it.original ? h('span', { class: 'strike', lang: 'en' }, it.original) : null,
        it.original ? h('span', { class: 'arrow', 'aria-hidden': 'true' }, '→') : null,
        h('span', { class: 'to', lang: 'en' }, it.revised)),
      it.explanation ? h('span', { class: 'fb-why' }, it.explanation) : null)));
}

export function feedbackCard(fb, original, mode, { title = '피드백', meta = '' } = {}) {
  const card = h('section', { class: 'fb-card', 'aria-label': title },
    h('div', { class: 'fb-head' }, h('b', {}, title), meta ? h('span', { class: 'tabular' }, meta) : null));
  if (!fb || !fb.has_issue) {
    // 점수가 기준(N) 미만이라 피드백 대상이 아닌 발화
    card.append(h('p', { class: 'fb-ok' }, '이 말에는 피드백이 없어요. 하고 싶은 말이 잘 전달됐어요!'));
    return card;
  }
  card.append(h('p', { class: 'fb-text', lang: 'en' }, highlighted(original, fb.revised)));
  if (mode === 'detailed' && fb.items?.length) card.append(feedbackItems(fb.items));
  return card;
}

export function loadingCard(text = '피드백을 불러오는 중이에요…') {
  return h('p', { class: 'fb-loading' }, text);
}
