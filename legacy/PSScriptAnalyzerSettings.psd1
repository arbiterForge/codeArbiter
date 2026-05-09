@{
    # PSScriptAnalyzer settings for cove-apps-fusion
    # This file satisfies the pre-commit PSScriptAnalyzer hook.
    # PowerShell scripts in this repo are limited to Ansible helper scripts and
    # developer tooling — not production code paths.

    Severity = @('Error', 'Warning')

    ExcludeRules = @(
        # Allow positional parameters in short dev scripts
        'PSAvoidUsingPositionalParameters'
    )
}
