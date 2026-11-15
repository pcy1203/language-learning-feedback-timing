// 선 아이콘 (stroke = currentColor)
const svg = (size, body, sw = 1.8) =>
  `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${sw}" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;

export const ICONS = {
  mic: (s) => svg(s, '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>'),
  speaker: (s) => svg(s, '<path d="M4 9v6h4l5 4V5L8 9H4z"/><path d="M17 9a4 4 0 0 1 0 6"/>'),
  clock: (s) => svg(s, '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 3h6"/>'),
  arrow: (s) => svg(s, '<path d="M5 12h14M13 6l6 6-6 6"/>', 2),
  check: (s) => svg(s, '<path d="M5 12.5l4.5 4.5L19 7.5"/>', 2.4),
  message: (s) => svg(s, '<path d="M4 5h16v11H9l-5 4V5z"/><path d="M9 10h6"/>'),
  download: (s) => svg(s, '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>'),
  trash: (s) => svg(s, '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/>'),
  refresh: (s) => svg(s, '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>'),
  chrome: (s) => svg(s, '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/>'),
  clipboard: (s) => svg(s, '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9zM9 12h6M9 16h4"/>'),
  play: (s) => svg(s, '<path d="M8 5.5v13l10.5-6.5z"/>'),
  stopSq: (s) => svg(s, '<rect x="7" y="7" width="10" height="10" rx="1.5"/>'),
  exit: (s) => svg(s, '<path d="M14 5H6v14h8M10 12h10M17 9l3 3-3 3"/>'),
  dot: (s) => svg(s, '<circle cx="12" cy="12" r="3"/>'),
};
