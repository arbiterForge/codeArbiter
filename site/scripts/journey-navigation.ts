/** Reader journeys; reference ordering stays owned by the generated catalog. */
import { conceptGroups, conceptBackground } from './concept-directory';
import type { ReferenceSidebarGroup as Group, ReferenceSidebarLink as Link } from './reference-sidebar';

export const primaryNavigation = [
  { label: 'Get started', slug: 'overview' },
  { label: 'Guides', slug: 'guides' },
  { label: 'Concepts', slug: 'concepts' },
  { label: 'Academy', slug: 'academy' },
  { label: 'Reference', slug: 'reference' },
  { label: 'Trust', slug: 'trust' },
] as const;
/** Create a reader-facing sidebar destination. */
const link = (label: string, slug: string): Link => ({ label, slug });
/** Group destinations under a collapsible journey heading. */
const group = (label: string, items: Array<Group | Link>, collapsed = true): Group => ({ label, items, collapsed });


/** Concise sidebar labels; group membership and order share the Concepts directory. */
const conceptLabels: Record<string, string> = {
  'concepts/workflow-routes': 'Compare Workflow Routes',
  'concepts/gated-lanes': 'The Gated-Lane Model',
  'concepts/artifacts': 'Project Knowledge and Artifacts',
  'concepts/test-first': 'Test-First Evidence',
  'concepts/smarts': 'SMARTS',
  'concepts/adrs': 'ADRs and the Decision Log',
  'concepts/provenance-drift': 'Provenance and Context Drift',
  'concepts/jit-context-injection': 'Just-in-Time Context Injection',
  'concepts/persona-and-context': 'The Persona-Register Split',
  'concepts/checkpoints': 'Checkpoints',
  'concepts/auditability': 'Auditability',
  'enforcement': 'Enforcement & Security',
};

/** Order reader journeys while retaining the generated Academy and reference inventories. */
export function buildJourneySidebar(reference: Group[], academy: Group[]): Group[] {
  return [
    group('Get started', [
      link('What Is codeArbiter', 'overview'), link('See the Product in Action', 'product-tour'),
      link('Choose Your Host', 'getting-started/choose-your-host'), link('Install', 'getting-started/install'),
      link('Initialize a Repository', 'guides/opt-in-a-repo'),
      link('Protect Your First Repository', 'getting-started/quickstart'),
      link('Complete One Feature', 'guides/first-feature'), link('Learning Path', 'learn'), link('FAQ', 'faq'),
    ], false),
    group('Guides', [
      link('Choose a Task', 'guides'),
      group('Initialize projects', [link('Plan a New Project', 'guides/plan-a-new-project'), link('Understand Existing Code', 'guides/understand-an-existing-project')]),
      group('Make a change', [link('Review Specs and Plans', 'guides/review-artifacts'), link('Build a Feature End to End', 'guides/feature-lane'), link('Investigate and Fix a Defect', 'guides/investigate-and-fix'), link('Run an Autonomous Sprint', 'guides/autonomous-sprints')]),
      group('Review and ship', [link('Review and Ship a Change', 'guides/review-and-ship'), link('Add a Dependency Safely', 'guides/adding-a-dependency'), link('Record an Architecture Decision', 'guides/recording-adrs'), link('Review a Change', 'reference/commands/review'), link('Commit', 'reference/commands/commit'), link('Open a Pull Request', 'reference/commands/pr'), link('Release Your Project', 'guides/releasing-a-version')]),
      group('Operate and recover', [link('Return to a Project', 'guides/return-to-a-project'), link('Resume and Recover', 'guides/resume-and-recover'), link('Troubleshooting', 'guides/troubleshooting'), link('Set Up the Statusline', 'guides/the-statusline'), link('Override a Gate Safely', 'guides/overriding-a-gate'), link('Uninstall & Disable', 'guides/uninstalling')]),
      group('Feature Forge', [link('What Is the Feature Forge', 'feature-forge/overview'), link("What's in the Forge", 'feature-forge/whats-in-the-forge'), link('Use a Preview Feature', 'feature-forge/using-preview-features'), link('Explore Untrusted Code', 'guides/ca-sandbox')]),
    ]),
    group('Concepts', [
      link('Concept Map', 'concepts'),
      ...conceptGroups.map(section => group(section.title,
        section.items.map(item => link(conceptLabels[item.slug], item.slug)))),
      group('Research and history', conceptBackground.map(item => link(item.title, item.slug))),
    ]),
    group('Academy', [link('Academy Overview', 'academy'), ...academy]),
    group('Reference', [link('All Reference', 'reference'), link('The .codearbiter/ Directory', 'codearbiter-directory'), link('Configuration', 'reference/configuration'), link('Glossary', 'glossary'), link('Hooks Reference', 'hooks'), link('Hook Gates', 'reference/hooks-gates'), ...reference]),
    group('Trust', [link('Trust & Lifecycle', 'trust'), link('Enforcement & Security', 'enforcement'), link('Supported Environments', 'getting-started/compatibility'), link('Claude Code + Codex Evidence', 'getting-started/claude-code-and-codex'), link('Pi Support and Boundaries', 'getting-started/pi'), link('Changelog', 'changelog'), link('Uninstall & Disable', 'guides/uninstalling')]),
  ];
}
