[CmdletBinding(DefaultParameterSetName = 'Production')]
param(
    [Parameter(ParameterSetName = 'Contract')]
    [switch]$ContractOnly,

    [Parameter(Mandatory, ParameterSetName = 'InputAbi')]
    [switch]$InputAbiOnly,

    [Parameter(Mandatory, ParameterSetName = 'Fixture')]
    [string]$FixturePath,

    [Parameter(Mandatory, ParameterSetName = 'PermissionProbeFixture')]
    [string]$PermissionProbeFixturePath,

    [Parameter(Mandatory, ParameterSetName = 'InventoryFixture')]
    [string]$InventoryFixturePath,

    [Parameter(Mandatory, ParameterSetName = 'InventoryProbe')]
    [switch]$InventoryProbe,

    [Parameter(Mandatory, ParameterSetName = 'InventoryProbe')]
    [string]$ProfilePath,

    [Parameter(Mandatory, ParameterSetName = 'InventoryProbe')]
    [string]$InventoryEvidencePath,

    [Parameter(Mandatory, ParameterSetName = 'Production')]
    [string]$ObservationPath,

    [Parameter(Mandatory, ParameterSetName = 'Production')]
    [Parameter(Mandatory, ParameterSetName = 'PermissionProbe')]
    [Parameter(Mandatory, ParameterSetName = 'InventoryProbe')]
    [string]$RuntimePath,

    [Parameter(Mandatory, ParameterSetName = 'Production')]
    [string]$PackagedRuntimePath,

    [Parameter(Mandatory, ParameterSetName = 'Production')]
    [Parameter(Mandatory, ParameterSetName = 'PermissionProbe')]
    [string]$ProofRepoPath,

    [Parameter(Mandatory, ParameterSetName = 'Production')]
    [Parameter(Mandatory, ParameterSetName = 'PermissionProbe')]
    [string]$AuthCanaryPath,

    [Parameter(Mandatory, ParameterSetName = 'PermissionProbe')]
    [switch]$PermissionProbe,

    [Parameter(Mandatory, ParameterSetName = 'PermissionProbe')]
    [string]$SelectedPluginRoot,

    [Parameter(Mandatory, ParameterSetName = 'PermissionProbe')]
    [string]$PermissionEvidencePath,

    [Parameter(Mandatory, ParameterSetName = 'Production')]
    [int]$DesktopProcessId,

    [string]$ContractPath = (Join-Path $PSScriptRoot '..\desktop-proof-boundary.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-Sha256([string]$LiteralPath) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $LiteralPath).Hash.ToLowerInvariant()
}

function Get-TextSha256([string]$Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        -join @($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)) |
            ForEach-Object { $_.ToString('x2') })
    } finally { $algorithm.Dispose() }
}

function Get-Contract {
    $resolved = (Resolve-Path -LiteralPath $ContractPath).Path
    $contract = Get-Content -LiteralPath $resolved -Raw -Encoding utf8 | ConvertFrom-Json
    if ($contract.schema_version -ne 2) { throw 'boundary contract schema_version must be 2' }
    if ($contract.driver.source_path -cne '.github/scripts/Invoke-CodeArbiterDesktopUiDriver.ps1') {
        throw 'boundary contract driver source path is untrusted'
    }
    $root = (Resolve-Path -LiteralPath (Join-Path (Split-Path $resolved -Parent) '..')).Path
    $driver = Join-Path $root $contract.driver.source_path
    if ((Get-Sha256 $driver) -cne $contract.driver.sha256) {
        throw 'tracked desktop driver digest mismatch'
    }
    [pscustomobject]@{ Contract = $contract; Driver = $driver }
}

function Assert-HexSha256([object]$Value, [string]$Label) {
    if ($Value -isnot [string] -or $Value -cnotmatch '^[0-9a-f]{64}$') {
        throw "$Label must be a lowercase SHA-256"
    }
}

