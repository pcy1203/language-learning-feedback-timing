// 연구 소개 (코드 입력 직후 한 번): 전체 진행 과정 + 세션 하나의 흐름을 화면 사진으로 보여준다.
import { state } from '../state.js';
import { h, icon } from '../lib/dom.js';
import { logEvent } from '../lib/log.js';

const SESSION_FLOW = [
  { key: 'intro', label: '설명', min: 1, img: 'intro', text: '피드백 제시 방식 확인' },
  { key: 'chat', label: '대화', min: 9, img: 'chat', text: 'AI와 영어로 대화하며 피드백 받기' },
  { key: 'annotation', label: '피드백 Annotation', min: 3, img: 'annotation', text: '각 발화마다 피드백 다시 검토하기' },
  { key: 'survey', label: '설문', min: 2, img: 'survey', text: '피드백 방식 평가하기' },
];

export function render(root, ctx) {
  const { config, participant } = state;
  const minutes = Math.round((config.settings.session_seconds || 540) / 60);
  const flow = SESSION_FLOW.map((s) => (s.key === 'chat' ? { ...s, min: minutes } : s));
  const total = flow.reduce((a, s) => a + s.min, 0);

  // 크게 보기
  const bigImg = h('img', { alt: '' });
  const bigCap = h('p', { class: 'ov-zoom-cap' });
  const zoom = h('dialog', { class: 'ov-zoom', onclick: () => zoom.close() }, bigImg, bigCap);
  function openZoom(s) {
    bigImg.src = `/img/overview/${s.img}.jpg`;
    bigImg.alt = `${s.label} 화면`;
    bigCap.textContent = `${s.label} · 약 ${s.min}분`;
    zoom.showModal();
    logEvent('overview_zoom', { step: s.key });
  }

  // 전체 진행: 사전 인터뷰 → 튜토리얼 → Session 1~3 (배정된 조건 순서) → 사후 인터뷰
  const sessionNodes = participant.order.map((task, i) => h('li', { class: 'ov-node is-session' },
    h('span', { class: 'ov-node-top' }, `Session ${i + 1}`),
    h('b', {}, config.tasks[task].name),
    h('span', { class: 'ov-node-sub' }, config.tasks[task].summary)));
  const offline = (label) => h('li', { class: 'ov-node is-offline' }, h('b', {}, label));
  const process = h('ol', { class: 'ov-process' }, offline('사전 인터뷰'), offline('튜토리얼'), sessionNodes, offline('사후 인터뷰'));

  // 세션 하나의 흐름 (화면 사진)
  const steps = h('ol', { class: 'ov-flow' }, flow.map((s, i) => h('li', { class: 'ov-step' },
    h('button', { type: 'button', class: 'ov-shot', onclick: () => openZoom(s), 'aria-label': `${s.label} 화면 크게 보기` },
      h('img', { src: `/img/overview/${s.img}.jpg`, alt: '', loading: 'lazy' }),
      h('span', { class: 'ov-zoom-hint' }, icon('search', 13), '크게 보기')),
    h('div', { class: 'ov-step-text' },
      h('span', { class: 'ov-step-num' }, String(i + 1)),
      h('b', {}, s.label),
      h('span', { class: 'ov-min' }, `${s.min}분`)),
    h('p', {}, s.text))));

  root.append(h('div', { class: 'solo' },
    h('header', { class: 'solo-header' }, config.study_title),
    h('main', { class: 'ov-main' },
      h('header', { class: 'page-head' },
        h('span', { class: 'eyebrow' }, '연구 소개'),
        h('h1', { class: 'page-title' }, 'AI와 영어로 대화하며, 세 가지 교정적 피드백 방식을 경험해요'),
        h('p', { class: 'lead' }, '대화를 세 세션 진행하며, 세션마다 피드백이 제시되는 방식이 달라요.')),
      h('section', { class: 'ov-section', 'aria-labelledby': 'ov-p' },
        h('h2', { id: 'ov-p' }, '전체 진행'),
        process),
      h('section', { class: 'ov-section', 'aria-labelledby': 'ov-s' },
        h('h2', { id: 'ov-s' }, '세션 하나는 이렇게 진행돼요', h('span', {}, `약 ${total}분`)),
        steps),
      h('div', { class: 'ov-actions' },
        h('button', { type: 'button', class: 'btn btn-primary btn-lg', onclick: () => { logEvent('overview_done'); ctx.goStep('intro'); } },
          '시작하기', icon('arrow', 18)))),
    zoom));

  logEvent('overview_view');
}
