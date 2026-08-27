[CmdletBinding(DefaultParameterSetName = 'Contract')]
param(
    [Parameter(ParameterSetName = 'Contract')]
    [switch]$ContractOnly,

    [Parameter(Mandatory, ParameterSetName = 'Prepare')]
    [switch]$PrepareAudit,

    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [switch]$CollectAudit,

    [Parameter(Mandatory, ParameterSetName = 'Prepare')]
    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [string]$PluginRoot,

    [Parameter(Mandatory, ParameterSetName = 'Prepare')]
    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [string]$DesktopSid,

    [Parameter(Mandatory, ParameterSetName = 'Prepare')]
    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [string]$AuthRoot,

    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [long]$StartRecordId,

    [Parameter(Mandatory, ParameterSetName = 'Fixture')]
    [string]$FixturePath,

    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [string]$DriverObservationPath,

    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$ChallengeKey,

    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [ValidatePattern('^[0-9a-f]{64}$')]
    [string]$ChallengeNonce,

    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [ValidatePattern('^[0-9a-fA-F-]{36}$')]
    [string]$VmId,

    [Parameter(Mandatory, ParameterSetName = 'Collect')]
    [string]$BootstrapSid,

    [string]$ContractPath = (Join-Path $PSScriptRoot '..\desktop-proof-boundary.json')
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-ExactFields($Value, [string[]]$Expected, [string]$Label) {
    if ($null -eq $Value) { throw "$Label is missing" }
    $actual = @($Value.PSObject.Properties.Name | Sort-Object)
    $wanted = @($Expected | Sort-Object)
    if (($actual -join "`n") -cne ($wanted -join "`n")) { throw "$Label fields are not exact" }
}

function Get-Sha256 {
    param([Parameter(Mandatory)][string]$LiteralPath)
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $LiteralPath).Hash.ToLowerInvariant()
}

function Get-TextSha256 {
    param([Parameter(Mandatory)][string]$Value)
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = $algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value))
        return -join @($bytes | ForEach-Object { $_.ToString('x2') })
    } finally {
        $algorithm.Dispose()
    }
}

function Convert-NativePathForComparison {
    param([Parameter(Mandatory)][string]$Value)
    [IO.Path]::GetFullPath($Value).Replace('/', '\').TrimEnd('\')
}

function Get-Contract {
    $resolved = (Resolve-Path -LiteralPath $ContractPath).Path
    $contract = Get-Content -LiteralPath $resolved -Raw -Encoding utf8 | ConvertFrom-Json
    if ($contract.schema_version -ne 2) { throw 'boundary contract schema_version must be 2' }
    if ($contract.probe.source_path -ne '.github/scripts/Invoke-CodeArbiterDesktopRouteProbe.ps1') {
        throw 'boundary contract probe source path is untrusted'
    }
    $repoRoot = (Resolve-Path -LiteralPath (Join-Path (Split-Path $resolved -Parent) '..')).Path
    $probePath = Join-Path $repoRoot $contract.probe.source_path
    if ((Get-Sha256 -LiteralPath $probePath) -cne $contract.probe.sha256) {
        throw 'tracked desktop route probe digest mismatch'
    }
    return [pscustomobject]@{ Contract = $contract; RepoRoot = $repoRoot; ProbePath = $probePath }
}

function Convert-HexBytes([string]$Value) {
    if ($Value -cnotmatch '^[0-9a-f]{64}$') { throw 'challenge key must be 32 lowercase hex bytes' }
    $bytes = New-Object byte[] 32
    for ($index = 0; $index -lt 32; $index++) {
        $bytes[$index] = [Convert]::ToByte($Value.Substring($index * 2, 2), 16)
    }
    $bytes
}

function Get-HmacSha256([string]$KeyHex, [string]$Value) {
    $algorithm = [Security.Cryptography.HMACSHA256]::new((Convert-HexBytes $KeyHex))
    try {
        -join @($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)) |
            ForEach-Object { $_.ToString('x2') })
    } finally { $algorithm.Dispose() }
}

