severity: medium

page: getting-started/install.md / guides/troubleshooting.md

user_goal: Know how to safely update codeArbiter to a new version.

gap: No page walks a user through the update flow end-to-end. The critical fact — "claude plugin update no-ops on an unchanged version string, leaving a stale payload; uninstall then install is the clean path" — only surfaces buried inside doctor.md's remediation ladder and troubleshooting.md's stale-cache section, never as a first-class "Updating codeArbiter" walkthrough a user would proactively find.

remediation: Add a short "Update the plugin" subsection to install.md or a new guide, stating the uninstall/reinstall pattern up front rather than only as troubleshooting.
