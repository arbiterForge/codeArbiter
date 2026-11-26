/** machine-stage.ts - start the 3D machine on /concepts/machine/ only when a reader asks for it.
 *
 * The page is complete as HTML. A start control loads the viewer chunk and the validated model, mounts
 * the viewer into the stage's shadow root, and routes to a tour, lab, lane run or part if one was asked
 * for. Astro's client router keeps this module alive across pages, so the viewer is disposed before
 * every page swap and wired again on each page load.
 */
import type { MachineHandle } from './machine/viewer.js';

let handle: MachineHandle | null = null;
let pending: Promise<MachineHandle | null> | null = null;

const stageOf = () => document.querySelector<HTMLElement>('[data-machine-stage]');

async function start(route: string, session: boolean): Promise<void> {
  const stage = stageOf();
  if (!stage) return;
  stage.scrollIntoView({ block: 'nearest', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  if (handle) {
    if (route) handle.route(route);
    if (session) handle.playSession();
    return;
  }
  if (pending) return;
  stage.dataset.state = 'loading';
  pending = (async () => {
    try {
      const [{ mountMachine }, response] = await Promise.all([
        import('./machine/viewer.js'),
        fetch(stage.dataset.machineModel!, { credentials: 'same-origin' }),
      ]);
      if (!response.ok) throw new Error(`model request failed: ${response.status}`);
      const model = await response.json();
      if (stageOf() !== stage) return null; // the reader navigated away while it loaded
      return await mountMachine(stage, model, {
        route,
        session,
        debug: new URLSearchParams(location.search).has('debug'),
        onClose: stop,
      });
    } catch (error) {
      console.warn('The 3D machine could not start:', error);
      stage.dataset.state = 'failed';
      return null;
    }
  })();
  const started = await pending;
  pending = null;
  if (!started) return;
  handle = started;
  stage.dataset.state = 'running';
  stage.focus({ preventScroll: true });
}

function stop(): void {
  handle?.dispose();
  handle = null;
  const stage = stageOf();
  if (!stage) return;
  stage.dataset.state = 'idle';
  stage.querySelector<HTMLButtonElement>('[data-machine-start]')?.focus({ preventScroll: true });
}

function wire(): void {
  for (const button of document.querySelectorAll<HTMLButtonElement>('[data-machine-start]')) {
    button.hidden = false;
    button.addEventListener('click', () => void start(button.dataset.machineRoute ?? '', button.dataset.machineSession === 'true'));
  }
}

document.addEventListener('astro:page-load', wire);
document.addEventListener('astro:before-swap', stop);
