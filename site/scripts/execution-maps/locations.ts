/** Site addresses only. Canonical workflow behavior remains in the source-traced models. */
import type { WorkflowDefinition } from './workflows';

const guideMaps: Readonly<Record<string, { id: string; path?: string }>> = {
  sprint: { id: 'sprint-execution-map' },
  dependency: { id: 'dependency-execution-map' },
  adr: { id: 'adr-execution-map' },
  release: { id: 'release-execution-map' },
  greenfield: { id: 'init-greenfield', path: '/guides/opt-in-a-repo/' },
  brownfield: { id: 'init-brownfield', path: '/guides/opt-in-a-repo/' },
};

/** The first chapter comes from the model; only its embedding is registered here. */
export function workflowMapHref(workflow: WorkflowDefinition): string {
  const location = guideMaps[workflow.id];
  const chapter = workflow.map.chapters[0];
  if (!location || !chapter) throw new Error(`Unregistered workflow map location: ${workflow.id}`);
  return `${location.path ?? workflow.guide}#${location.id}-${chapter.id}`;
}
