import { readFooterStatusSnapshot, updateFooterUsageSnapshot } from "./bridge.ts";
import type {
  BridgePort,
  ExtensionContextPort,
  ParentPiPort,
  PiFooterActivationState,
  PiFooterDataLifecyclePort,
  PiFooterFactoryPort,
  PiUsageSnapshotPortResult,
} from "./contracts.ts";
import { adaptPiFooterState } from "./footer-state.ts";
import { renderFooter } from "./footer.ts";
import type { FooterTextMetrics } from "./footer.ts";
import type { ActivitySnapshotSource } from "./activity.ts";

export function setArbiterStatus(
  context: Pick<ExtensionContextPort, "ui">,
  text: string | undefined,
): void {
  context.ui.setStatus("codearbiter", text);
}

const FOOTER_DIAGNOSIS = "codeArbiter footer unavailable; native Pi footer restored; run /ca-doctor";
function interactiveContext(context: ExtensionContextPort): boolean {
  return context.hasUI === true && (context.mode === undefined || context.mode === "tui");
}

function notifyFooterFailure(context: ExtensionContextPort): void {
  try { context.ui.notify(FOOTER_DIAGNOSIS, "warning"); } catch { /* UI failure remains fail-soft. */ }
}

function requestRender(tui: { requestRender(): void } | undefined): void {
  try { tui?.requestRender(); } catch { /* Rendering remains independently fail-soft. */ }
}

function affirmativeTrust(context: ExtensionContextPort): boolean {
  try { return context.isProjectTrusted?.() === true; } catch { return false; }
}

function boundedAsciiFallback(width: unknown): string {
  const safeWidth = typeof width === "number" && Number.isFinite(width) && width > 0
    ? Math.min(160, Math.floor(width))
    : 0;
  return "codeArbiter footer unavailable".slice(0, safeWidth);
}

export interface PiFooterRefreshOptions {
  readonly activation: PiFooterActivationState;
  readonly prepareBridge?: (cwd: string, context: ExtensionContextPort) => Promise<void> | void;
  readonly readUpdateVersion?: () => Promise<string | undefined>;
}

/** Session-local owner for the parent interactive footer. No state survives shutdown. */
export class PiFooterLifecycle {
  private generation = 0;
  private context: ExtensionContextPort | undefined;
  private footerData: PiFooterDataLifecyclePort | undefined;
  private tui: { requestRender(): void } | undefined;
  private usageCursor = -1;
  private usageSnapshot: PiUsageSnapshotPortResult | undefined;
  private governance: Awaited<ReturnType<typeof readFooterStatusSnapshot>>;
  private updateVersion: string | undefined;
  private activationEnabled = false;
  private expected = false;
  private installed = false;
  private refreshQueue: Promise<void> = Promise.resolve();

  constructor(
    private readonly pi: ParentPiPort,
    private readonly bridge: BridgePort,
    private readonly loadMetrics: (() => Promise<FooterTextMetrics>) | undefined,
    private readonly currentActivity?: () => ActivitySnapshotSource | undefined,
  ) {}

  requestActivityRender(): void {
    requestRender(this.tui);
  }

  health(): Readonly<{ expected: boolean; initialized: boolean }> {
    return Object.freeze({
      expected: this.expected,
      initialized: this.installed && this.context !== undefined,
    });
  }

