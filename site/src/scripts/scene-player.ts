/** scene-player.ts - play the site's step-through scenes (SceneStage.astro).
 *
 * A scene is complete as HTML: every part drawn, every step listed. This player adds the
 * sequence. It lights the parts of one step at a time, moves a token along the handoffs and
 * fires the step's verdict (refuse, allow, decide, record) at its focus.
 *
 * Rules (DESIGN-SYSTEM.md "Scenes"):
 * - Under prefers-reduced-motion the player does not start; the static scene stays.
 * - Only a scene marked data-autoplay plays on its own, and only while at least a third of it
 *   is on screen and the tab is visible. It always shows a pause control.
 * - Any control use stops autoplay and leaves the reader in charge.
 * - No storage, history or network use. Astro's client router keeps this module alive, so
 *   players are destroyed before every page swap and created again on each page load.
 */

interface StepPlan {
  focus: string;
  travel: string[];
  verdict: string;
  ms: number;
}

const HOLD_AT_END = 4600;
const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

class ScenePlayer {
  private readonly plan: StepPlan[];
  private readonly elements: SVGElement[];
  private readonly steps: HTMLElement[];
  private readonly dots: HTMLButtonElement[];
  private readonly toggle: HTMLButtonElement;
  private readonly toggleLabel: HTMLElement;
  private readonly counter: HTMLElement | null;
  private readonly controls: HTMLElement;
  private readonly abort = new AbortController();
  private readonly timers = new Set<number>();
  private observer: IntersectionObserver | null = null;
  private index = 0;
  private generation = 0;
  private frame = 0;
  private playing = false;
  private autoplay: boolean;
  private onScreen = false;

  constructor(private readonly root: HTMLElement) {
    this.plan = JSON.parse(root.dataset.plan ?? '[]') as StepPlan[];
    this.elements = [...root.querySelectorAll<SVGElement>('[data-el]')];
    this.steps = [...root.querySelectorAll<HTMLElement>('.ca-scene__step')];
    this.dots = [...root.querySelectorAll<HTMLButtonElement>('[data-scene-go]')];
    this.toggle = root.querySelector<HTMLButtonElement>('[data-scene-toggle]')!;
    this.toggleLabel = root.querySelector<HTMLElement>('[data-scene-toggle-label]')!;
    this.counter = root.querySelector<HTMLElement>('[data-scene-num]');
    this.controls = root.querySelector<HTMLElement>('[data-scene-controls]')!;
    this.autoplay = root.dataset.autoplay === 'true';

    const { signal } = this.abort;
    this.toggle.addEventListener('click', () => (this.playing ? this.pause() : this.play()), { signal });
    root.querySelector('[data-scene-prev]')?.addEventListener('click', () => this.take(this.index - 1), { signal });
    root.querySelector('[data-scene-next]')?.addEventListener('click', () => this.take(this.index + 1), { signal });
    for (const dot of this.dots) dot.addEventListener('click', () => this.take(Number(dot.dataset.sceneGo)), { signal });
    this.controls.addEventListener('keydown', (event) => this.onKey(event), { signal });
    document.addEventListener('visibilitychange', () => this.sync(), { signal });

    root.dataset.js = 'on';
    this.controls.hidden = false;
    this.show(0);
    this.label();

    if (this.autoplay) {
      this.observer = new IntersectionObserver(([entry]) => {
        this.onScreen = entry.isIntersecting;
        this.sync();
      }, { threshold: 0.34 });
      this.observer.observe(root);
    }
  }

  /** The reader takes the steps: autoplay ends for this visit. */
  private take(target: number): void {
    this.autoplay = false;
    this.playing = false;
    this.label();
    const last = this.plan.length - 1;
    this.run(Math.max(0, Math.min(last, target)));
  }

  private onKey(event: KeyboardEvent): void {
    const keys: Record<string, number> = { ArrowLeft: this.index - 1, ArrowRight: this.index + 1, Home: 0, End: this.plan.length - 1 };
    if (!(event.key in keys)) return;
    event.preventDefault();
    this.take(keys[event.key]);
    const dot = this.dots[this.index];
    if (dot && this.controls.contains(document.activeElement) && document.activeElement?.hasAttribute('data-scene-go')) dot.focus();
  }

  play(): void {
    this.playing = true;
    this.label();
    this.run(this.index >= this.plan.length - 1 ? 0 : this.index + 1);
  }

  pause(): void {
    this.autoplay = false;
    this.playing = false;
    this.clearTimers();
    this.label();
  }

  /** Autoplay follows visibility: on screen and tab visible, or not at all. */
  private sync(): void {
    if (!this.autoplay) return;
    const allowed = this.onScreen && document.visibilityState === 'visible';
    if (allowed && !this.playing) {
      this.playing = true;
      this.label();
      this.run(this.index === 0 && !this.root.dataset.started ? 0 : this.index);
    } else if (!allowed && this.playing) {
      this.playing = false;
      this.clearTimers();
      this.label();
    }
  }