function Convert-RouteEvidence {
    param([Parameter(Mandatory)]$InputValue, [Parameter(Mandatory)]$Contract)
    if ($InputValue.schema_version -ne 1) { throw 'probe evidence schema is invalid' }
    if ([string]$InputValue.driver_observation.dispatch_agent -cne $Contract.route_corpus.dispatch_agent) {
        throw 'desktop dispatch does not match the approved reviewer charter'
    }
    foreach ($field in @('request_sha256','thread_id_sha256','desktop_process_sha256',
        'runtime_process_sha256','process_chain_sha256','dispatch_sha256')) {
        if ([string]$InputValue.driver_observation.$field -cnotmatch '^[0-9a-f]{64}$') {
            throw "driver observation $field is invalid"
        }
    }
    $processAudit = $InputValue.process_audit
    Assert-ExactFields $processAudit @(
        'record_id','timestamp','subject_sid','process_id','parent_process_id','executable_sha256'
    ) 'runtime process audit'
    try {
        $processInstant = ([DateTimeOffset]$processAudit.timestamp).ToUniversalTime()
        $candidateInstant = ([DateTimeOffset]$InputValue.driver_observation.candidate_activated_at).ToUniversalTime()
        $requestInstant = ([DateTimeOffset]$InputValue.driver_observation.request_submitted_at).ToUniversalTime()
        $dispatchInstant = ([DateTimeOffset]$InputValue.driver_observation.dispatch_completed_at).ToUniversalTime()
        $processTimestamp = $processInstant.ToString('o')
    }
    catch { throw 'Windows process-creation audit timestamp is invalid' }
    if ([long]$processAudit.record_id -le 0 -or $processTimestamp -notmatch '^20[0-9]{2}-[0-9]{2}-[0-9]{2}T' -or
        $processInstant -lt $candidateInstant -or $processInstant -gt $requestInstant -or $dispatchInstant -lt $requestInstant) {
        throw 'Windows process-creation audit identity is invalid'
    }
    if ([string]$processAudit.subject_sid -cne [string]$InputValue.desktop_sid) {
        throw 'Windows process-creation audit subject is not the disposable desktop identity'
    }
    if ([int]$processAudit.process_id -ne [int]$InputValue.driver_observation.runtime_process_id -or
        [int]$processAudit.parent_process_id -ne [int]$InputValue.driver_observation.runtime_parent_process_id) {
        throw 'Windows process-creation audit PID ancestry does not bind the measured runtime'
    }
    if ([string]$processAudit.executable_sha256 -cne [string]$InputValue.driver_observation.runtime_process_sha256) {
        throw 'Windows process-creation audit executable does not bind the measured runtime'
    }
    if ([string]$InputValue.challenge_nonce -cnotmatch '^[0-9a-f]{64}$' -or
        [string]$InputValue.vm_id -notmatch '^[0-9a-fA-F-]{36}$' -or
        [string]$InputValue.bootstrap_sid -notmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$' -or
        [string]$InputValue.desktop_sid -notmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$') {
        throw 'probe channel identity or challenge is invalid'
    }
    $records = @($InputValue.audit_records)
    $authRecords = @($InputValue.auth_audit_records)
    if (($records.Count + $authRecords.Count) -gt [int]$Contract.channel.max_audit_records) {
        throw 'desktop audit record bound exceeded'
    }
    if ($records.Count -lt $Contract.route_corpus.paths.Count) {
        throw 'desktop route audit corpus is incomplete'
    }
    $orderedRecords = @($records | Sort-Object { [long]$_.record_id })
    for ($index = 1; $index -lt $orderedRecords.Count; $index++) {
        if ([long]$orderedRecords[$index].record_id -le [long]$orderedRecords[$index - 1].record_id) {
            throw 'desktop audit records are duplicated or unordered'
        }
    }
    if (@($orderedRecords | Group-Object record_id | Where-Object Count -ne 1).Count) {
        throw 'desktop audit records contain duplicate record identifiers'
    }
    if ([long]$processAudit.record_id -ge [long]$orderedRecords[0].record_id) {
        throw 'runtime process creation was not observed before the route reads'
    }

    $authRoot = [IO.Path]::GetFullPath([string]$InputValue.auth_root).TrimEnd('\')
    if (-not $authRoot.EndsWith('\.codex',[StringComparison]::OrdinalIgnoreCase)) {
        throw 'auth audit root is not the disposable Codex profile root'
    }
    foreach ($authRecord in $authRecords) {
        Assert-ExactFields $authRecord @(
            'record_id','timestamp','subject_sid','process_id','object_name','access_status'
        ) 'auth-store audit record'
        try { $authInstant = ([DateTimeOffset]$authRecord.timestamp).ToUniversalTime() }
        catch { throw 'auth-store audit timestamp is invalid' }
        $authPath = [IO.Path]::GetFullPath([string]$authRecord.object_name)
        if ($authInstant -lt $candidateInstant -or $authInstant -gt $dispatchInstant -or
            -not (Test-ReusableAuthPath $authRoot $authPath) -or
            [string]$authRecord.subject_sid -cne [string]$InputValue.desktop_sid -or
            [string]$authRecord.access_status -notin @('success','failure')) {
            throw 'auth-store audit record is outside the measured candidate window or identity'
        }
        if ([string]$authRecord.access_status -ceq 'success') {
            throw 'reusable Codex auth material was read during the protected candidate activation window'
        }
    }

    $firstPath = [IO.Path]::GetFullPath([string]$orderedRecords[0].object_name)
    $firstPathComparable = Convert-NativePathForComparison $firstPath
    $firstRelative = ([string]$Contract.route_corpus.paths[0]).Replace('/', '\')
    if (-not $firstPathComparable.EndsWith('\' + $firstRelative, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'first audited path is not the selected skill entry'
    }
    $root = [IO.Path]::GetFullPath([string]$InputValue.plugin_root).TrimEnd('\','/')
    $rootComparable = Convert-NativePathForComparison $root
    $auditedRootComparable = $firstPathComparable.Substring(
        0, $firstPathComparable.Length - $firstRelative.Length - 1).TrimEnd('\')
    if ($rootComparable -cne $auditedRootComparable) {
        throw 'expected plugin root does not match the audited selected-skill root'
    }
    $suffix = ('\.codex\plugins\cache\{0}\{1}\' -f
        $Contract.marketplace.name, $Contract.marketplace.plugin)
    if ($rootComparable -notmatch ('(?i)' + [regex]::Escape($suffix) + $Contract.marketplace.version_regex + '$')) {
        throw 'audited root is not a versioned Codex marketplace root'
    }

    $paths = @($Contract.route_corpus.paths | ForEach-Object {
        [IO.Path]::GetFullPath((Join-Path $root ([string]$_)))
    })
    foreach ($path in $paths) {
        if (-not (Convert-NativePathForComparison $path).StartsWith(
                $rootComparable + '\', [StringComparison]::OrdinalIgnoreCase) -or
            -not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'audited route path escapes or is missing from the selected root'
        }
    }
    $skillText = Get-Content -LiteralPath $paths[0] -Raw -Encoding utf8
    if ($skillText -notmatch [regex]::Escape('dispatching-parallel-agents') -or
        $skillText -notmatch [regex]::Escape('coverage-auditor')) {
        throw 'selected skill does not actually reference the routed routine and reviewer charter'
    }

    $routeEvents = @()
    $recordCanonical = @(
        'process|{0}|{1}|{2}|{3}|{4}' -f $processAudit.record_id,$processTimestamp,
        $processAudit.subject_sid,$processAudit.process_id,$processAudit.executable_sha256
    )
    for ($index = 0; $index -lt $paths.Count; $index++) {
        $matches = @($orderedRecords | Where-Object {
            [IO.Path]::GetFullPath([string]$_.object_name).Equals(
                $paths[$index], [StringComparison]::OrdinalIgnoreCase)
        })
        if ($matches.Count -ne 1) { throw 'each approved route path must have exactly one audit record' }
        $record = $matches[0]
        try { $recordInstant = ([DateTimeOffset]$record.timestamp).ToUniversalTime() }
        catch { throw 'route audit timestamp is invalid' }
        if ([string]$record.subject_sid -cne [string]$InputValue.desktop_sid -or
            [int]$record.process_id -ne [int]$InputValue.driver_observation.runtime_process_id -or
            [string]$record.process_sha256 -cne [string]$InputValue.driver_observation.runtime_process_sha256 -or
            [int]$record.parent_process_id -ne [int]$InputValue.driver_observation.runtime_parent_process_id -or
            [string]$record.process_chain_sha256 -cne [string]$InputValue.driver_observation.process_chain_sha256 -or
            [string]$record.package_full_name -cne [string]$InputValue.driver_observation.package_full_name -or
            [string]$record.publisher -cne [string]$InputValue.driver_observation.package_publisher -or
            $recordInstant -lt $requestInstant -or $recordInstant -gt $dispatchInstant) {
            throw 'route audit record is not attributable to the measured Store desktop runtime'
        }
        if ($index -gt 0 -and [long]$record.record_id -le [long]$routeEvents[$index - 1].record_id) {
            throw 'approved route events are reordered'
        }
        $contentSha = Get-Sha256 -LiteralPath $paths[$index]
        $canonical = 'codearbiter.desktop-route.v2|{0}|{1}|{2}|{3}|{4}' -f (
            $index + 1), $Contract.route_corpus.event_kinds[$index],
            $Contract.route_corpus.references[$index], $Contract.route_corpus.paths[$index], $contentSha
        $routeEvents += [pscustomobject][ordered]@{
            sequence = $index + 1
            kind = [string]$Contract.route_corpus.event_kinds[$index]
            reference = [string]$Contract.route_corpus.references[$index]
            resolved_path = $paths[$index]
            content_sha256 = $contentSha
            event_sha256 = Get-TextSha256 $canonical
            record_id = [long]$record.record_id
        }
        $recordCanonical += ('{0}|{1}|{2}|{3}' -f $record.record_id,
            $record.timestamp, $record.process_id, (Get-TextSha256 ([string]$record.object_name)))
    }
    if ($routeEvents.Count -gt [int]$Contract.channel.max_messages) {
        throw 'desktop route message bound exceeded'
    }
    $causalCanonical='codearbiter.desktop-causal-window.v1|{0}|{1}|{2}|{3}|{4}|{5}' -f
        $InputValue.driver_observation.desktop_process_id,$InputValue.driver_observation.runtime_process_id,
        $InputValue.driver_observation.runtime_process_started_at,$InputValue.driver_observation.request_submitted_at,
        $InputValue.driver_observation.dispatch_completed_at,$InputValue.driver_observation.thread_id_sha256
    $causalWindowSha=Get-TextSha256 $causalCanonical
    $securityRecordsSha = Get-TextSha256 ('codearbiter.desktop-security-records.v2|' + ($recordCanonical -join '|'))
    $eventParts = @($routeEvents | ForEach-Object {
        '{0},{1},{2},{3},{4},{5}' -f [int]$_.sequence,
            (Get-TextSha256 ([string]$_.kind)),(Get-TextSha256 ([string]$_.reference)),
            (Get-TextSha256 ([string]$_.resolved_path)),[string]$_.content_sha256,[string]$_.event_sha256
    })
    $responseCanonical = 'codearbiter.desktop-route-response.v1|{0}|{1}|{2}|{3}|{4}|true|false|true|{5}' -f
        (Get-TextSha256 $root),(Get-TextSha256 ([string]$InputValue.driver_observation.dispatch_agent)),
        [string]$InputValue.driver_observation.thread_id_sha256,$securityRecordsSha,$routeEvents.Count,
        ($eventParts -join ';')
    $responseBindingSha = Get-TextSha256 $responseCanonical
    $challengeCanonical = 'codearbiter.desktop-channel.v4|{0}|{1}|{2}|{3}|{4}|{5}|{6}|{7}|{8}|{9}|{10}|{11}' -f
        $InputValue.vm_id, $InputValue.bootstrap_sid, $InputValue.desktop_sid,
        $InputValue.challenge_nonce, $InputValue.driver_observation.request_sha256,
        $InputValue.driver_observation.dispatch_sha256,$causalWindowSha,
        $InputValue.driver_observation.auth_canary_content_sha256,
        $InputValue.driver_observation.permission_profile_id,
        ([string]$InputValue.driver_observation.auth_canary_denied).ToLowerInvariant(),
        $responseBindingSha,
        (@($routeEvents | ForEach-Object record_id) -join ',')
    $result = [ordered]@{
        test_result = 'SUCCEEDED'
        selected_plugin_root = $root
        dispatch_agent = [string]$InputValue.driver_observation.dispatch_agent
        request_sha256 = [string]$InputValue.driver_observation.request_sha256
        thread_id_sha256 = [string]$InputValue.driver_observation.thread_id_sha256
        dispatch_sha256 = [string]$InputValue.driver_observation.dispatch_sha256
        causal_window_sha256 = $causalWindowSha
        auth_canary_content_sha256 = [string]$InputValue.driver_observation.auth_canary_content_sha256
        permission_profile_id = [string]$InputValue.driver_observation.permission_profile_id
        auth_canary_denied = [bool]$InputValue.driver_observation.auth_canary_denied
        record_ids = @($routeEvents | ForEach-Object record_id)
        route_events = @($routeEvents | Select-Object -ExcludeProperty record_id)
        security_records_sha256 = $securityRecordsSha
        response_binding_sha256 = $responseBindingSha
        challenge_response_sha256 = Get-HmacSha256 ([string]$InputValue.challenge_key) $challengeCanonical
        observed_messages = $routeEvents.Count
        sequence_complete = $true
        timed_out = $false
        teardown_requested = $true
    }
    $withoutSize = $result | ConvertTo-Json -Depth 8 -Compress
    $result.response_utf8_bytes = [Text.Encoding]::UTF8.GetByteCount($withoutSize)
    $json = $result | ConvertTo-Json -Depth 8 -Compress
    if ([Text.Encoding]::UTF8.GetByteCount($json) -gt [int]$Contract.channel.max_message_bytes) {
        throw 'desktop route response byte bound exceeded'
    }
    $result.response_utf8_bytes = [Text.Encoding]::UTF8.GetByteCount($json)
    $result
}

function Get-RoutePaths {
    param([Parameter(Mandatory)]$Contract, [Parameter(Mandatory)][string]$Root)
    $resolvedRoot = [IO.Path]::GetFullPath($Root).TrimEnd('\','/')
    $comparableRoot = Convert-NativePathForComparison $resolvedRoot
    $expectedSuffix = ('\.codex\plugins\cache\{0}\{1}\{2}' -f
        $Contract.marketplace.name, $Contract.marketplace.plugin, $Contract.marketplace.version_pattern)
    if ($comparableRoot -notmatch ('(?i)' + [regex]::Escape($expectedSuffix).Replace(
        [regex]::Escape($Contract.marketplace.version_pattern), $Contract.marketplace.version_regex
    ) + '$')) {
        throw 'plugin root is not the versioned Codex marketplace-selected root'
    }
    $paths = @()
    foreach ($relative in $Contract.route_corpus.paths) {
        $candidate = [IO.Path]::GetFullPath((Join-Path $resolvedRoot $relative))
        if (-not (Convert-NativePathForComparison $candidate).StartsWith(
                $comparableRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'route corpus path escapes the selected plugin root'
        }
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw 'route corpus file is missing from the selected plugin root'
        }
        $paths += $candidate
    }
    return $paths
}

function Get-EventDataMap {
    param([Parameter(Mandatory)]$EventRecord)
    $xml = [xml]$EventRecord.ToXml()
    $values = @{}
    foreach ($node in $xml.Event.EventData.Data) {
        $values[[string]$node.Name] = [string]$node.'#text'
    }
    return $values
}

function Convert-AuditProcessId([object]$Value) {
    $raw = [string]$Value
    if ($raw.StartsWith('0x',[StringComparison]::OrdinalIgnoreCase)) {
        return [Convert]::ToInt32($raw.Substring(2),16)
    }
    [int]$raw
}

function Test-ReusableAuthPath([string]$AuthRoot, [string]$Path) {
    $root = [IO.Path]::GetFullPath($AuthRoot).TrimEnd('\')
    $candidate = [IO.Path]::GetFullPath($Path)
    if (-not $candidate.StartsWith($root + '\',[StringComparison]::OrdinalIgnoreCase)) { return $false }
    $relative = $candidate.Substring($root.Length + 1).Replace('/','\')
    if ($relative -match '^(?i:auth\.json)(?:\..+)?$' -or
        $relative -match '^(?i:(?:\.credentials|credentials)\.json)(?:\..+)?$' -or
        $relative -match '^(?i:credentials|sessions|tokens)\\') { return $true }
    $false
}

function Invoke-AuditPreparation($RoutePaths, [string]$AuthRoot, [string]$Sid, $Adapters) {
    $required = @('enable_file_system','set_route_audit','set_auth_audit','enable_process_creation','latest_record_id')
    foreach($name in $required){if(-not$Adapters.ContainsKey($name)){throw "audit preparation adapter is missing $name"}}
    $trace=[Collections.Generic.List[string]]::new()
    & $Adapters['enable_file_system'];$null=$trace.Add('file-system-audit-enabled')
    foreach($path in @($RoutePaths)){
        & $Adapters['set_route_audit'] $path $Sid
        $null=$trace.Add('route-audit:'+(Get-TextSha256 ([IO.Path]::GetFullPath($path))))
    }
    & $Adapters['set_auth_audit'] $AuthRoot $Sid;$null=$trace.Add('auth-audit-enabled')
    & $Adapters['enable_process_creation'];$null=$trace.Add('process-creation-audit-enabled')
    $latest=[long](& $Adapters['latest_record_id'])
    [pscustomobject]@{start_record_id=$latest;trace=@($trace)}
}

function Get-ActivationProcessKind($Event, $Driver) {
    $data=$Event.data
    $processId=Convert-AuditProcessId $data.NewProcessId
    $parentRaw=if($data.ProcessId){$data.ProcessId}else{$data.CreatorProcessId}
    $parentId=Convert-AuditProcessId $parentRaw
    $digest=[string]$Event.executable_sha256
    $commandLine=[string]$data.CommandLine
    $eventInstant=([DateTimeOffset]$Event.timestamp).ToUniversalTime()
    $nearStart={param([string]$Value) [Math]::Abs(($eventInstant-([DateTimeOffset]$Value).ToUniversalTime()).TotalSeconds)-le 2}
    if($processId-eq[int]$Driver.desktop_process_id-and$digest-ceq[string]$Driver.desktop_process_sha256){return $true}
    if($processId-eq[int]$Driver.runtime_process_id-and$parentId-eq[int]$Driver.runtime_parent_process_id-and
        $digest-ceq[string]$Driver.runtime_process_sha256-and(& $nearStart ([string]$Driver.runtime_process_started_at))){return 'route-runtime'}
    if($processId-eq[int]$Driver.app_server_process_id-and$parentId-eq[int]$Driver.app_server_parent_process_id-and
        $digest-ceq[string]$Driver.app_server_process_sha256-and(& $nearStart ([string]$Driver.app_server_process_started_at))){return 'app-server'}
    if($digest-ceq[string]$Driver.driver_process_executable_sha256-and
        [string]$Driver.driver_process_signature_status-ceq'Valid'){
        if($processId-eq[int]$Driver.driver_process_id-and$parentId-eq[int]$Driver.driver_parent_process_id-and
            (Get-TextSha256 $commandLine)-ceq[string]$Driver.driver_process_command_line_sha256-and
            (& $nearStart ([string]$Driver.driver_process_started_at))){return 'driver'}
        $commandMarker=' -Command '
        $commandIndex=$commandLine.IndexOf($commandMarker,[StringComparison]::OrdinalIgnoreCase)
        $logicalCommand=if($commandIndex-ge 0){$commandLine.Substring($commandIndex+$commandMarker.Length).Trim()}else{''}
        if($parentId-eq[int]$Driver.runtime_process_id-and
            $eventInstant-lt([DateTimeOffset]$Driver.request_submitted_at).ToUniversalTime()-and
            (Get-TextSha256 $logicalCommand)-ceq[string]$Driver.canary_command_sha256){return 'canary'}
    }
    $null
}

function Test-AllowedActivationProcess($Event, $Driver) {
    $null-ne(Get-ActivationProcessKind $Event $Driver)
}

function Convert-WindowsAuditEvents($Events, $Driver, [string]$DesktopSid, $RoutePaths, [string]$AuthRoot, [string]$PluginRoot) {
    $processMatches=@();$routeRecords=@();$authRecords=@();$unexpectedProcesses=@()
    $allowedKinds=@{driver=0;'app-server'=0;canary=0}
    $resolvedAuthRoot=[IO.Path]::GetFullPath($AuthRoot).TrimEnd('\')
    $resolvedPluginRoot=[IO.Path]::GetFullPath($PluginRoot).TrimEnd('\')
    $candidateInstant=([DateTimeOffset]$Driver.candidate_activated_at).ToUniversalTime()
    $requestInstant=([DateTimeOffset]$Driver.request_submitted_at).ToUniversalTime()
    $dispatchInstant=([DateTimeOffset]$Driver.dispatch_completed_at).ToUniversalTime()
    foreach($event in @($Events|Sort-Object{[long]$_.record_id})){
        $data=$event.data
        if([string]$data.SubjectUserSid-cne$DesktopSid){continue}
        if([int]$event.id-eq 4688){
            $processId=Convert-AuditProcessId $data.NewProcessId
            $eventInstant=([DateTimeOffset]$event.timestamp).ToUniversalTime()
            $commandLine=[string]$data.CommandLine
            $newProcessName=[string]$data.NewProcessName
            if($eventInstant-ge$candidateInstant){
                $kind=Get-ActivationProcessKind $event $Driver
                if($null-eq$kind){
                    $unexpectedProcesses += [pscustomobject]@{record_id=[long]$event.record_id;process_id=$processId;executable_sha256=[string]$event.executable_sha256}
                }elseif($allowedKinds.ContainsKey([string]$kind)){$allowedKinds[[string]$kind]++}
            }
            if($processId-ne[int]$Driver.runtime_process_id){continue}
            $parentRaw=if($data.ProcessId){$data.ProcessId}else{$data.CreatorProcessId}
            $processMatches += [pscustomobject]@{
                record_id=[long]$event.record_id;timestamp=([DateTimeOffset]$event.timestamp).ToUniversalTime().ToString('o')
                subject_sid=$DesktopSid;process_id=$processId;parent_process_id=Convert-AuditProcessId $parentRaw
                executable_sha256=[string]$event.executable_sha256
            }
            continue
        }
        if([int]$event.id-ne 4663){continue}
        $objectPath=[IO.Path]::GetFullPath([string]$data.ObjectName)
        $processId=Convert-AuditProcessId $data.ProcessId
        $eventInstant=([DateTimeOffset]$event.timestamp).ToUniversalTime()
        if((Test-ReusableAuthPath $resolvedAuthRoot $objectPath)-and
            $eventInstant-ge$candidateInstant-and$eventInstant-le$dispatchInstant){
            $authRecords += [pscustomobject]@{
                record_id=[long]$event.record_id;timestamp=$eventInstant.ToString('o');subject_sid=$DesktopSid
                process_id=$processId;object_name=$objectPath;access_status=[string]$event.access_status
            }
        }
        if(@($RoutePaths|Where-Object{$_.Equals($objectPath,[StringComparison]::OrdinalIgnoreCase)}).Count-and
            $processId-eq[int]$Driver.runtime_process_id){
            $routeRecords += [pscustomobject]@{
                record_id=[long]$event.record_id;timestamp=$eventInstant.ToString('o');subject_sid=$DesktopSid
                process_id=$processId;process_sha256=[string]$Driver.runtime_process_sha256
                package_full_name=[string]$Driver.package_full_name;publisher=[string]$Driver.package_publisher
                parent_process_id=[int]$Driver.runtime_parent_process_id;process_chain_sha256=[string]$Driver.process_chain_sha256
                object_name=$objectPath
            }
        }
    }
    if($unexpectedProcesses.Count){throw 'nonallowlisted process ran inside the protected candidate activation window'}
    if($processMatches.Count-ne 1){throw 'exactly one measured runtime process-creation event is required'}
    foreach($kind in @('driver','app-server','canary')){
        if([int]$allowedKinds[$kind]-ne 1){throw "exactly one $kind process-creation event is required"}
    }
    [pscustomobject]@{process_audit=$processMatches[0];audit_records=@($routeRecords);auth_audit_records=@($authRecords)}
}

$loaded = Get-Contract
$contract = $loaded.Contract
$script:Contract = $contract

if ($ContractOnly -or $PSCmdlet.ParameterSetName -eq 'Contract') {
    [ordered]@{
        verdict = 'PASS'
        probe_sha256 = $contract.probe.sha256
        event_source = $contract.route_corpus.event_source
        route_corpus_id = $contract.route_corpus.id
    } | ConvertTo-Json -Compress
    exit 0
}

if ($PSCmdlet.ParameterSetName -eq 'Fixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'fixture mode is test-only' }
    $fixture = Get-Content -LiteralPath $FixturePath -Raw -Encoding utf8 | ConvertFrom-Json
    if($fixture.schema_version-eq 2-and$fixture.harness_mode-ceq'production-audit'){
        $fixturePaths=Get-RoutePaths -Contract $contract -Root ([string]$fixture.plugin_root)
        $applied=[Collections.Generic.List[string]]::new()
        $adapters=@{
            enable_file_system={$null=$applied.Add('enable-file-system')}
            set_route_audit={param($Path,$Sid)$null=$applied.Add('route:'+([IO.Path]::GetFullPath($Path))+':'+$Sid)}
            set_auth_audit={param($Path,$Sid)$null=$applied.Add('auth:'+([IO.Path]::GetFullPath($Path))+':'+$Sid)}
            enable_process_creation={$null=$applied.Add('enable-process-creation')}
            latest_record_id={[long]$fixture.start_record_id}
        }
        $prepared=Invoke-AuditPreparation $fixturePaths ([string]$fixture.auth_root) ([string]$fixture.desktop_sid) $adapters
        $parsed=Convert-WindowsAuditEvents @($fixture.event_envelopes) $fixture.driver_observation ([string]$fixture.desktop_sid) $fixturePaths ([string]$fixture.auth_root) ([string]$fixture.plugin_root)
        $inputValue=[pscustomobject]@{
            schema_version=1;plugin_root=$fixture.plugin_root;auth_root=$fixture.auth_root;desktop_sid=$fixture.desktop_sid
            challenge_key=$fixture.challenge_key;challenge_nonce=$fixture.challenge_nonce;vm_id=$fixture.vm_id;bootstrap_sid=$fixture.bootstrap_sid
            driver_observation=$fixture.driver_observation;process_audit=$parsed.process_audit
            audit_records=@($parsed.audit_records);auth_audit_records=@($parsed.auth_audit_records)
        }
        $result=Convert-RouteEvidence -InputValue $inputValue -Contract $contract
        $result|Add-Member -NotePropertyName preparation_trace -NotePropertyValue @($prepared.trace)
        $result|Add-Member -NotePropertyName applied_operations -NotePropertyValue @($applied)
        $result|ConvertTo-Json -Depth 8 -Compress
        exit 0
    }
    Convert-RouteEvidence -InputValue $fixture -Contract $contract | ConvertTo-Json -Depth 8 -Compress
    exit 0
}

if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
    throw 'desktop route auditing requires Windows'
}
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'desktop route auditing requires an elevated guest probe service'
}
if ($DesktopSid -notmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$') {
    throw 'desktop SID must be an exact disposable local-account SID'
}

$routePaths = Get-RoutePaths -Contract $contract -Root $PluginRoot

if ($PrepareAudit) {
    $resolvedAuthRoot = [IO.Path]::GetFullPath($AuthRoot).TrimEnd('\')
    if (-not $resolvedAuthRoot.EndsWith('\.codex',[StringComparison]::OrdinalIgnoreCase) -or
        -not (Test-Path -LiteralPath $resolvedAuthRoot -PathType Container)) {
        throw 'auth audit root is not the disposable Codex profile root'
    }
    $adapters=@{
        enable_file_system={& auditpol.exe /set /subcategory:'File System' /success:enable /failure:enable|Out-Null;if($LASTEXITCODE-ne 0){throw 'could not enable Windows File System auditing'}}
        set_route_audit={param($Path,$Sid)$rule=[Security.AccessControl.FileSystemAuditRule]::new($Sid,[Security.AccessControl.FileSystemRights]'ReadData,ReadAttributes',[Security.AccessControl.AuditFlags]::Success);$acl=Get-Acl -LiteralPath $Path -Audit;$acl.SetAuditRule($rule);Set-Acl -LiteralPath $Path -AclObject $acl}
        set_auth_audit={param($Path,$Sid)$rule=[Security.AccessControl.FileSystemAuditRule]::new($Sid,[Security.AccessControl.FileSystemRights]'ReadData,ReadAttributes',[Security.AccessControl.InheritanceFlags]'ContainerInherit,ObjectInherit',[Security.AccessControl.PropagationFlags]::None,[Security.AccessControl.AuditFlags]'Success,Failure');$acl=Get-Acl -LiteralPath $Path -Audit;$acl.AddAuditRule($rule);Set-Acl -LiteralPath $Path -AclObject $acl}
        enable_process_creation={& auditpol.exe /set /subcategory:'Process Creation' /success:enable|Out-Null;if($LASTEXITCODE-ne 0){throw 'could not enable Windows Process Creation auditing'};New-Item -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\System\Audit' -Force|Out-Null;Set-ItemProperty -Path 'HKLM:\Software\Microsoft\Windows\CurrentVersion\Policies\System\Audit' -Name ProcessCreationIncludeCmdLine_Enabled -Type DWord -Value 1}
        latest_record_id={$latest=Get-WinEvent -FilterHashtable @{LogName='Security';Id=@(4663,4688)} -MaxEvents 1 -ErrorAction SilentlyContinue;if($null-eq$latest){[long]0}else{[long]$latest.RecordId}}
    }
    $prepared=Invoke-AuditPreparation $routePaths $resolvedAuthRoot $DesktopSid $adapters
    [ordered]@{
        verdict = 'PASS'
        route_corpus_id = $contract.route_corpus.id
        start_record_id = [long]$prepared.start_record_id
        desktop_sid_sha256 = Get-TextSha256 -Value $DesktopSid
    } | ConvertTo-Json -Compress
    exit 0
}

$driver = Get-Content -LiteralPath $DriverObservationPath -Raw -Encoding utf8 | ConvertFrom-Json
$eventQuery = @{
    FilterHashtable = @{ LogName = 'Security'; Id = @(4663,4688) }
    MaxEvents = [int]$contract.channel.max_audit_records + 1
    ErrorAction = 'Stop'
}
$queried = @(Get-WinEvent @eventQuery |
    Where-Object { $_.RecordId -gt $StartRecordId })
if ($queried.Count -gt [int]$contract.channel.max_audit_records) {
    throw 'desktop audit record bound exceeded'
}
$resolvedAuthRoot = [IO.Path]::GetFullPath($AuthRoot).TrimEnd('\')
$envelopes=@()
foreach($event in @($queried|Sort-Object RecordId)){
    $data = Get-EventDataMap -EventRecord $event
    $executableSha=$null
    if($event.Id-eq 4688-and$data.NewProcessName){
        $executable=[IO.Path]::GetFullPath([string]$data.NewProcessName)
        if(Test-Path -LiteralPath $executable -PathType Leaf){$executableSha=Get-Sha256 -LiteralPath $executable}
    }
    $envelopes += [pscustomobject]@{
        id=[int]$event.Id;record_id=[long]$event.RecordId;timestamp=$event.TimeCreated.ToUniversalTime().ToString('o')
        access_status=if(@($event.KeywordsDisplayNames)-contains'Audit Failure'){'failure'}else{'success'}
        executable_sha256=$executableSha;data=[pscustomobject]$data
    }
}
$parsed=Convert-WindowsAuditEvents $envelopes $driver $DesktopSid $routePaths $resolvedAuthRoot $PluginRoot
$processAudit=$parsed.process_audit
$records=@($parsed.audit_records)
$authRecords=@($parsed.auth_audit_records)
$inputValue = [pscustomobject]@{
    schema_version = 1
    plugin_root = $PluginRoot
    auth_root = $resolvedAuthRoot
    desktop_sid = $DesktopSid
    challenge_key = $ChallengeKey
    challenge_nonce = $ChallengeNonce
    vm_id = $VmId
    bootstrap_sid = $BootstrapSid
    driver_observation = $driver
    process_audit = $processAudit
    audit_records = $records
    auth_audit_records = $authRecords
}
$result = Convert-RouteEvidence -InputValue $inputValue -Contract $contract
$json = $result | ConvertTo-Json -Depth 8 -Compress
if ([Text.Encoding]::UTF8.GetByteCount($json) -gt [int]$contract.channel.max_message_bytes) {
    throw 'desktop route response byte bound exceeded'
}
$json
