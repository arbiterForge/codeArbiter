/** Chapter selection is presentation only. Native links are the sole history writes. */
export function fragmentId(hash: string): string | undefined {
  if (!hash.startsWith('#') || hash.length < 2 || hash.length > 1024) return;
  try { return decodeURIComponent(hash.slice(1)); } catch { return; }
}

/** Resolve literal IDs within this map; a fragment is never a selector or code. */
export function installMapNavigation(root: HTMLElement): AbortController {
  const controller = new AbortController();
  const options = { signal: controller.signal };
  const controls = root.querySelector<HTMLElement>('.ca-execution-map__controls');
  const status = root.querySelector<HTMLElement>('[data-map-status]');
  const sections = Array.from(root.querySelectorAll<HTMLElement>('[data-map-chapter]'));
  const buttons = Array.from(root.querySelectorAll<HTMLButtonElement>('[data-map-select]'));
  if (!controls || !status || !sections.length || !buttons.length) return controller;
  let frame = 0;
  let focusTarget: HTMLElement | undefined;
  const choose = (selection: string) => {
    if (selection !== 'all' && !sections.some(section => section.dataset.mapChapter === selection)) return;
    cancelAnimationFrame(frame);
    sections.forEach(section => { section.hidden = selection !== 'all' && section.dataset.mapChapter !== selection; });
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.mapSelect === selection)));
    status.textContent = selection === 'all' ? `All ${sections.length} chapters. Read in numbered order.`
      : `Chapter ${sections.findIndex(section => section.dataset.mapChapter === selection) + 1} of ${sections.length}. Choose another chapter or read the whole path.`;
  };
  const revealFragment = (hash: string, moveFocus = false) => {
    const id = fragmentId(hash);
    if (!id) return;
    const target = document.getElementById(id);
    if (!target || !root.contains(target)) return;
    if (moveFocus) focusTarget = target;
    const chapter = target.closest<HTMLElement>('[data-map-chapter]');
    if (chapter && sections.includes(chapter)) choose(chapter.dataset.mapChapter!);
    // A chapter may live inside both an initialization chooser and its route.
    // Reveal only ancestors of the requested target, never its sibling route.
    for (let element: HTMLElement | null = target; element; element = element.parentElement) {
      if (element instanceof HTMLDetailsElement) element.open = true;
    }
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (controller.signal.aborted || !target.isConnected) return;
      // Explicit chapter links move keyboard focus as well as the reading view.
      // Keep this request if a native hash event reschedules the animation frame.
      if (focusTarget === target) {
        target.focus({ preventScroll: true });
        focusTarget = undefined;
      }
      target.scrollIntoView({ block: 'start', behavior: 'instant' });
    });
  };
  buttons.forEach(button => button.addEventListener('click', () => {
    focusTarget = undefined;
    choose(button.dataset.mapSelect!);
  }, options));
  const readLocation = () => revealFragment(location.hash);
  window.addEventListener('hashchange', readLocation, options);
  window.addEventListener('popstate', readLocation, options);
  // Astro may update history before replacing the document. Re-read its final DOM.
  document.addEventListener('astro:page-load', readLocation, options);
  root.addEventListener('click', event => {
    if (!(event instanceof MouseEvent) || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const link = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href^="#"]') : null;
    if (!link || link.target || link.hasAttribute('download')) return;
    // Read the clicked destination, not the old location. Astro can use
    // pushState for a same-page link without firing hashchange or page-load.
    // Keep its native history handling; also restore a same-fragment selection.
    const requestedHash = link.hash;
    queueMicrotask(() => { if (!controller.signal.aborted) revealFragment(requestedHash, true); });
  }, options);
  controller.signal.addEventListener('abort', () => cancelAnimationFrame(frame), { once: true });
  choose(root.dataset.initial ?? sections[0].dataset.mapChapter!);
  controls.hidden = false;
  readLocation();
  return controller;
}
