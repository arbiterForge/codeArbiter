/** Pure mappings from existing adapter facts onto the sidebar's input shape
 * (spec pi-sidebar-panel AC-6). The sidebar adds no bridge traffic: the session,
 * subagents and workspace panels reuse the footer's already-gathered facts, and
 * the todos panel reuses the native plan session ledger. Trust gating is
 * inherited — the footer only carries git facts under affirmative trust, and a
 * plan session only exists in a trusted parent. */

import type { FooterInput } from "./footer.ts";
import type { PlanSessionState } from "./plan-mode.ts";
import type { SidebarInput, SidebarSession, SidebarTodoRow } from "./sidebar.ts";

function sessionFromFooter(footer: FooterInput): SidebarSession | undefined {
  const context = footer.context;
  const contextPercent = context !== undefined
    && typeof context.windowTokens === "number" && Number.isFinite(context.windowTokens)
    && context.windowTokens > 0
    && typeof context.usedTokens === "number" && Number.isFinite(context.usedTokens)
    ? (context.usedTokens / context.windowTokens) * 100
    : undefined;
  const session: SidebarSession = {
    ...(footer.model?.name === undefined ? {} : { model: footer.model.name }),
    ...(footer.model?.thinking === undefined ? {} : { thinkingLevel: footer.model.thinking }),
    ...(contextPercent === undefined ? {} : { contextPercent }),
    ...(footer.session === undefined ? {} : {
      inputTokens: footer.session.inputTokens,
      outputTokens: footer.session.outputTokens,
      costUsd: footer.session.costUsd,
    }),
    ...(footer.sparkline === undefined || footer.sparkline.length === 0 ? {} : { burn: footer.sparkline }),
  };
  return Object.keys(session).length === 0 ? undefined : session;
}

/** Map the footer's display facts onto sidebar panels. Panels whose source is
 * absent are omitted entirely so the renderer drops them. */
export function sidebarInputFromFooter(footer: FooterInput | undefined): SidebarInput {
  if (footer === undefined) return {};
  const session = sessionFromFooter(footer);
  const subagents = footer.activity !== undefined && footer.activity.length > 0
    ? footer.activity.map((item) => ({
      kind: item.kind,
      label: item.label,
      state: item.state,
      ...(item.ageSeconds === undefined ? {} : { ageSeconds: item.ageSeconds }),
    }))
    : undefined;
  const workspace = footer.git === undefined ? undefined : {
    cwd: footer.folder,
    ...(footer.git.repository === undefined ? {} : { repository: footer.git.repository }),
    ...(footer.git.dirty === undefined ? {} : { dirty: footer.git.dirty }),
  };
  return {
    ...(session === undefined ? {} : { session }),
    ...(subagents === undefined ? {} : { subagents }),
    ...(workspace === undefined ? {} : { workspace }),
  };
}

const TODO_STATE = Object.freeze({
  PENDING: "open",
  IN_PROGRESS: "active",
  ACCEPTED: "done",
} as const);

/** Project the native plan ledger onto todo rows; no session or an empty
 * ledger yields no panel. */
export function sidebarTodosFromPlan(
  state: PlanSessionState | undefined,
): readonly SidebarTodoRow[] | undefined {
  const tasks = state?.activePlan.tasks;
  if (tasks === undefined || tasks.length === 0) return undefined;
  return tasks.map((task) => ({ text: task.id, state: TODO_STATE[task.status] }));
}