  private label(): void {
    this.toggleLabel.textContent = this.playing ? 'Pause' : 'Play';
    this.toggle.dataset.playing = String(this.playing);
  }

  /** Light the parts of step `index`: earlier steps settle, later steps wait in outline. */
  private show(index: number): void {
    this.index = index;
    this.root.dataset.step = String(index);
    const { focus } = this.plan[index];
    for (const element of this.elements) {
      const from = Number(element.dataset.fromStep);
      element.dataset.state = from < index ? 'past' : from === index ? 'active' : 'future';
      element.toggleAttribute('data-focus', element.dataset.el === focus);
      delete element.dataset.verdict;
    }
    this.steps.forEach((step, i) => (i === index ? step.setAttribute('aria-current', 'step') : step.removeAttribute('aria-current')));
    this.dots.forEach((dot, i) => (i === index ? dot.setAttribute('aria-current', 'step') : dot.removeAttribute('aria-current')));
    if (this.counter) this.counter.textContent = String(index + 1);
  }

  private async run(index: number): Promise<void> {
    const generation = ++this.generation;
    this.clearTimers();
    this.root.dataset.started = 'true';
    this.show(index);
    const step = this.plan[index];
    await this.travel(step, generation);
    if (generation !== this.generation) return;
    for (const element of this.elements) {
      if (element.dataset.el === step.focus) element.dataset.verdict = step.verdict;
    }
    if (!this.playing) return;
    const last = index === this.plan.length - 1;
    this.wait(step.ms + (last ? HOLD_AT_END : 0), () => {
      if (generation !== this.generation || !this.playing) return;
      this.run(last ? 0 : index + 1);
    });
  }

  /** Move the token along this step's handoffs in the composition that is showing. */
  private travel(step: StepPlan, generation: number): Promise<void> {
    const svg = [...this.root.querySelectorAll<SVGSVGElement>('.ca-scene__svg')].find((candidate) => candidate.getBoundingClientRect().width > 0);
    const token = svg?.querySelector<SVGGElement>('[data-token]');
    if (!svg || !token || step.travel.length === 0) return Promise.resolve();
    token.dataset.verdict = step.verdict;
    const paths = step.travel
      .map((id) => [...svg.querySelectorAll<SVGPathElement>('path.ca-scene__edge')].find((path) => path.dataset.el === id))
      .filter((path): path is SVGPathElement => Boolean(path));
    return new Promise((resolve) => {
      let leg = 0;
      let started = 0;
      const tick = (now: number) => {
        if (generation !== this.generation) {
          delete token.dataset.on;
          resolve();
          return;
        }
        const path = paths[leg];
        if (!path) {
          delete token.dataset.on;
          resolve();
          return;
        }
        const length = path.getTotalLength();
        const duration = Math.min(1100, Math.max(420, length * 2.6));
        if (!started) started = now;
        const t = Math.min(1, (now - started) / duration);
        const eased = t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
        const point = path.getPointAtLength(length * eased);
        token.setAttribute('transform', `translate(${point.x.toFixed(1)} ${point.y.toFixed(1)})`);
        token.dataset.on = 'true';
        if (t >= 1) {
          leg += 1;
          started = 0;
        }
        this.frame = requestAnimationFrame(tick);
      };
      this.frame = requestAnimationFrame(tick);
    });
  }

  private wait(ms: number, then: () => void): void {
    const timer = window.setTimeout(() => {
      this.timers.delete(timer);
      then();
    }, ms);
    this.timers.add(timer);
  }

  private clearTimers(): void {
    for (const timer of this.timers) clearTimeout(timer);
    this.timers.clear();
  }

  destroy(): void {
    this.generation += 1;
    this.playing = false;
    this.clearTimers();
    cancelAnimationFrame(this.frame);
    this.observer?.disconnect();
    this.abort.abort();
  }
}

const players = new Map<HTMLElement, ScenePlayer>();

function mount(): void {
  if (reducedMotion()) return;
  for (const root of document.querySelectorAll<HTMLElement>('[data-scene]')) {
    if (!players.has(root)) players.set(root, new ScenePlayer(root));
  }
}

function unmount(): void {
  for (const [root, player] of players) {
    player.destroy();
    delete root.dataset.js;
  }
  players.clear();
}

/** A reader who turns on reduced motion mid-visit gets the static scene back. */
matchMedia('(prefers-reduced-motion: reduce)').addEventListener('change', (event) => {
  if (event.matches) {
    for (const [root, player] of players) {
      player.destroy();
      delete root.dataset.js;
      root.querySelector<HTMLElement>('[data-scene-controls]')!.hidden = true;
      for (const element of root.querySelectorAll<HTMLElement | SVGElement>('[data-state], [aria-current]')) {
        delete element.dataset.state;
        delete element.dataset.verdict;
        element.removeAttribute('data-focus');
        element.removeAttribute('aria-current');
      }
    }
    players.clear();
  } else {
    mount();
  }
});

document.addEventListener('astro:page-load', mount);
document.addEventListener('astro:before-swap', unmount);