  async start(context: ExtensionContextPort): Promise<void> {
    this.dispose();
    this.generation += 1;
    const generation = this.generation;
    this.usageCursor = -1;
    this.usageSnapshot = undefined;
    this.governance = undefined;
    this.updateVersion = undefined;
    this.activationEnabled = false;
    if (!interactiveContext(context)) return;
    this.expected = true;
    const setFooter = context.ui.setFooter;
    if (typeof setFooter !== "function" || this.loadMetrics === undefined) {
      notifyFooterFailure(context);
      return;
    }
    this.context = context;
    let metrics: FooterTextMetrics;
    try {
      metrics = await this.loadMetrics();
      if (typeof metrics.visibleWidth !== "function" || typeof metrics.truncateToWidth !== "function") {
        throw new Error("invalid footer metrics");
      }
    } catch {
      if (this.context === context && generation === this.generation) {
        try { setFooter.call(context.ui, undefined); } catch { /* Native restore was attempted. */ }
        this.context = undefined;
        notifyFooterFailure(context);
      }
      return;
    }
    if (this.context !== context || generation !== this.generation) return;
    const factory: PiFooterFactoryPort = (tui, _theme, footerData) => {
      if (this.context !== context) {
        return { render: () => [], invalidate: () => undefined };
      }
      this.tui = tui;
      this.footerData = footerData;
      let unsubscribe: (() => void) | undefined;
      try {
        const result = footerData.onBranchChange?.(() => requestRender(tui));
        if (typeof result === "function") unsubscribe = result;
      } catch {
        unsubscribe = undefined;
      }
      return {
        invalidate: () => undefined,
        render: (width) => {
          try {
            let activity: ActivitySnapshotSource | undefined;
            try { activity = this.currentActivity?.(); } catch { activity = undefined; }
            const input = adaptPiFooterState({
              pi: this.pi,
              context,
              footerData,
              ...(this.usageSnapshot === undefined ? {} : { usageSnapshot: this.usageSnapshot }),
              ...(this.updateVersion === undefined ? {} : { updateVersion: this.updateVersion }),
              ...(activity === undefined ? {} : { activity }),
            });
            const enriched = this.governance === undefined || !this.activationEnabled || !affirmativeTrust(context)
              ? input
              : {
                ...input,
                governance: {
                  stage: this.governance.stage,
                  tasks: this.governance.tasks,
                  questions: this.governance.questions,
                  overrides: this.governance.overrides,
                  sprint: this.governance.sprint,
                  dev: this.governance.dev,
                  ...(this.governance.prune === undefined ? {} : { prune: this.governance.prune }),
                },
              };
            const rendered = renderFooter(enriched, {
              width,
              noColor: Object.prototype.hasOwnProperty.call(process.env, "NO_COLOR"),
            }, metrics);
            return rendered ? rendered.split("\n") : [boundedAsciiFallback(width)];
          } catch {
            return [boundedAsciiFallback(width)];
          }
        },
        dispose: () => {
          try { unsubscribe?.(); } catch { /* Host subscription disposal is fail-soft. */ }
          if (this.tui === tui) this.tui = undefined;
          if (this.footerData === footerData) this.footerData = undefined;
        },
      };
    };
    try {
      setFooter.call(context.ui, factory);
      this.installed = true;
    } catch {
      try { setFooter.call(context.ui, undefined); } catch { /* Native restore was attempted. */ }
      this.context = undefined;
      this.installed = false;
      notifyFooterFailure(context);
    }
  }

  refresh(context: ExtensionContextPort, options: PiFooterRefreshOptions): Promise<void> {
    const generation = this.generation;
    const scheduled = this.refreshQueue.then(async () => await this.runRefresh(context, options, generation));
    this.refreshQueue = scheduled.catch(() => undefined);
    return scheduled;
  }

  private async runRefresh(
    context: ExtensionContextPort,
    options: PiFooterRefreshOptions,
    generation: number,
  ): Promise<void> {
    if (this.context !== context || !this.installed || generation !== this.generation) return;
    this.activationEnabled = options.activation.enabled === true;
    try { await options.prepareBridge?.(context.cwd, context); } catch { /* Missing bridge omits bridge segments. */ }
    if (this.context !== context || generation !== this.generation) return;

    const usagePromise = updateFooterUsageSnapshot(this.bridge, context, this.usageCursor, { maxRanges: 1 });
    const governancePromise = readFooterStatusSnapshot(this.bridge, context, options.activation);
    const [usage, governance] = await Promise.allSettled([
      usagePromise,
      governancePromise,
    ]);
    const updateVersion = options.readUpdateVersion === undefined
      ? undefined
      : await Promise.resolve().then(async () => await options.readUpdateVersion!())
        .then((value) => ({ status: "fulfilled" as const, value }))
        .catch(() => ({ status: "rejected" as const }));
    if (this.context !== context || generation !== this.generation) return;
    if (usage.status === "fulfilled") {
      this.usageCursor = usage.value.acknowledgedCursor;
      if (usage.value.snapshot !== undefined) this.usageSnapshot = usage.value.snapshot;
    }
    if (options.activation.enabled !== true || !affirmativeTrust(context)) this.governance = undefined;
    else if (governance.status === "fulfilled" && governance.value !== undefined) this.governance = governance.value;
    if (updateVersion?.status === "fulfilled") this.updateVersion = updateVersion.value;
    requestRender(this.tui);
  }

  dispose(): void {
    const context = this.context;
    this.generation += 1;
    this.context = undefined;
    this.footerData = undefined;
    this.tui = undefined;
    this.usageCursor = -1;
    this.usageSnapshot = undefined;
    this.governance = undefined;
    this.updateVersion = undefined;
    this.activationEnabled = false;
    this.expected = false;
    this.refreshQueue = Promise.resolve();
    if (!this.installed || context === undefined) {
      this.installed = false;
      return;
    }
    this.installed = false;
    try { context.ui.setFooter?.(undefined); } catch { notifyFooterFailure(context); }
  }
}