function Convert-WindowsEvidencePath([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value) -or $Value.IndexOf([char]0) -ge 0) {
        throw 'Windows evidence path is empty or invalid'
    }
    $normalized = $Value.Replace('/','\')
    if ($normalized -cnotmatch '^[A-Za-z]:\\') {
        throw 'Windows evidence path is not drive-rooted'
    }
    $components = @($normalized.Substring(3).Split('\'))
    if ($components.Count -eq 0 -or @($components | Where-Object {
        [string]::IsNullOrEmpty($_) -or $_ -in @('.','..') -or
        $_.EndsWith(' ') -or $_.EndsWith('.') -or $_ -match '[<>:"|?*\x00-\x1f]'
    }).Count) {
        throw 'Windows evidence path is not canonical'
    }
    $normalized.Substring(0,3) + ($components -join '\')
}

function Assert-PermissionProbeEvidence {
    param([Parameter(Mandatory)]$Evidence)
    if ($Evidence.schema_version -ne 1) { throw 'permission probe schema is invalid' }
    $diagnostics = $Evidence.diagnostics
    if (-not [bool]$diagnostics.config_parse_ok -or [int]$diagnostics.startup_warning_count -ne 0 -or
        -not [bool]$diagnostics.restricted_filesystem -or -not [bool]$diagnostics.restricted_network -or
        [bool]$diagnostics.hooks_enabled -or
        [string]$diagnostics.profile_id -cne [string]$script:Contract.authentication.permission_profile_id) {
        throw 'real Codex permission diagnostics do not match the reviewed fail-closed profile'
    }
    $expected = [ordered]@{
        'plugin-route' = 0; 'proof-input' = 0; 'auth-file' = 1; 'auth-sidecar' = 1
        'other-codex-state' = 1; 'outside-root' = 1; 'network-egress' = 1
    }
    $cases = @($Evidence.cases)
    if ($cases.Count -ne $expected.Count) { throw 'permission probe case set is incomplete' }
    foreach ($id in $expected.Keys) {
        $matches = @($cases | Where-Object { [string]$_.id -ceq $id })
        if ($matches.Count -ne 1 -or [int]$matches[0].exit_code -ne [int]$expected[$id]) {
            throw "real Codex permission probe failed case: $id"
        }
    }
    [ordered]@{
        verdict = 'PASS'
        consumer = 'codex-sandbox-permission-profile'
        permission_profile_id = [string]$diagnostics.profile_id
        restricted_filesystem = [bool]$diagnostics.restricted_filesystem
        restricted_network = [bool]$diagnostics.restricted_network
        hooks_enabled = [bool]$diagnostics.hooks_enabled
        startup_warning_count = [int]$diagnostics.startup_warning_count
    }
}

function Test-ReusableStatePath {
    param([Parameter(Mandatory)][string]$LiteralPath, [Parameter(Mandatory)][string]$Profile)
    $codexRoot = (Convert-WindowsEvidencePath $Profile).TrimEnd('\') + '\.codex'
    $path = Convert-WindowsEvidencePath $LiteralPath
    if (-not $path.StartsWith($codexRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { return $false }
    $relative = $path.Substring($codexRoot.Length + 1).Replace('/', '\')
    $relative -match '^(?i:auth\.json(?:\..+)?|\.credentials\.json(?:\..+)?|credentials\.json(?:\..+)?|(?:credentials|sessions|tokens)(?:\\|$))'
}

function Measure-PostAuthInventory {
    param([Parameter(Mandatory)]$InputValue)
    $doctorProperties = @($InputValue.doctor_checks.PSObject.Properties)
    $invalidDoctorChecks = @($doctorProperties | Where-Object {
        -not $_.Value.PSObject.Properties['status'] -or [string]$_.Value.status -cne 'ok'
    })
    $doctorNames = @($doctorProperties | ForEach-Object Name)
    $missingRequiredChecks = @($script:Contract.authentication.doctor_required_checks | Where-Object {
        [string]$_ -cnotin $doctorNames
    })
    if ($InputValue.schema_version -ne 1 -or [int]$InputValue.doctor_exit_code -ne 0 -or
        [string]$InputValue.doctor_overall_status -notin @('pass','ok') -or
        $doctorProperties.Count -eq 0 -or $invalidDoctorChecks.Count -or $missingRequiredChecks.Count) {
        throw 'post-auth Codex doctor did not complete with an all-ok diagnostic set'
    }
    $profile = Convert-WindowsEvidencePath ([string]$InputValue.profile)
    if ([string]$InputValue.config_text -cnotmatch '(?m)^\s*cli_auth_credentials_store\s*=\s*["'']file["'']\s*$') {
        throw 'Codex auth storage is not explicitly file-only'
    }
    $reusable = @($InputValue.files | Where-Object { Test-ReusableStatePath -LiteralPath ([string]$_) -Profile $profile })
    $expectedAuth = $profile.TrimEnd('\') + '\.codex\auth.json'
    if ($reusable.Count -ne 1 -or (Convert-WindowsEvidencePath ([string]$reusable[0])) -cne $expectedAuth) {
        throw 'post-auth reusable state is not exactly one auth.json file'
    }
    $targets = @($InputValue.credential_targets | Where-Object { [string]$_ -match '(?i)(codex|openai|chatgpt)' })
    if ($targets.Count -ne 0) { throw 'post-auth keyring contains a Codex authentication target' }
    [ordered]@{
        storage_backend = 'file'
        reusable_state_file_count = $reusable.Count
        keyring_target_count = $targets.Count
        doctor_overall_status = [string]$InputValue.doctor_overall_status
        doctor_check_count = $doctorProperties.Count
        doctor_warning_or_failure_count = $invalidDoctorChecks.Count
    }
}

function Convert-Observation {
    param([Parameter(Mandatory)]$InputValue, [Parameter(Mandatory)]$Contract)
    if ($InputValue.schema_version -ne 1) { throw 'driver observation input schema is invalid' }
    if ($InputValue.account.auth_mode -cne 'chatgpt') {
        throw 'desktop account is not authenticated through ChatGPT'
    }
    if ($InputValue.policy.approval_policy -cne 'never' -or
        $InputValue.policy.sandbox_mode -cne 'read-only' -or
        $InputValue.policy.permission_profile_id -cne $Contract.authentication.permission_profile_id -or
        [bool]$InputValue.policy.hooks_enabled -or $InputValue.policy.windows_sandbox -cne 'elevated') {
        throw 'desktop effective approval or sandbox policy is not the reviewed policy'
    }
    if ($InputValue.window.submission_method -cne 'windows-sendinput-unicode' -or
        [int]$InputValue.window.foreground_process_id -ne [int]$InputValue.desktop.process_id) {
        throw 'desktop request was not submitted to the measured foreground process'
    }
    $prompt = [string]$InputValue.window.prompt
    if ($prompt -cne [string]$Contract.route_corpus.desktop_request) {
        throw 'desktop request does not match the fixed non-secret route corpus'
    }
    if ($InputValue.desktop.package_name -cne $Contract.application.package_name -or
        $InputValue.desktop.publisher -cne $Contract.application.publisher -or
        $InputValue.desktop.signature_status -cne 'Valid' -or
        $InputValue.desktop.package_full_name -notmatch $Contract.application.package_full_name_regex) {
        throw 'desktop process is not the verified Store/MSIX package'
    }
    Assert-HexSha256 $InputValue.desktop.process_sha256 'desktop process digest'
    Assert-HexSha256 $InputValue.runtime.process_sha256 'runtime process digest'
    Assert-HexSha256 $InputValue.app_server_process.process_sha256 'app-server process digest'
    Assert-HexSha256 $InputValue.driver_process.executable_sha256 'driver process executable digest'
    Assert-HexSha256 $InputValue.driver_process.script_sha256 'driver script digest'
    Assert-HexSha256 $InputValue.driver_process.command_line_sha256 'driver process command-line digest'
    if ([int]$InputValue.driver_process.process_id -le 0 -or
        [string]$InputValue.driver_process.script_sha256 -cne [string]$Contract.driver.sha256 -or
        [string]$InputValue.driver_process.signature_status -cne 'Valid') {
        throw 'desktop driver process is not bound to the trusted script'
    }
    $ancestorIds = @($InputValue.runtime.process_ancestor_ids | ForEach-Object { [int]$_ })
    $versionMatch = [regex]::Match([string]$InputValue.runtime.version,'^codex-cli ([0-9][0-9A-Za-z.+-]{0,63})$')
    try {
        $candidateActivated = ([DateTimeOffset]$InputValue.desktop.process_start_time).ToUniversalTime()
        $runtimeStarted = ([DateTimeOffset]$InputValue.runtime.process_start_time).ToUniversalTime()
        $appServerStarted = ([DateTimeOffset]$InputValue.app_server_process.process_start_time).ToUniversalTime()
        $driverStarted = ([DateTimeOffset]$InputValue.driver_process.process_start_time).ToUniversalTime()
        $requestSubmitted = ([DateTimeOffset]$InputValue.thread.request_submitted_at).ToUniversalTime()
        $dispatchCompleted = ([DateTimeOffset]$InputValue.thread.dispatch_completed_at).ToUniversalTime()
    } catch { throw 'desktop causal observation timestamp is invalid' }
    if ($InputValue.runtime.process_sha256 -cne $InputValue.runtime.packaged_resource_sha256 -or
        [int]$InputValue.desktop.process_id -notin $ancestorIds -or
        [int]$InputValue.runtime.process_id -le 0 -or
        [int]$InputValue.runtime.eligible_process_count -ne 1 -or
        [int]$InputValue.app_server_process.process_id -le 0 -or
        [int]$InputValue.app_server_process.process_id -eq [int]$InputValue.runtime.process_id -or
        [int]$InputValue.app_server_process.parent_process_id -ne [int]$InputValue.driver_process.process_id -or
        [string]$InputValue.app_server_process.process_sha256 -cne [string]$InputValue.runtime.process_sha256 -or
        $candidateActivated -gt $runtimeStarted -or $runtimeStarted -gt $requestSubmitted -or
        $candidateActivated -gt $appServerStarted -or $appServerStarted -gt $requestSubmitted -or
        $driverStarted -gt $appServerStarted -or
        $dispatchCompleted -lt $requestSubmitted -or
        -not $versionMatch.Success) {
        throw 'desktop runtime is not uniquely and causally bound to the packaged Codex resource and request window'
    }
    if ([int]$InputValue.app_server_query_count -le 0 -or
        [int]$InputValue.app_server_query_count -gt [int]$Contract.channel.max_queries) {
        throw 'desktop app-server query bound was exceeded'
    }
    $items = @($InputValue.thread.items)
    if (@($items | Where-Object { $_.type -ceq 'commandExecution' }).Count -ne 0) {
        throw 'canonical desktop route contains an unexpected command execution'
    }
    $userMessages = @($items | Where-Object { $_.type -ceq 'userMessage' -and $_.text -ceq $prompt })
    if ($userMessages.Count -ne 1) { throw 'canonical desktop thread does not contain the submitted request exactly once' }
    $dispatches = @($items | Where-Object {
        $_.type -ceq 'collabAgentToolCall' -and
        $_.tool -ceq 'spawn_agent' -and
        $_.status -ceq 'completed' -and
        [string]$_.prompt -match '(?i)\bcoverage-auditor\b'
    })
    if ($dispatches.Count -ne 1) { throw 'canonical desktop thread lacks one completed coverage-auditor dispatch' }
    $authIsolation = $InputValue.auth_isolation
    $canaryPath = Convert-WindowsEvidencePath ([string]$authIsolation.canary_path)
    $canaryLeaf = [string]$Contract.authentication.denial_canary_filename
    if (-not $canaryPath.EndsWith("\.codex\$canaryLeaf", [StringComparison]::OrdinalIgnoreCase)) {
        throw 'auth-isolation canary is outside the disposable Codex profile'
    }
    Assert-HexSha256 $authIsolation.canary_content_sha256 'auth-isolation canary digest'
    if ((Get-TextSha256 ([string]$authIsolation.canary_content)) -cne
        [string]$authIsolation.canary_content_sha256) {
        throw 'auth-isolation canary digest does not bind its non-secret content'
    }
    $canaryPrompt = [string]$Contract.authentication.denial_canary_prompt_prefix + ' ' + $canaryPath
    if ([string]$authIsolation.canary_prompt -cne $canaryPrompt) {
        throw 'auth-isolation canary prompt is not the fixed reviewed prompt'
    }
    $canaryItems = @($authIsolation.thread.items)
    $canaryUser = @($canaryItems | Where-Object { $_.type -ceq 'userMessage' -and $_.text -ceq $canaryPrompt })
    $canaryCommands = @($canaryItems | Where-Object { $_.type -ceq 'commandExecution' })
    $expectedCanaryCommand = 'Get-Content -LiteralPath "{0}"' -f $canaryPath
    if ($canaryUser.Count -ne 1 -or $canaryCommands.Count -ne 1 -or
        [string]$canaryCommands[0].command -cne $expectedCanaryCommand -or
        [string]$canaryCommands[0].status -cne 'failed' -or
        [int]$canaryCommands[0].exitCode -eq 0 -or
        [string]$canaryCommands[0].aggregatedOutput -notmatch '(?i)(denied|not permitted|sandbox)' -or
        [string]$canaryCommands[0].aggregatedOutput -like ('*' + [string]$authIsolation.canary_content + '*')) {
        throw 'exact desktop auth-isolation canary read was not observably denied'
    }
    $dispatchCanonical = 'codearbiter.desktop-dispatch.v1|spawn_agent|coverage-auditor|completed'
    $canaryCommandSha256 = Get-TextSha256 $expectedCanaryCommand
    $processCanonical = 'codearbiter.desktop-process-chain.v1|{0}|{1}|{2}' -f
        $InputValue.desktop.process_id, $InputValue.runtime.process_id, ($ancestorIds -join ',')
    [ordered]@{
        test_result = 'SUCCEEDED'
        auth_mode = 'chatgpt'
        effective_approval = 'never'
        effective_sandbox = 'read-only'
        permission_profile_id = [string]$InputValue.policy.permission_profile_id
        hooks_enabled = [bool]$InputValue.policy.hooks_enabled
        windows_sandbox = [string]$InputValue.policy.windows_sandbox
        auth_canary_denied = $true
        auth_canary_content_observed = $false
        auth_canary_path_sha256 = Get-TextSha256 $canaryPath
        auth_canary_content_sha256 = [string]$authIsolation.canary_content_sha256
        request_sha256 = Get-TextSha256 $prompt
        thread_id_sha256 = Get-TextSha256 ([string]$InputValue.thread.id)
        desktop_process_id = [int]$InputValue.desktop.process_id
        desktop_process_sha256 = [string]$InputValue.desktop.process_sha256
        package_full_name = [string]$InputValue.desktop.package_full_name
        package_publisher = [string]$InputValue.desktop.publisher
        runtime_process_id = [int]$InputValue.runtime.process_id
        runtime_parent_process_id = [int]$InputValue.runtime.parent_process_id
        runtime_process_sha256 = [string]$InputValue.runtime.process_sha256
        app_server_process_id = [int]$InputValue.app_server_process.process_id
        app_server_parent_process_id = [int]$InputValue.app_server_process.parent_process_id
        app_server_process_sha256 = [string]$InputValue.app_server_process.process_sha256
        app_server_process_started_at = $appServerStarted.ToString('o')
        process_chain_sha256 = Get-TextSha256 $processCanonical
        runtime_version = [string]$versionMatch.Groups[1].Value
        eligible_runtime_process_count = [int]$InputValue.runtime.eligible_process_count
        driver_process_id = [int]$InputValue.driver_process.process_id
        driver_parent_process_id = [int]$InputValue.driver_process.parent_process_id
        driver_process_executable_sha256 = [string]$InputValue.driver_process.executable_sha256
        driver_process_signature_status = [string]$InputValue.driver_process.signature_status
        driver_process_command_line_sha256 = [string]$InputValue.driver_process.command_line_sha256
        driver_process_started_at = $driverStarted.ToString('o')
        driver_script_sha256 = [string]$InputValue.driver_process.script_sha256
        driver_script_path = Convert-WindowsEvidencePath ([string]$InputValue.driver_process.script_path)
        runtime_process_started_at = $runtimeStarted.ToString('o')
        candidate_activated_at = $candidateActivated.ToString('o')
        request_submitted_at = $requestSubmitted.ToString('o')
        dispatch_completed_at = $dispatchCompleted.ToString('o')
        canary_command_sha256 = $canaryCommandSha256
        app_server_query_count = [int]$InputValue.app_server_query_count
        dispatch_agent = 'coverage-auditor'
        dispatch_sha256 = Get-TextSha256 $dispatchCanonical
        raw_content_persisted = $false
    }
}

function Start-AppServerReader([string]$Executable) {
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Executable
    $start.Arguments = 'app-server --stdio'
    $start.UseShellExecute = $false
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.CreateNoWindow = $true
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    if (-not $process.Start()) { throw 'could not start the measured app-server reader' }
    $process
}

function Invoke-ProcessCapture {
    param(
        [Parameter(Mandatory)][string]$Executable,
        [Parameter(Mandatory)][string[]]$ArgumentList,
        [int]$TimeoutSeconds = 30
    )
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $Executable
    $start.UseShellExecute = $false
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.CreateNoWindow = $true
    foreach ($argument in $ArgumentList) { $null = $start.ArgumentList.Add($argument) }
    $process = [Diagnostics.Process]::new(); $process.StartInfo = $start
    try {
        if (-not $process.Start()) { throw 'could not start bounded Codex diagnostic process' }
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill($true); throw 'bounded Codex diagnostic process timed out'
        }
        [pscustomobject]@{
            ExitCode = $process.ExitCode
            Stdout = $stdoutTask.GetAwaiter().GetResult()
            Stderr = $stderrTask.GetAwaiter().GetResult()
        }
    } finally { $process.Dispose() }
}

function Invoke-SandboxReadCase {
    param(
        [Parameter(Mandatory)][string]$Runtime,
        [Parameter(Mandatory)][string]$WorkingDirectory,
        [Parameter(Mandatory)][string]$LiteralPath,
        [Parameter(Mandatory)][string]$Id
    )
    $escaped = $LiteralPath.Replace("'", "''")
    $result = Invoke-ProcessCapture -Executable $Runtime -TimeoutSeconds 20 -ArgumentList @(
        'sandbox','--disable','hooks','-P',[string]$script:Contract.authentication.permission_profile_id,
        '-C',$WorkingDirectory,'powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',
        "Get-Content -LiteralPath '$escaped' -Raw -ErrorAction Stop | Out-Null"
    )
    [pscustomobject]@{ id=$Id; exit_code=if($result.ExitCode -eq 0){0}else{1} }
}

function Invoke-RealPermissionProbe {
    param(
        [Parameter(Mandatory)][string]$Runtime,
        [Parameter(Mandatory)][string]$Repo,
        [Parameter(Mandatory)][string]$PluginRoot,
        [Parameter(Mandatory)][string]$Canary
    )
    $repoPath = [IO.Path]::GetFullPath($Repo)
    $pluginPath = [IO.Path]::GetFullPath($PluginRoot)
    $canaryPath = [IO.Path]::GetFullPath($Canary)
    $routePath = Join-Path $pluginPath ([string]$script:Contract.route_corpus.paths[0])
    $proofPath = Join-Path $repoPath 'desktop-proof-fixture.ps1'
    foreach ($path in @($routePath,$proofPath,$canaryPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw 'permission probe input is missing' }
    }

    $strict = Invoke-ProcessCapture -Executable $Runtime -ArgumentList @('--strict-config','--version')
    if ($strict.ExitCode -ne 0) { throw 'Codex strict configuration parsing failed' }
    $startupWarnings = @($strict.Stderr -split "`r?`n" |
        Where-Object { $_ -match '(?i)\bwarning\b|unknown configuration|deprecated' }).Count

    $reader = Start-AppServerReader $Runtime
    try {
        $script:NextRequestId = 10
        $null = Send-AppServerRequest $reader 1 'initialize' @{
            clientInfo = @{ name='codearbiter-permission-probe'; title='CodeArbiter permission probe'; version='1.0.0' }
            capabilities = @{ experimentalApi=$false }
        }
        $reader.StandardInput.WriteLine('{"method":"initialized"}'); $reader.StandardInput.Flush()
        $policy = Send-AppServerRequest $reader 2 'config/read' @{ cwd=$repoPath; includeLayers=$false }
    } finally {
        if ($reader -and -not $reader.HasExited) { $reader.Kill(); $reader.WaitForExit(5000) }
        if ($reader) { $reader.Dispose() }
    }
    $hooksEnabled = $false
    if ($policy.config.features -and $policy.config.features.PSObject.Properties.Name -contains 'hooks') {
        $hooksEnabled = [bool]$policy.config.features.hooks
    }
    $windowsSandbox = if ($policy.config.windows) { [string]$policy.config.windows.sandbox } else { '' }
    $cases = @(
        Invoke-SandboxReadCase $Runtime $repoPath $routePath 'plugin-route'
        Invoke-SandboxReadCase $Runtime $repoPath $proofPath 'proof-input'
        Invoke-SandboxReadCase $Runtime $repoPath (Join-Path $env:USERPROFILE '.codex\auth.json') 'auth-file'
        Invoke-SandboxReadCase $Runtime $repoPath ((Join-Path $env:USERPROFILE '.codex\auth.json') + '.lock') 'auth-sidecar'
        Invoke-SandboxReadCase $Runtime $repoPath (Join-Path $env:USERPROFILE '.codex\config.toml') 'other-codex-state'
        Invoke-SandboxReadCase $Runtime $repoPath (Join-Path $env:SystemRoot 'System32\drivers\etc\hosts') 'outside-root'
    )
    $networkRun = Invoke-ProcessCapture -Executable $Runtime -TimeoutSeconds 20 -ArgumentList @(
        'sandbox','--disable','hooks','-P',[string]$script:Contract.authentication.permission_profile_id,
        '-C',$repoPath,'powershell.exe','-NoLogo','-NoProfile','-NonInteractive','-Command',
        '$client=[Net.Sockets.TcpClient]::new();try{$client.Connect("1.1.1.1",443);exit 0}catch{exit 1}finally{$client.Dispose()}'
    )
    $cases += [pscustomobject]@{id='network-egress';exit_code=if($networkRun.ExitCode-eq 0){0}else{1}}
    $filesystemRestricted = @($cases | Where-Object { $_.id -in @('auth-file','auth-sidecar','other-codex-state','outside-root') -and $_.exit_code -ne 1 }).Count -eq 0
    $networkRestricted = @($cases | Where-Object { $_.id -ceq 'network-egress' -and $_.exit_code -eq 1 }).Count -eq 1
    $evidence = [pscustomobject]@{
        schema_version = 1
        diagnostics = [pscustomobject]@{
            config_parse_ok = ($strict.ExitCode -eq 0)
            startup_warning_count = $startupWarnings
            restricted_filesystem = $filesystemRestricted
            restricted_network = $networkRestricted
            hooks_enabled = $hooksEnabled
            profile_id = [string]$policy.config.default_permissions
            windows_sandbox = $windowsSandbox
        }
        cases = $cases
    }
    if ($evidence.diagnostics.windows_sandbox -cne 'elevated') {
        throw 'Codex permission profile is not using the elevated Windows sandbox backend'
    }
    Assert-PermissionProbeEvidence -Evidence $evidence
}

function Read-AppServerResponse($Process, [int]$Id, [int]$TimeoutSeconds = 15) {
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $task = $Process.StandardOutput.ReadLineAsync()
        $remaining = [Math]::Max(1,[int]($deadline - [DateTime]::UtcNow).TotalMilliseconds)
        if (-not $task.Wait($remaining)) { throw 'app-server reader timed out' }
        $line = $task.Result
        if ($null -eq $line) { throw 'app-server reader closed unexpectedly' }
        try { $message = $line | ConvertFrom-Json } catch { continue }
        if ($message.id -eq $Id) {
            if ($null -ne $message.error) { throw 'app-server reader returned an error' }
            return $message.result
        }
    }
    throw 'app-server reader timed out'
}

function Send-AppServerRequest($Process, [int]$Id, [string]$Method, $Params) {
    $script:AppServerQueryCount++
    if ($script:AppServerQueryCount -gt $script:AppServerMaxQueries) {
        throw 'desktop app-server query bound was exceeded'
    }
    $request = [ordered]@{ id = $Id; method = $Method; params = $Params } |
        ConvertTo-Json -Depth 8 -Compress
    $Process.StandardInput.WriteLine($request)
    $Process.StandardInput.Flush()
    Read-AppServerResponse $Process $Id
}

function Wait-ObservedThread($Process, [string[]]$BeforeIds, [ValidateSet('canary','route')][string]$Kind) {
    $deadline = [DateTime]::UtcNow.AddSeconds([int]$script:Contract.channel.timeout_seconds)
    do {
        Start-Sleep -Seconds 2
        $listed = Send-AppServerRequest $Process $script:NextRequestId 'thread/list' @{
            limit = 100; useStateDbOnly = $true
        }
        $script:NextRequestId++
        $new = @($listed.data | Where-Object { $_.id -notin $BeforeIds })
        if ($new.Count -eq 1) {
            $read = Send-AppServerRequest $Process $script:NextRequestId 'thread/read' @{
                threadId = $new[0].id; includeTurns = $true
            }
            $script:NextRequestId++
            $flat = @($read.thread.turns | ForEach-Object { $_.items })
            $complete = if ($Kind -ceq 'canary') {
                @($flat | Where-Object {
                    $_.type -ceq 'commandExecution' -and $_.status -in @('completed','failed')
                }).Count -gt 0
            } else {
                @($flat | Where-Object {
                    $_.type -ceq 'collabAgentToolCall' -and $_.status -ceq 'completed'
                }).Count -gt 0
            }
            if ($complete) { return [pscustomobject]@{ id = $read.thread.id; items = $flat } }
        } elseif ($new.Count -gt 1) {
            throw 'more than one desktop thread appeared inside one bounded observation window'
        }
    } while ([DateTime]::UtcNow -lt $deadline)
    throw "desktop $Kind thread did not complete inside the bounded observation window"
}

function Add-InputInterop {
    if ('CodeArbiterDesktopInput' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class CodeArbiterDesktopInput {
  [StructLayout(LayoutKind.Sequential)] public struct MOUSEINPUT { public int dx; public int dy; public uint mouseData; public uint dwFlags; public uint time; public UIntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct KEYBDINPUT { public ushort wVk; public ushort wScan; public uint dwFlags; public uint time; public UIntPtr dwExtraInfo; }
  [StructLayout(LayoutKind.Sequential)] public struct HARDWAREINPUT { public uint uMsg; public ushort wParamL; public ushort wParamH; }
  [StructLayout(LayoutKind.Explicit)] public struct InputUnion {
    [FieldOffset(0)] public MOUSEINPUT mi;
    [FieldOffset(0)] public KEYBDINPUT ki;
    [FieldOffset(0)] public HARDWAREINPUT hi;
  }
  [StructLayout(LayoutKind.Sequential)] public struct INPUT { public uint type; public InputUnion u; }
  [DllImport("user32.dll", SetLastError=true)] public static extern uint SendInput(uint nInputs, INPUT[] inputs, int cbSize);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint pid);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
}
'@
}

function Send-UnicodeText([string]$Text) {
    $inputs = [Collections.Generic.List[CodeArbiterDesktopInput+INPUT]]::new()
    foreach ($character in $Text.ToCharArray()) {
        foreach ($flags in @(0x0004, 0x0006)) {
            $input = [CodeArbiterDesktopInput+INPUT]::new()
            $input.type = 1
            $input.u.ki.wScan = [uint16]$character
            $input.u.ki.dwFlags = $flags
            $inputs.Add($input)
        }
    }
    if ([CodeArbiterDesktopInput]::SendInput($inputs.Count, $inputs.ToArray(),
        [Runtime.InteropServices.Marshal]::SizeOf([type][CodeArbiterDesktopInput+INPUT])) -ne $inputs.Count) {
        throw 'Unicode desktop request injection was incomplete'
    }
}

function Send-Key([uint16]$VirtualKey, [switch]$Control) {
    $keys = [Collections.Generic.List[CodeArbiterDesktopInput+INPUT]]::new()
    if ($Control) {
        $down = [CodeArbiterDesktopInput+INPUT]::new(); $down.type = 1; $down.u.ki.wVk = 0x11; $keys.Add($down)
    }
    $keyDown = [CodeArbiterDesktopInput+INPUT]::new(); $keyDown.type = 1; $keyDown.u.ki.wVk = $VirtualKey; $keys.Add($keyDown)
    $keyUp = [CodeArbiterDesktopInput+INPUT]::new(); $keyUp.type = 1; $keyUp.u.ki.wVk = $VirtualKey; $keyUp.u.ki.dwFlags = 0x0002; $keys.Add($keyUp)
    if ($Control) {
        $up = [CodeArbiterDesktopInput+INPUT]::new(); $up.type = 1; $up.u.ki.wVk = 0x11; $up.u.ki.dwFlags = 0x0002; $keys.Add($up)
    }
    if ([CodeArbiterDesktopInput]::SendInput($keys.Count, $keys.ToArray(),
        [Runtime.InteropServices.Marshal]::SizeOf([type][CodeArbiterDesktopInput+INPUT])) -ne $keys.Count) {
        throw 'desktop key injection was incomplete'
    }
}

if ($InputAbiOnly) {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') {
        throw 'input ABI measurement is test-only'
    }
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitProcess) {
        throw 'input ABI measurement requires 64-bit Windows'
    }
    Add-InputInterop
    [ordered]@{
        input = [Runtime.InteropServices.Marshal]::SizeOf([type][CodeArbiterDesktopInput+INPUT])
        mouse_input = [Runtime.InteropServices.Marshal]::SizeOf([type][CodeArbiterDesktopInput+MOUSEINPUT])
        keyboard_input = [Runtime.InteropServices.Marshal]::SizeOf([type][CodeArbiterDesktopInput+KEYBDINPUT])
    } | ConvertTo-Json -Compress
    exit 0
}

$loaded = Get-Contract
$contract = $loaded.Contract
$script:Contract = $contract
$script:AppServerQueryCount = 0
$script:AppServerMaxQueries = [int]$contract.channel.max_queries
if ($ContractOnly -or $PSCmdlet.ParameterSetName -eq 'Contract') {
    [ordered]@{ verdict = 'PASS'; driver_sha256 = $contract.driver.sha256;
        submission_method = $contract.route_corpus.submission_method } | ConvertTo-Json -Compress
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'Fixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'fixture mode is test-only' }
    $fixture = Get-Content -LiteralPath $FixturePath -Raw -Encoding utf8 | ConvertFrom-Json
    Convert-Observation -InputValue $fixture -Contract $contract | ConvertTo-Json -Depth 8 -Compress
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'PermissionProbeFixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'permission fixture mode is test-only' }
    $fixture = Get-Content -LiteralPath $PermissionProbeFixturePath -Raw -Encoding utf8 | ConvertFrom-Json
    Assert-PermissionProbeEvidence -Evidence $fixture | ConvertTo-Json -Depth 5 -Compress
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'InventoryFixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'inventory fixture mode is test-only' }
    $fixture = Get-Content -LiteralPath $InventoryFixturePath -Raw -Encoding utf8 | ConvertFrom-Json
    Measure-PostAuthInventory -InputValue $fixture | ConvertTo-Json -Depth 5 -Compress
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'InventoryProbe') {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'post-auth inventory probe requires Windows'
    }
    $profile = [IO.Path]::GetFullPath($ProfilePath)
    if ([IO.Path]::GetFullPath($env:USERPROFILE) -cne $profile) {
        throw 'post-auth inventory must execute as the disposable desktop identity'
    }
    $codexRoot = Join-Path $profile '.codex'
    if (-not (Test-Path -LiteralPath $codexRoot -PathType Container)) {
        throw 'post-auth Codex root is missing'
    }
    $doctorRun = Invoke-ProcessCapture -Executable $RuntimePath -ArgumentList @('doctor','--json') -TimeoutSeconds 45
    try { $doctor = $doctorRun.Stdout | ConvertFrom-Json } catch { throw 'post-auth Codex doctor did not emit valid JSON' }
    $files = @(Get-ChildItem -LiteralPath $codexRoot -Recurse -File -Force -ErrorAction Stop |
        ForEach-Object FullName)
    $credentialOutput = @(& cmdkey.exe /list 2>&1)
    if ($LASTEXITCODE -ne 0) { throw 'post-auth Credential Manager inventory failed' }
    $inputValue = [pscustomobject]@{
        schema_version = 1
        profile = $profile
        config_text = Get-Content -LiteralPath (Join-Path $codexRoot 'config.toml') -Raw -Encoding utf8
        files = $files
        credential_targets = @($credentialOutput | Select-String '^\s*Target:' |
            ForEach-Object { [string]$_ })
        doctor_exit_code = [int]$doctorRun.ExitCode
        doctor_overall_status = [string]$doctor.overallStatus
        doctor_checks = $doctor.checks
    }
    $evidence = Measure-PostAuthInventory -InputValue $inputValue
    $evidence | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $InventoryEvidencePath -Encoding utf8NoBOM
    $evidence | ConvertTo-Json -Depth 4 -Compress
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'PermissionProbe') {
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'real Codex permission probe requires Windows'
    }
    $evidence = Invoke-RealPermissionProbe -Runtime $RuntimePath -Repo $ProofRepoPath `
        -PluginRoot $SelectedPluginRoot -Canary $AuthCanaryPath
    $evidence | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $PermissionEvidencePath -Encoding utf8NoBOM
    $evidence | ConvertTo-Json -Depth 6 -Compress
    exit 0
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'desktop UI driver requires Windows'
}
if ((Get-Sha256 $RuntimePath) -cne (Get-Sha256 $PackagedRuntimePath)) {
    throw 'runtime bytes do not match the packaged Store resource'
}
$desktop = Get-Process -Id $DesktopProcessId -ErrorAction Stop
$driverProcess = Get-Process -Id $PID -ErrorAction Stop
$driverCim = Get-CimInstance Win32_Process -Filter "ProcessId=$PID"
$package = Get-AppxPackage $contract.application.package_name | Sort-Object Version -Descending | Select-Object -First 1
if ($null -eq $package -or $package.Publisher -cne $contract.application.publisher -or
    $package.PackageFullName -notmatch $contract.application.package_full_name_regex) {
    throw 'installed Codex Store package is untrusted'
}
$desktopPath = [IO.Path]::GetFullPath($desktop.Path)
$expectedDesktopPath = [IO.Path]::GetFullPath((Join-Path $package.InstallLocation $contract.application.executable_relative_path))
if ($desktopPath -cne $expectedDesktopPath -or (Get-AuthenticodeSignature $desktopPath).Status -ne 'Valid') {
    throw 'foreground desktop process is not the signed Store executable'
}

$expectedCanaryPath = Join-Path (Join-Path $env:USERPROFILE '.codex') ([string]$contract.authentication.denial_canary_filename)
if ([IO.Path]::GetFullPath($AuthCanaryPath) -cne [IO.Path]::GetFullPath($expectedCanaryPath) -or
    -not (Test-Path -LiteralPath $AuthCanaryPath -PathType Leaf)) {
    throw 'auth-isolation canary path is not the exact disposable Codex profile path'
}
$canaryContent = Get-Content -LiteralPath $AuthCanaryPath -Raw -Encoding utf8
$canaryPrompt = [string]$contract.authentication.denial_canary_prompt_prefix + ' ' +
    [IO.Path]::GetFullPath($AuthCanaryPath)

$runtimeDeadline = [DateTime]::UtcNow.AddSeconds(30)
do {
    $processes = @(Get-CimInstance Win32_Process)
    $byId = @{}; foreach ($item in $processes) { $byId[[int]$item.ProcessId] = $item }
    $eligible = @()
    foreach ($candidate in @($processes | Where-Object {
        $_.ProcessId -ne $PID -and $_.Name -ceq 'codex.exe' -and $_.ExecutablePath -and
        (Get-Sha256 $_.ExecutablePath) -ceq (Get-Sha256 $RuntimePath)
    })) {
        $ancestors = @(); $parent = [int]$candidate.ParentProcessId; $isDescendant = $false
        for ($depth = 0; $depth -lt 16 -and $parent -gt 0; $depth++) {
            $ancestors += $parent
            if ($parent -eq $DesktopProcessId) { $isDescendant = $true; break }
            if (-not $byId.ContainsKey($parent)) { break }
            $parent = [int]$byId[$parent].ParentProcessId
        }
        if ($isDescendant) { $eligible += [pscustomobject]@{ Process=$candidate; Ancestors=@($ancestors) } }
    }
    if ($eligible.Count -eq 0) { Start-Sleep -Milliseconds 500 }
} while ($eligible.Count -eq 0 -and [DateTime]::UtcNow -lt $runtimeDeadline)
if ($eligible.Count -ne 1) { throw 'exactly one packaged runtime descendant must own the desktop proof window' }
$runtime = $eligible[0].Process
$runtimeAncestors = @($eligible[0].Ancestors)
$runtimeStarted = ([DateTimeOffset]$runtime.CreationDate).ToUniversalTime()

$reader = Start-AppServerReader $RuntimePath
try {
    $appServerCim = Get-CimInstance Win32_Process -Filter "ProcessId=$($reader.Id)"
    if ($null -eq $appServerCim) { throw 'could not bind the measured app-server process' }
    $script:Contract = $contract
    $script:NextRequestId = 10
    $null = Send-AppServerRequest $reader 1 'initialize' @{
        clientInfo = @{ name = 'codearbiter-desktop-proof'; title = 'CodeArbiter desktop proof'; version = '1.0.0' }
        capabilities = @{ experimentalApi = $false }
    }
    $reader.StandardInput.WriteLine('{"method":"initialized"}'); $reader.StandardInput.Flush()
    $account = Send-AppServerRequest $reader 2 'account/read' @{ refreshToken = $false }
    if ($account.account.type -cne 'chatgpt') { throw 'desktop account is not ChatGPT-authenticated' }
    $policy = Send-AppServerRequest $reader 3 'config/read' @{ cwd = $ProofRepoPath; includeLayers = $false }
    if ($policy.config.approval_policy -cne 'never' -or $policy.config.sandbox_mode -cne 'read-only' -or
        $policy.config.default_permissions -cne $contract.authentication.permission_profile_id -or
        [bool]$policy.config.features.hooks -or [string]$policy.config.windows.sandbox -cne 'elevated') {
        throw 'effective desktop policy and permission profile are not the reviewed fail-closed policy'
    }
    $before = Send-AppServerRequest $reader 4 'thread/list' @{ limit = 100; useStateDbOnly = $true }
    $beforeIds = @($before.data | ForEach-Object { $_.id })

    Add-InputInterop
    $window = $desktop.MainWindowHandle
    if ($window -eq [IntPtr]::Zero -or -not [CodeArbiterDesktopInput]::SetForegroundWindow($window)) {
        throw 'could not focus the measured Codex desktop window'
    }
    Start-Sleep -Milliseconds 500
    [uint32]$foregroundPid = 0
    $null = [CodeArbiterDesktopInput]::GetWindowThreadProcessId(
        [CodeArbiterDesktopInput]::GetForegroundWindow(), [ref]$foregroundPid)
    if ($foregroundPid -ne $DesktopProcessId) { throw 'measured Codex desktop is not foreground' }

    Send-Key -VirtualKey 0x4E -Control
    Start-Sleep -Milliseconds 500
    Send-UnicodeText $canaryPrompt
    Send-Key -VirtualKey 0x0D
    $canaryThread = Wait-ObservedThread $reader $beforeIds 'canary'
    $routeBeforeIds = @($beforeIds) + [string]$canaryThread.id

    if (-not [CodeArbiterDesktopInput]::SetForegroundWindow($window)) {
        throw 'could not refocus the measured Codex desktop window'
    }
    Send-Key -VirtualKey 0x4E -Control
    Start-Sleep -Milliseconds 500
    $requestSubmitted = [DateTimeOffset]::UtcNow
    Send-UnicodeText ([string]$contract.route_corpus.desktop_request)
    Send-Key -VirtualKey 0x0D
    $thread = Wait-ObservedThread $reader $routeBeforeIds 'route'
    $dispatchCompleted = [DateTimeOffset]::UtcNow

    $version = (& $RuntimePath --version 2>$null | Select-Object -First 1)
    $inputValue = [pscustomobject]@{
        schema_version = 1
        app_server_query_count = $script:AppServerQueryCount
        account = [pscustomobject]@{ auth_mode = $account.account.type }
        policy = [pscustomobject]@{ approval_policy = $policy.config.approval_policy; sandbox_mode = $policy.config.sandbox_mode; permission_profile_id = $policy.config.default_permissions; hooks_enabled = [bool]$policy.config.features.hooks; windows_sandbox = [string]$policy.config.windows.sandbox }
        window = [pscustomobject]@{ submission_method = 'windows-sendinput-unicode'; foreground_process_id = $DesktopProcessId; prompt = $contract.route_corpus.desktop_request }
        desktop = [pscustomobject]@{ process_id = $DesktopProcessId; process_sha256 = Get-Sha256 $desktopPath; package_name = $package.Name; package_full_name = $package.PackageFullName; publisher = $package.Publisher; signature_status = (Get-AuthenticodeSignature $desktopPath).Status.ToString(); process_start_time = ([DateTimeOffset]$desktop.StartTime).ToUniversalTime().ToString('o') }
        runtime = [pscustomobject]@{ process_id = [int]$runtime.ProcessId; parent_process_id = [int]$runtime.ParentProcessId; process_ancestor_ids = @($runtimeAncestors); process_sha256 = Get-Sha256 $runtime.ExecutablePath; packaged_resource_sha256 = Get-Sha256 $RuntimePath; version = $version; eligible_process_count = $eligible.Count; process_start_time = $runtimeStarted.ToString('o') }
        app_server_process = [pscustomobject]@{ process_id=[int]$reader.Id; parent_process_id=[int]$appServerCim.ParentProcessId; process_sha256=Get-Sha256 $RuntimePath; process_start_time=([DateTimeOffset]$reader.StartTime).ToUniversalTime().ToString('o') }
        driver_process = [pscustomobject]@{ process_id=$PID; parent_process_id=[int]$driverCim.ParentProcessId; executable_sha256=Get-Sha256 $driverProcess.Path; signature_status=(Get-AuthenticodeSignature $driverProcess.Path).Status.ToString(); script_sha256=Get-Sha256 $PSCommandPath; script_path=[IO.Path]::GetFullPath($PSCommandPath); command_line_sha256=Get-TextSha256 ([string]$driverCim.CommandLine); process_start_time=([DateTimeOffset]$driverProcess.StartTime).ToUniversalTime().ToString('o') }
        auth_isolation = [pscustomobject]@{ canary_path = [IO.Path]::GetFullPath($AuthCanaryPath); canary_content = $canaryContent; canary_content_sha256 = Get-TextSha256 $canaryContent; canary_prompt = $canaryPrompt; thread = $canaryThread }
        thread = [pscustomobject]@{ id=$thread.id; request_submitted_at=$requestSubmitted.ToString('o'); dispatch_completed_at=$dispatchCompleted.ToString('o'); items=@($thread.items) }
    }
    $observation = Convert-Observation -InputValue $inputValue -Contract $contract
    $observation | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ObservationPath -Encoding utf8NoBOM
    $observation | ConvertTo-Json -Depth 8 -Compress
} finally {
    if ($reader -and -not $reader.HasExited) { $reader.Kill(); $reader.WaitForExit(5000) }
    if ($reader) { $reader.Dispose() }
}
