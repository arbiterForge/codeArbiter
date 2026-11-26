// Symbology. Like map symbology, every mark means one thing everywhere it appears:
// the frame's SHAPE says what kind of thing a part is, its FILL says what state it is in right now,
// and each kind of MOTION in the machine carries one meaning.

export { KIND_FRAME, FRAME_KEY, MOTION_KEY } from './content.js';
import { KIND_FRAME } from './content.js';

const PATHS = {
  circle: '<circle cx="8" cy="8" r="6"/>',
  square: '<rect x="2.25" y="2.25" width="11.5" height="11.5" rx="2.6"/>',
  shield: '<path d="M8 1.7 13.5 3.7V8c0 3.1-2.3 5.2-5.5 6.3C4.8 13.2 2.5 11.1 2.5 8V3.7Z"/>',
  hex: '<path d="M8 1.6 13.55 4.8v6.4L8 14.4 2.45 11.2V4.8Z"/>',
  chevron: '<path d="M2 3.3h7.7L14 8l-4.3 4.7H2L5.3 8Z"/>',
  doc: '<path d="M3.3 1.8H10l2.7 2.7v9.7H3.3Z"/><path d="M10 1.8v2.7h2.7" fill="none"/>',
  rect: '<rect x="1.8" y="3.6" width="12.4" height="8.8" rx="1.3"/>',
  diamond: '<path d="M8 1.5 14.5 8 8 14.5 1.5 8Z"/>',
  dashed: '<circle cx="8" cy="8" r="6" stroke-dasharray="2.2 2.1"/>',
};

export const frameOf = (p) => KIND_FRAME[p?.kind] || 'square';
export function frameSVG(shape, cls = 'fr') {
  return `<svg class="${cls}" viewBox="0 0 16 16" aria-hidden="true" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round">${PATHS[shape] || PATHS.square}</svg>`;
}
