[CmdletBinding(DefaultParameterSetName = 'Production')]
param(
    [Parameter(ParameterSetName = 'Production')]
    [string]$RequestPath,
    [Parameter(ParameterSetName = 'Production')]
    [string]$ReceiptPath,
    [string]$ContractPath = (Join-Path $PSScriptRoot '..\desktop-proof-boundary.json'),
    [Parameter(Mandatory, ParameterSetName = 'Fixture')]
    [string]$FixturePath,
    [Parameter(ParameterSetName = 'Fixture')]
    [string]$TestFailAfter,
    [Parameter(ParameterSetName = 'Fixture')]
    [ValidatePattern('^(vm-destroyed|run-root-destroyed):(once|always)$')]
    [string]$TestCleanupFailure,
    [Parameter(ParameterSetName = 'Fixture')]
    [ValidateSet('write-after-persist','post-write-inventory')]
    [string]$TestReceiptFailure,
    [Parameter(ParameterSetName = 'Fixture')]
    [switch]$TestReceiptCleanupFailure,
    [Parameter(Mandatory, ParameterSetName = 'CandidateSurfaceFixture')]
    [string]$CandidateSurfaceFixturePath,
    [Parameter(Mandatory, ParameterSetName = 'ReceiptContractFixture')]
    [string]$ReceiptContractFixturePath,
    [Parameter(Mandatory, ParameterSetName = 'ArchiveExtractionFixture')]
    [string]$ArchiveExtractionFixturePath,
    [Parameter(Mandatory, ParameterSetName = 'ArchiveExtractionFixture')]
    [string]$ArchiveExtractionDestination,
    [Parameter(Mandatory, ParameterSetName = 'CandidateMetadataFixture')]
    [string]$CandidateMetadataFixturePath,
    [Parameter(ParameterSetName = 'Contract')]
    [switch]$ContractOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$RunnerRoot = 'C:\codearbiter-runner'
$WorkingRoot = 'C:\codearbiter-runner\desktop-proof-runs'
$VmSwitchName = 'CodeArbiter-Desktop-Proof'

function Get-Sha256([string]$LiteralPath) {
    (Get-FileHash -Algorithm SHA256 -LiteralPath $LiteralPath).Hash.ToLowerInvariant()
}

function Assert-GuestTrustedBytes {
    param([Parameter(Mandatory)]$Session, [Parameter(Mandatory)][hashtable]$Bindings)
    $result = Invoke-Command -Session $Session -ArgumentList $Bindings -ScriptBlock {
        param($Expected)
        foreach ($entry in $Expected.GetEnumerator()) {
            if (-not (Test-Path -LiteralPath $entry.Key -PathType Leaf)) {
                throw "trusted guest input is missing: $($entry.Key)"
            }
            $actual = (Get-FileHash -Algorithm SHA256 -LiteralPath $entry.Key).Hash.ToLowerInvariant()
            if ($actual -cne [string]$entry.Value) { throw "trusted guest input digest mismatch: $($entry.Key)" }
        }
        $true
    }
    if ($result -ne $true) { throw 'guest trusted-input verification did not complete' }
}

function Get-TextSha256([string]$Value) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        -join @($algorithm.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)) |
            ForEach-Object { $_.ToString('x2') })
    } finally { $algorithm.Dispose() }
}

function Get-RandomHex([int]$Bytes) {
    $buffer = New-Object byte[] $Bytes
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($buffer) } finally { $generator.Dispose() }
    -join @($buffer | ForEach-Object { $_.ToString('x2') })
}

function Convert-DesktopPermissionPath([string]$Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { throw 'desktop permission path is empty' }
    ([IO.Path]::GetFullPath($Value).Replace('\','/')).TrimEnd('/')
}

function New-DesktopProofPermissionProfile($Contract, [string]$Account, [string]$Version, [string]$ProofRepo) {
    if ($Account -cnotmatch '^[A-Za-z0-9][A-Za-z0-9-]{0,63}$') {
        throw 'desktop permission account is invalid'
    }
    if ($Version -cnotmatch ('^' + [string]$Contract.marketplace.version_regex + '$')) {
        throw 'desktop permission plugin version is invalid'
    }
    $proofRepoPath = Convert-DesktopPermissionPath $ProofRepo
    if ($proofRepoPath -cne 'C:/CodeArbiterProof/repo') {
        throw 'desktop permission proof repository is outside the reviewed boundary'
    }
    $codexRoot = "C:/Users/$Account/.codex"
    $pluginRoot = "$codexRoot/plugins/cache/$($Contract.marketplace.name)/$($Contract.marketplace.plugin)/$Version"
    $canary = "$codexRoot/$($Contract.authentication.denial_canary_filename)"
    $toml = @"
approval_policy = "never"
default_permissions = "desktop-proof"
cli_auth_credentials_store = "file"

[features]
hooks = false

[windows]
sandbox = "elevated"

[permissions.desktop-proof]
description = "Read-only desktop proof with exact plugin resources allowed and reusable Codex auth state denied to model tools"

[permissions.desktop-proof.filesystem]
"$pluginRoot/**" = "read"
"$proofRepoPath/**" = "read"
"$codexRoot/auth.json" = "deny"
"$codexRoot/auth.json.*" = "deny"
"$codexRoot/.credentials.json" = "deny"
"$codexRoot/.credentials.json.*" = "deny"
"$codexRoot/credentials.json" = "deny"
"$codexRoot/credentials.json.*" = "deny"
"$codexRoot/credentials" = "deny"
"$codexRoot/sessions" = "deny"
"$codexRoot/tokens" = "deny"
"$canary" = "deny"

[permissions.desktop-proof.network]
enabled = false
"@
    [pscustomobject]@{
        PermissionProfileId = 'desktop-proof'
        CodexRoot = $codexRoot
        PluginRoot = $pluginRoot
        ProofRepo = $proofRepoPath
        Toml = $toml
    }
}

function Convert-HexBytes([string]$Value) {
    if ($Value -cnotmatch '^[0-9a-f]+$' -or $Value.Length % 2) { throw 'hex value is invalid' }
    $bytes = [byte[]]::new($Value.Length / 2)
    for ($index = 0; $index -lt $bytes.Length; $index++) {
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

function Test-FixedTimeEquals([byte[]]$Left, [byte[]]$Right) {
    if (-not ('CodeArbiterFixedTime' -as [type])) {
        Add-Type -TypeDefinition @'
using System.Security.Cryptography;
public static class CodeArbiterFixedTime {
  public static bool Equals(byte[] left, byte[] right) {
    return left != null && right != null && CryptographicOperations.FixedTimeEquals(left, right);
  }
}
'@
    }
    [CodeArbiterFixedTime]::Equals($Left,$Right)
}

function Assert-ChannelResponse($Channel) {
    Assert-ExactFields $Channel @(
        'key','nonce','vm_id','bootstrap_sid','desktop_sid','request_sha256',
        'dispatch_sha256','causal_window_sha256','auth_canary_content_sha256',
        'permission_profile_id','auth_canary_denied','response_binding_sha256','record_ids','response_sha256'
    ) 'desktop channel response'
    foreach ($field in @('key','nonce','request_sha256','dispatch_sha256','causal_window_sha256',
        'auth_canary_content_sha256','response_binding_sha256','response_sha256')) {
        if ([string]$Channel.$field -cnotmatch '^[0-9a-f]{64}$') { throw "desktop channel $field is invalid" }
    }
    if ([string]$Channel.vm_id -notmatch '^[0-9a-fA-F-]{36}$' -or
        [string]$Channel.bootstrap_sid -notmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$' -or
        [string]$Channel.desktop_sid -notmatch '^S-1-5-21-(?:[0-9]+-){3}[0-9]+$') {
        throw 'desktop channel identity binding is invalid'
    }
    $recordIds = @($Channel.record_ids | ForEach-Object { [long]$_ })
    if (-not $recordIds.Count -or @($recordIds | Sort-Object -Unique).Count -ne $recordIds.Count) {
        throw 'desktop channel record IDs are missing or duplicated'
    }
    if([string]$Channel.permission_profile_id-cne'desktop-proof'-or$Channel.auth_canary_denied-ne$true){
        throw 'desktop channel auth-isolation binding is invalid'
    }
    $canonical = 'codearbiter.desktop-channel.v4|{0}|{1}|{2}|{3}|{4}|{5}|{6}|{7}|{8}|{9}|{10}|{11}' -f
        $Channel.vm_id,$Channel.bootstrap_sid,$Channel.desktop_sid,$Channel.nonce,
        $Channel.request_sha256,$Channel.dispatch_sha256,$Channel.causal_window_sha256,
        $Channel.auth_canary_content_sha256,$Channel.permission_profile_id,
        ([string]$Channel.auth_canary_denied).ToLowerInvariant(),$Channel.response_binding_sha256,
        ($recordIds -join ',')
    [byte[]]$expected = Convert-HexBytes (Get-HmacSha256 ([string]$Channel.key) $canonical)
    [byte[]]$actual = Convert-HexBytes ([string]$Channel.response_sha256)
    if (-not (Test-FixedTimeEquals $expected $actual)) {
        throw 'desktop channel HMAC response is invalid'
    }
}

function Get-RouteResponseBinding($Route) {
    $eventParts = @($Route.route_events | ForEach-Object {
        '{0},{1},{2},{3},{4},{5}' -f [int]$_.sequence,
            (Get-TextSha256 ([string]$_.kind)),(Get-TextSha256 ([string]$_.reference)),
            (Get-TextSha256 ([string]$_.resolved_path)),[string]$_.content_sha256,[string]$_.event_sha256
    })
    $canonical = 'codearbiter.desktop-route-response.v1|{0}|{1}|{2}|{3}|{4}|{5}|{6}|{7}|{8}' -f
        (Get-TextSha256 ([string]$Route.selected_plugin_root)),
        (Get-TextSha256 ([string]$Route.dispatch_agent)),[string]$Route.thread_id_sha256,
        [string]$Route.security_records_sha256,[int]$Route.observed_messages,
        ([string]$Route.sequence_complete).ToLowerInvariant(),
        ([string]$Route.timed_out).ToLowerInvariant(),
        ([string]$Route.teardown_requested).ToLowerInvariant(),($eventParts -join ';')
    Get-TextSha256 $canonical
}

function Assert-ExactFields($Value, [string[]]$Required, [string]$Label) {
    $actual = @($Value.PSObject.Properties.Name)
    if (@($Required | Where-Object { $_ -notin $actual }).Count -or
        @($actual | Where-Object { $_ -notin $Required }).Count) {
        throw "$Label fields must be exact"
    }
}

function New-ReceiptPolicyAndChannel($Fixture, $Contract) {
    Assert-ExactFields $Fixture @('schema_version','policy','channel') 'receipt contract fixture'
    if ($Fixture.schema_version -ne 1) { throw 'receipt contract fixture schema is invalid' }
    Assert-ExactFields $Fixture.policy @(
        'requested_approval','effective_approval','requested_sandbox','effective_sandbox',
        'permission_consumer','restricted_filesystem','restricted_network','hooks_enabled',
        'startup_warning_count','windows_sandbox','guest_acl_boundary'
    ) 'receipt policy'
    Assert-ExactFields $Fixture.channel @(
        'challenge_nonce','challenge_response_sha256','observed_queries','observed_messages',
        'response_utf8_bytes','sequence_complete','timed_out'
    ) 'receipt channel'
    [ordered]@{
        policy = [ordered]@{
            requested_approval = [string]$Fixture.policy.requested_approval
            effective_approval = [string]$Fixture.policy.effective_approval
            requested_sandbox = [string]$Fixture.policy.requested_sandbox
            effective_sandbox = [string]$Fixture.policy.effective_sandbox
            permission_consumer = [string]$Fixture.policy.permission_consumer
            restricted_filesystem = [bool]$Fixture.policy.restricted_filesystem
            restricted_network = [bool]$Fixture.policy.restricted_network
            hooks_enabled = [bool]$Fixture.policy.hooks_enabled
            startup_warning_count = [int]$Fixture.policy.startup_warning_count
            windows_sandbox = [string]$Fixture.policy.windows_sandbox
            guest_acl_boundary = [bool]$Fixture.policy.guest_acl_boundary
        }
        channel = [ordered]@{
            transport = [string]$Contract.channel.transport
            authentication = [string]$Contract.channel.authentication
            challenge = [string]$Contract.channel.challenge
            challenge_nonce_sha256 = Get-TextSha256 ([string]$Fixture.channel.challenge_nonce)
            challenge_response_sha256 = [string]$Fixture.channel.challenge_response_sha256
            max_queries = [int]$Contract.channel.max_queries
            observed_queries = [int]$Fixture.channel.observed_queries
            max_audit_records = [int]$Contract.channel.max_audit_records
            max_messages = [int]$Contract.channel.max_messages
            max_message_bytes = [int]$Contract.channel.max_message_bytes
            observed_messages = [int]$Fixture.channel.observed_messages
            response_utf8_bytes = [int]$Fixture.channel.response_utf8_bytes
            sequence_complete = [bool]$Fixture.channel.sequence_complete
            timed_out = [bool]$Fixture.channel.timed_out
        }
    }
}

function Get-Contract {
    $resolved = (Resolve-Path -LiteralPath $ContractPath).Path
    $contract = Get-Content -LiteralPath $resolved -Raw -Encoding utf8 | ConvertFrom-Json
    if ($contract.schema_version -ne 2 -or
        $contract.image.provisioning_mode -cne 'iso-apply-fresh-vhdx' -or
        $contract.channel.transport -cne 'powershell-direct-vmbus') {
        throw 'boundary contract identity is invalid'
    }
    Assert-ExactFields $contract.candidate_archive @(
        'max_archive_bytes','max_entries','max_entry_uncompressed_bytes',
        'max_total_uncompressed_bytes','max_compression_ratio'
    ) 'candidate archive limits'
    $expectedArchiveLimits = [ordered]@{
        max_archive_bytes = 8388608L
        max_entries = 1024L
        max_entry_uncompressed_bytes = 2097152L
        max_total_uncompressed_bytes = 33554432L
        max_compression_ratio = 100L
    }
    foreach ($name in $expectedArchiveLimits.Keys) {
        if ([long]$contract.candidate_archive.$name -ne [long]$expectedArchiveLimits[$name]) {
            throw 'candidate archive limits are not the reviewed values'
        }
    }
    $root = (Resolve-Path -LiteralPath (Join-Path (Split-Path $resolved -Parent) '..')).Path
    foreach ($name in @('broker','driver','probe')) {
        $source = Join-Path $root $contract.$name.source_path
        if ((Get-Sha256 $source) -cne $contract.$name.sha256) {
            throw "tracked desktop $name digest mismatch"
        }
    }
    if ($contract.image.sha256 -cne 'a61adeab895ef5a4db436e0a7011c92a2ff17bb0357f58b13bbc4062e535e7b9') {
        throw 'approved Windows evaluation image digest mismatch'
    }
    [pscustomobject]@{ Contract = $contract; Root = $root }
}

function Expand-BoundedCandidateArchive {
    param(
        [Parameter(Mandatory)][string]$ArchivePath,
        [Parameter(Mandatory)][string]$DestinationPath,
        [Parameter(Mandatory)]$Contract,
        [string]$ExpectedSha256
    )
    if (-not (Test-Path -LiteralPath $ArchivePath -PathType Leaf)) {
        throw 'candidate archive is missing'
    }
    $archiveItem = Get-Item -LiteralPath $ArchivePath -Force
    if (($archiveItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw 'candidate archive must not be a reparse point'
    }
    if ([long]$archiveItem.Length -gt [long]$Contract.candidate_archive.max_archive_bytes) {
        throw 'candidate archive exceeds the archive-byte limit'
    }
    $destination = [IO.Path]::GetFullPath($DestinationPath)
    if (Test-Path -LiteralPath $destination) {
        throw 'candidate archive destination must not pre-exist'
    }

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $fileStream = $null
    $archive = $null
    $records = [Collections.Generic.List[object]]::new()
    $pathKinds = [Collections.Generic.Dictionary[string,bool]]::new([StringComparer]::OrdinalIgnoreCase)
    $totalUncompressed = 0L
    try {
        $fileStream = [IO.File]::Open($archiveItem.FullName,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
        if ($ExpectedSha256) {
            if ($ExpectedSha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'candidate archive binding digest is invalid' }
            $algorithm = [Security.Cryptography.SHA256]::Create()
            try {
                $actualSha256 = -join @($algorithm.ComputeHash($fileStream) | ForEach-Object { $_.ToString('x2') })
            } finally { $algorithm.Dispose() }
            if ($actualSha256 -cne $ExpectedSha256) { throw 'candidate archive changed after validation' }
            $fileStream.Position = 0
        }
        $archive = [IO.Compression.ZipArchive]::new($fileStream,[IO.Compression.ZipArchiveMode]::Read,$false)
        $allEntries = @($archive.Entries)
        if ($allEntries.Count -gt [long]$Contract.candidate_archive.max_entries) {
            throw 'candidate archive exceeds the entry-count limit'
        }
        foreach ($entry in $allEntries) {
            $name = [string]$entry.FullName
            if ([string]::IsNullOrEmpty($name) -or $name.Contains('\')) {
                throw 'candidate archive path is invalid'
            }
            $isDirectory = $name.EndsWith('/',[StringComparison]::Ordinal)
            $external = [uint32]([int64]$entry.ExternalAttributes -band 0xFFFFFFFFL)
            $mode = ($external -shr 16) -band 0xFFFF
            $kind = $mode -band 0xF000
            if (($external -band 0x400) -ne 0 -or $kind -notin @(0,0x4000,0x8000)) {
                throw 'candidate archive contains a non-regular file'
            }
            if ($isDirectory -and $kind -notin @(0,0x4000)) {
                throw 'candidate archive directory has a non-directory mode'
            }
            if (-not $isDirectory -and $kind -eq 0x4000) {
                throw 'candidate archive file has a directory mode'
            }
            if ($name -in @('plugins/','plugins/ca-codex/')) {
                if (-not $isDirectory) { throw 'candidate archive ancestor is not a directory' }
                continue
            }
            if (-not $name.StartsWith('plugins/ca-codex/',[StringComparison]::Ordinal)) {
                throw 'candidate archive contains an entry outside plugins/ca-codex'
            }
            $relative = $name.Substring('plugins/ca-codex/'.Length)
            if ($isDirectory) { $relative = $relative.TrimEnd('/') }
            if ([string]::IsNullOrEmpty($relative)) { continue }
            $components = @($relative.Split('/'))
            $normalizedComponents = [Collections.Generic.List[string]]::new()
            foreach ($component in $components) {
                if ([string]::IsNullOrEmpty($component) -or $component -in @('.','..') -or
                    $component.EndsWith(' ') -or $component.EndsWith('.') -or
                    $component -match '[<>:"|?*\x00-\x1f]' -or
                    $component -match '^(?i:CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:[ .]|$)') {
                    throw 'candidate archive has a Windows-unsafe path'
                }
                $normalizedComponents.Add($component.Normalize([Text.NormalizationForm]::FormC))
            }
            $pathKey = $normalizedComponents -join '/'
            if ($pathKinds.ContainsKey($pathKey)) {
                throw 'candidate archive contains a Windows-ambiguous path collision'
            }
            $pathKinds.Add($pathKey,$isDirectory)
            if ($isDirectory) { continue }
            if ([long]$entry.Length -gt [long]$Contract.candidate_archive.max_entry_uncompressed_bytes) {
                throw 'candidate archive entry exceeds the size limit'
            }
            if ([long]$entry.Length -gt [long]$Contract.candidate_archive.max_total_uncompressed_bytes - $totalUncompressed) {
                throw 'candidate archive exceeds the total expansion limit'
            }
            $totalUncompressed += [long]$entry.Length
            if ([long]$entry.Length -gt 0 -and
                ([long]$entry.CompressedLength -eq 0 -or
                 ([decimal]$entry.Length / [decimal]$entry.CompressedLength) -gt [decimal]$Contract.candidate_archive.max_compression_ratio)) {
                throw 'candidate archive exceeds the compression-ratio limit'
            }
            $records.Add([pscustomobject]@{ Relative=$relative; Entry=$entry })
        }

        foreach ($pathKey in @($pathKinds.Keys)) {
            $keyComponents = @($pathKey.Split('/'))
            for ($index = 1; $index -lt $keyComponents.Count; $index++) {
                $prefixKey = $keyComponents[0..($index - 1)] -join '/'
                if ($pathKinds.ContainsKey($prefixKey) -and -not $pathKinds[$prefixKey]) {
                    throw 'candidate archive contains a file/directory prefix collision'
                }
            }
        }

        $null = New-Item -ItemType Directory -Path $destination -Force
        $destinationPrefix = $destination.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
        $actualTotal = 0L
        try {
            foreach ($record in $records) {
                $target = [IO.Path]::GetFullPath((Join-Path $destination ($record.Relative.Replace('/','\'))))
                if (-not $target.StartsWith($destinationPrefix,[StringComparison]::OrdinalIgnoreCase)) {
                    throw 'candidate archive extraction escaped its destination'
                }
                $parent = Split-Path -Parent $target
                $null = New-Item -ItemType Directory -Path $parent -Force
                $inputStream = $null
                $outputStream = $null
                $actualEntry = 0L
                try {
                    $inputStream = $record.Entry.Open()
                    $outputStream = [IO.File]::Open($target,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
                    $buffer = [byte[]]::new(65536)
                    while (($read = $inputStream.Read($buffer,0,$buffer.Length)) -gt 0) {
                        $actualEntry += $read
                        $actualTotal += $read
                        if ($actualEntry -gt [long]$record.Entry.Length -or
                            $actualEntry -gt [long]$Contract.candidate_archive.max_entry_uncompressed_bytes -or
                            $actualTotal -gt [long]$Contract.candidate_archive.max_total_uncompressed_bytes) {
                            throw 'candidate archive expanded beyond declared bounds'
                        }
                        $outputStream.Write($buffer,0,$read)
                    }
                } finally {
                    if ($outputStream) { $outputStream.Dispose() }
                    if ($inputStream) { $inputStream.Dispose() }
                }
                if ($actualEntry -ne [long]$record.Entry.Length) {
                    throw 'candidate archive entry size does not match metadata'
                }
            }
        } catch {
            Remove-Item -LiteralPath $destination -Recurse -Force -ErrorAction SilentlyContinue
            throw
        }
        [ordered]@{
            entry_count = $allEntries.Count
            file_count = $records.Count
            total_uncompressed_bytes = $actualTotal
        }
    } finally {
        if ($archive) { $archive.Dispose() }
        if ($fileStream) { $fileStream.Dispose() }
    }
}

function Assert-TrustedAclEvidence($Evidence, [string]$RunnerSid) {
    Assert-ExactFields $Evidence @('owner_sid','access') 'protected path ACL evidence'
    $approved = @('S-1-5-18','S-1-5-32-544',$RunnerSid)
    if ([string]$Evidence.owner_sid -notin $approved) { throw 'protected runner path owner is not approved' }
    # Use primitive mutation bits only. Composite values such as Modify and
    # FullControl contain read/execute bits and would misclassify a normal
    # ReadAndExecute ACE as writable when intersected as a mask.
    $mutationMask = [Security.AccessControl.FileSystemRights]::Write -bor
        [Security.AccessControl.FileSystemRights]::Delete -bor
        [Security.AccessControl.FileSystemRights]::DeleteSubdirectoriesAndFiles -bor
        [Security.AccessControl.FileSystemRights]::ChangePermissions -bor
        [Security.AccessControl.FileSystemRights]::TakeOwnership -bor
        [Security.AccessControl.FileSystemRights]::CreateFiles -bor
        [Security.AccessControl.FileSystemRights]::CreateDirectories -bor
        [Security.AccessControl.FileSystemRights]::AppendData -bor
        [Security.AccessControl.FileSystemRights]::WriteData
    foreach ($entry in @($Evidence.access)) {
        Assert-ExactFields $entry @('sid','type','rights') 'protected path ACL entry'
        if ([string]$entry.type -ceq 'Allow' -and
            (([Security.AccessControl.FileSystemRights][string]$entry.rights) -band $mutationMask) -and
            [string]$entry.sid -notin $approved) {
            throw 'protected runner path grants mutation rights to an unapproved principal'
        }
    }
}

function Get-AclEvidence([string]$LiteralPath) {
    $acl = Get-Acl -LiteralPath $LiteralPath
    $ownerSid = try {
        ([Security.Principal.NTAccount]$acl.Owner).Translate([Security.Principal.SecurityIdentifier]).Value
    } catch { [string]$acl.Owner }
    $access = @($acl.Access | ForEach-Object {
        $sid = try { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value }
            catch { [string]$_.IdentityReference.Value }
        [pscustomobject]@{sid=$sid;type=$_.AccessControlType.ToString();rights=$_.FileSystemRights.ToString()}
    })
    [pscustomobject]@{owner_sid=$ownerSid;access=$access}
}

function Assert-TrustedRunnerPath([string]$LiteralPath, [switch]$Leaf) {
    $full = [IO.Path]::GetFullPath($LiteralPath)
    $root = [IO.Path]::GetFullPath($RunnerRoot).TrimEnd('\')
    if (-not ($full -ceq $root -or
        $full.StartsWith($root + '\', [StringComparison]::OrdinalIgnoreCase))) {
        throw 'desktop host path escapes the protected runner root'
    }
    if ($Leaf -and -not (Test-Path -LiteralPath $full -PathType Leaf)) {
        throw 'required protected runner file is missing'
    }
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    $current = $root
    if (-not (Test-Path -LiteralPath $current -PathType Container)) { throw 'protected runner root is missing' }
    $rootItem = Get-Item -LiteralPath $current -Force
    if (($rootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'protected runner root is a reparse point' }
    Assert-TrustedAclEvidence (Get-AclEvidence $current) $identity
    foreach ($component in $full.Substring($root.Length).TrimStart('\').Split('\')) {
        if (-not $component) { continue }
        $current = Join-Path $current $component
        if (-not (Test-Path -LiteralPath $current)) { continue }
        $item = Get-Item -LiteralPath $current -Force
        if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'protected runner path contains a reparse component'
        }
        Assert-TrustedAclEvidence (Get-AclEvidence $current) $identity
    }
    $full
}

function Get-CandidateMetadata([string]$PackageRoot, [string]$Checker) {
    $root = (Resolve-Path -LiteralPath $PackageRoot).Path
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
        throw 'validated candidate plugin root is missing'
    }
    $validated = & python $Checker --candidate-contract-only --candidate-package $root --json |
        ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $validated.verdict -cne 'PASS') {
        throw 'candidate contract failed'
    }
    $manifestPath = Join-Path $root '.codex-plugin\plugin.json'
    $hooksPath = Join-Path $root 'hooks\hooks.json'
    foreach ($path in @($manifestPath,$hooksPath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw 'validated candidate metadata file is missing'
        }
    }
    $utf8 = [Text.UTF8Encoding]::new($false,$true)
    $manifest = $utf8.GetString([IO.File]::ReadAllBytes($manifestPath)) | ConvertFrom-Json
    $hooksManifestText = $utf8.GetString([IO.File]::ReadAllBytes($hooksPath))
    $rootPrefix = $root.TrimEnd('\','/') + [IO.Path]::DirectorySeparatorChar
    $paths = @([IO.Directory]::EnumerateFiles($root,'*',[IO.SearchOption]::AllDirectories) | ForEach-Object {
        $full = [IO.Path]::GetFullPath($_)
        if (-not $full.StartsWith($rootPrefix,[StringComparison]::OrdinalIgnoreCase)) {
            throw 'validated candidate metadata path escaped the plugin root'
        }
        $full.Substring($rootPrefix.Length).Replace('\','/').Replace([IO.Path]::DirectorySeparatorChar.ToString(),'/')
    })
    $null = Assert-BoundedCandidateSurface -Manifest $manifest -HooksManifestText $hooksManifestText -Paths $paths
    [pscustomobject]@{ Version = $manifest.version; ResourceSha256 = $validated.sha256 }
}

function Assert-BoundedCandidateSurface {
    param(
        [Parameter(Mandatory)]$Manifest,
        [Parameter(Mandatory)][string]$HooksManifestText,
        [Parameter(Mandatory)][string[]]$Paths
    )
    Assert-ExactFields $Manifest @(
        'name','description','version','author','license','homepage','repository','keywords','interface'
    ) 'candidate plugin manifest'
    Assert-ExactFields $Manifest.author @('name') 'candidate plugin author'
    Assert-ExactFields $Manifest.interface @(
        'displayName','shortDescription','longDescription','developerName','category',
        'capabilities','brandColor','defaultPrompt'
    ) 'candidate plugin interface'
    if ($Manifest.name -cne 'ca-codex' -or $Manifest.author.name -cne 'arbiterForge' -or
        $Manifest.version -notmatch '^[0-9][0-9A-Za-z.+-]{0,63}$') {
        throw 'candidate plugin manifest identity is invalid'
    }
    $allowedData = '^(?:\.codex-plugin/plugin\.json|(?:arbiter|CHANGELOG|COMMANDS|SPRINT)\.md|(?:skills|routines|agents|includes)/.+\.md)$'
    $hookPaths = @($Paths | Where-Object { ([string]$_).StartsWith('hooks/',[StringComparison]::Ordinal) })
    foreach ($path in @($Paths | Where-Object { -not ([string]$_).StartsWith('hooks/',[StringComparison]::Ordinal) })) {
        if ([string]$path -cnotmatch $allowedData) { throw "candidate package contains an unsupported surface: $path" }
    }
    $canonicalHooks = 'codearbiter.desktop-hook-paths.v1|' + (@($hookPaths | Sort-Object -CaseSensitive) -join '|')
    if ((Get-TextSha256 $canonicalHooks) -cne [string]$script:Contract.candidate_surface.hook_path_set_sha256) {
        throw 'candidate hook path set differs from the reviewed inert payload inventory'
    }
    if ((Get-TextSha256 $HooksManifestText) -cne [string]$script:Contract.candidate_surface.hooks_manifest_sha256) {
        throw 'candidate hooks manifest bytes differ from the reviewed inert payload declaration'
    }
    try { $HooksManifest = $HooksManifestText | ConvertFrom-Json } catch {
        throw 'candidate hooks manifest is not valid JSON'
    }
    Assert-ExactFields $HooksManifest @('hooks') 'candidate hooks manifest'
    Assert-ExactFields $HooksManifest.hooks @('SessionStart','PreToolUse','PostToolUse','UserPromptSubmit') 'candidate hook events'
    foreach ($eventName in @('SessionStart','PreToolUse','PostToolUse','UserPromptSubmit')) {
        foreach ($group in @($HooksManifest.hooks.$eventName)) {
            $groupFields = @($group.PSObject.Properties.Name)
            if (@($groupFields | Where-Object { $_ -notin @('matcher','hooks') }).Count -or 'hooks' -notin $groupFields) {
                throw 'candidate hook group schema is outside the reviewed boundary'
            }
            foreach ($hook in @($group.hooks)) {
                $fields = @($hook.PSObject.Properties.Name)
                if (@($fields | Where-Object { $_ -notin @('type','command','commandWindows','timeout','statusMessage','additionalContextLimit') }).Count -or
                    @('type','command','commandWindows','timeout','statusMessage' | Where-Object { $_ -notin $fields }).Count -or
                    [string]$hook.type -cne 'command' -or [int]$hook.timeout -le 0) {
                    throw 'candidate hook declaration schema is outside the reviewed boundary'
                }
                $unix = [regex]::Match([string]$hook.command, '^python3 "\$\{CLAUDE_PLUGIN_ROOT\}/(hooks/[A-Za-z0-9_-]+\.py)"$')
                $windows = [regex]::Match([string]$hook.commandWindows, '^python "\$\{CLAUDE_PLUGIN_ROOT\}/(hooks/[A-Za-z0-9_-]+\.py)"$')
                if (-not $unix.Success -or -not $windows.Success -or
                    $unix.Groups[1].Value -cne $windows.Groups[1].Value -or
                    $unix.Groups[1].Value -cnotin $hookPaths) {
                    throw 'candidate hook declaration is not a single reviewed inert hook path'
                }
            }
        }
    }
    [ordered]@{verdict='PASS';surface='known-hooks-disabled';path_count=@($Paths).Count}
}

function Assert-MeasuredProof($Measurements, [int]$ExpectedAllowRules) {
    $fields = @(
        'fresh_iso_applied','enhanced_session_enabled','guest_service_interface_enabled',
        'host_profile_mounted','host_shared_folders','network_policy_sha256',
        'enabled_allow_rules','outside_allow_rules','preauth_api_key_variables',
        'preauth_credential_targets','preauth_network_mappings','preauth_auth_files',
        'auth_storage_mode','postauth_credential_targets','postauth_auth_files','auth_prompt_ready',
        'auth_completed','app_account_mode','permission_profile_id','auth_canary_denied',
        'auth_canary_content_observed','eligible_runtime_process_count','permission_consumer',
        'permission_restricted_filesystem','permission_restricted_network','permission_hooks_enabled',
        'permission_startup_warning_count','permission_windows_sandbox','guest_acl_boundary',
        'raw_content_persisted','artifact_sidecars'
    )
    Assert-ExactFields $Measurements $fields 'measured desktop proof'
    if ($Measurements.fresh_iso_applied -ne $true -or
        $Measurements.enhanced_session_enabled -ne $false -or
        $Measurements.guest_service_interface_enabled -ne $false -or
        $Measurements.host_profile_mounted -ne $false -or
        $Measurements.host_shared_folders -ne $false -or
        [string]$Measurements.network_policy_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [int]$Measurements.enabled_allow_rules -ne $ExpectedAllowRules -or
        [int]$Measurements.outside_allow_rules -ne 0 -or
        [int]$Measurements.preauth_api_key_variables -ne 0 -or
        [int]$Measurements.preauth_credential_targets -ne 0 -or
        [int]$Measurements.preauth_network_mappings -ne 0 -or
        [int]$Measurements.preauth_auth_files -ne 0 -or
        [string]$Measurements.auth_storage_mode -cne 'file' -or
        [int]$Measurements.postauth_credential_targets -ne 0 -or
        [int]$Measurements.postauth_auth_files -ne 1 -or
        $Measurements.auth_prompt_ready -ne $true -or
        $Measurements.auth_completed -ne $true -or
        [string]$Measurements.app_account_mode -cne 'chatgpt' -or
        [string]$Measurements.permission_profile_id -cne 'desktop-proof' -or
        [string]$Measurements.permission_consumer -cne 'codex-sandbox-permission-profile' -or
        $Measurements.permission_restricted_filesystem -ne $true -or
        $Measurements.permission_restricted_network -ne $true -or
        $Measurements.permission_hooks_enabled -ne $false -or
        [int]$Measurements.permission_startup_warning_count -ne 0 -or
        [string]$Measurements.permission_windows_sandbox -cne 'elevated' -or
        $Measurements.guest_acl_boundary -ne $true -or
        $Measurements.auth_canary_denied -ne $true -or
        $Measurements.auth_canary_content_observed -ne $false -or
        [int]$Measurements.eligible_runtime_process_count -ne 1 -or
        $Measurements.raw_content_persisted -ne $false -or
        [int]$Measurements.artifact_sidecars -ne 0) {
        throw 'measured desktop proof contains an unsafe or unobserved outcome'
    }
}

function New-BrokerLifecycle {
    [pscustomobject]@{
        Trace = [Collections.Generic.List[string]]::new()
        Errors = [Collections.Generic.List[string]]::new()
        AttemptedCleanup = [Collections.Generic.List[string]]::new()
        CleanupAttempts = [ordered]@{}
        CleanupObservations = [ordered]@{}
        ForwardIndex = 0
        CleanupIndex = 0
        CleanupRetryExhausted = $false
        Failed = $false
    }
}

$script:BrokerForwardStages = @(
    'contract-verified','iso-applied-to-fresh-vhdx','isolation-measured',
    'identity-created','network-policy-installed','codex-permission-profile-proven','autologon-secret-cleared',
    'device-auth-prompt-ready','device-auth-completed','desktop-route-observed',
    'network-policy-measured'
)
$script:BrokerCleanupStages = @(
    'account-disabled','account-deleted','profile-destroyed','vm-destroyed',
    'run-root-destroyed','artifact-inventory-cleared'
)

function Invoke-BrokerStage($Lifecycle, [string]$Name, [scriptblock]$Operation, [string]$FailAfter) {
    if ($Lifecycle.Failed -or $Lifecycle.ForwardIndex -ge $script:BrokerForwardStages.Count -or
        $script:BrokerForwardStages[$Lifecycle.ForwardIndex] -cne $Name) {
        throw "broker forward transition is invalid: $Name"
    }
    $result = & $Operation
    $null = $Lifecycle.Trace.Add($Name)
    $Lifecycle.ForwardIndex++
    if ($FailAfter -and $Name -ceq $FailAfter) { throw "injected failure after $Name" }
    $result
}

function Invoke-BrokerCleanupStage($Lifecycle, [string]$Name, [scriptblock]$Operation, [string]$FailAfter) {
    if ($Lifecycle.CleanupIndex -ge $script:BrokerCleanupStages.Count -or
        $script:BrokerCleanupStages[$Lifecycle.CleanupIndex] -cne $Name) {
        throw "broker cleanup transition is invalid: $Name"
    }
    $null = $Lifecycle.AttemptedCleanup.Add($Name)
    try {
        $result = & $Operation
        $null = $Lifecycle.Trace.Add($Name)
        if ($FailAfter -and $Name -ceq $FailAfter) { throw "injected failure after $Name" }
        $result
    } catch {
        $Lifecycle.Failed = $true
        $null = $Lifecycle.Errors.Add($_.Exception.Message)
    } finally {
        $Lifecycle.CleanupIndex++
    }
}

function Invoke-BoundedCleanupOperation(
    $Lifecycle,
    [string]$Name,
    [scriptblock]$Operation,
    [scriptblock]$Verify,
    [int]$MaxAttempts = 3,
    [int]$DelayMilliseconds = 200
) {
    if ($MaxAttempts -lt 1 -or $MaxAttempts -gt 5 -or $DelayMilliseconds -lt 0 -or $DelayMilliseconds -gt 2000) {
        throw 'cleanup retry policy is outside the reviewed bounds'
    }
    $lastError = $null
    for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
        $Lifecycle.CleanupAttempts[$Name] = $attempt
        try {
            $null = & $Operation
            if (-not (& $Verify)) { throw "$Name absence was not observed" }
            $Lifecycle.CleanupObservations[$Name] = $true
            return $true
        } catch {
            $lastError = $_.Exception
            if ($attempt -lt $MaxAttempts -and $DelayMilliseconds -gt 0) {
                Start-Sleep -Milliseconds $DelayMilliseconds
            }
        }
    }
    $Lifecycle.CleanupRetryExhausted = $true
    $Lifecycle.CleanupObservations[$Name] = $false
    throw "$Name cleanup retry exhausted after $MaxAttempts attempt(s): $($lastError.Message)"
}

function Assert-BrokerCleanupObservations($Lifecycle, [Collections.IDictionary]$Observations) {
    $required = @(
        'account-disabled','account-deleted','profile-destroyed','vm-destroyed',
        'vhdx-destroyed','run-root-destroyed','receipt-absent'
    )
    $missing = [Collections.Generic.List[string]]::new()
    foreach ($name in $required) {
        $observed = $Observations.Contains($name) -and [bool]$Observations[$name]
        $Lifecycle.CleanupObservations[$name] = $observed
        if (-not $observed) { $null = $missing.Add($name) }
    }
    if ($missing.Count -gt 0) {
        throw "final cleanup absence was not observed: $($missing -join ', ')"
    }
    $true
}

function Write-BrokerReceiptArtifact(
    [string]$ReceiptPath,
    [string]$Serialized,
    [string]$TestFailure = ''
) {
    $receiptDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($ReceiptPath))
    $receiptLeaf = Split-Path -Leaf $ReceiptPath
    $Serialized | Set-Content -LiteralPath $ReceiptPath -Encoding utf8NoBOM -ErrorAction Stop
    if($TestFailure -ceq 'write-after-persist'){
        throw 'injected receipt failure after bytes persisted'
    }
    if($TestFailure -ceq 'post-write-inventory'){
        throw 'injected post-write receipt inventory failure'
    }
    $ownedArtifacts = @(Get-ChildItem -LiteralPath $receiptDirectory -File -ErrorAction Stop |
        Where-Object { $_.Name.StartsWith($receiptLeaf,[StringComparison]::OrdinalIgnoreCase) })
    if($ownedArtifacts.Count-ne 1-or[IO.Path]::GetFullPath($ownedArtifacts[0].FullName)-cne[IO.Path]::GetFullPath($ReceiptPath)){
        Remove-Item -LiteralPath $ReceiptPath -Force -ErrorAction SilentlyContinue
        throw 'broker produced durable artifacts other than the finalized receipt'
    }
    $true
}

function Remove-BrokerReceiptAfterFailure(
    $Lifecycle,
    [string]$ReceiptPath,
    [switch]$TestAlwaysFail
) {
    try {
        $null = Invoke-BoundedCleanupOperation $Lifecycle 'receipt-absent' {
            if($TestAlwaysFail){throw 'injected receipt removal failure'}
            if(Test-Path -LiteralPath $ReceiptPath){
                Remove-Item -LiteralPath $ReceiptPath -Force -ErrorAction Stop
            }
        } { -not(Test-Path -LiteralPath $ReceiptPath) } 3 200
    } catch {
        if($Lifecycle.Errors -notcontains $_.Exception.Message){$null=$Lifecycle.Errors.Add($_.Exception.Message)}
    }
}

function New-BrokerReportedFailure($Failure, $Lifecycle) {
    $cleanupErrors = @($Lifecycle.Errors | Select-Object -Unique)
    if($cleanupErrors.Count){
        return [InvalidOperationException]::new(
            "$($Failure.Exception.Message) | cleanup blockers: $($cleanupErrors -join '; ')",
            $Failure.Exception
        )
    }
    $Failure.Exception
}

function Invoke-BrokerFailureFinalization(
    $Lifecycle,
    $Failure,
    [string]$ReceiptPath,
    [scriptblock]$ObserveCleanup,
    [switch]$TestReceiptCleanupFailure
) {
    Remove-BrokerReceiptAfterFailure $Lifecycle $ReceiptPath -TestAlwaysFail:$TestReceiptCleanupFailure
    $observations = & $ObserveCleanup
    try {
        $null = Assert-BrokerCleanupObservations $Lifecycle $observations
    } catch {
        if($Lifecycle.Errors -notcontains $_.Exception.Message){$null=$Lifecycle.Errors.Add($_.Exception.Message)}
    }
    throw (New-BrokerReportedFailure $Failure $Lifecycle)
}

function Invoke-BrokerReceiptFailureFixture(
    [string]$Failure,
    [string]$FixturePath,
    [switch]$TestCleanupFailure
) {
    $lifecycle = New-BrokerLifecycle
    $receiptPath = Join-Path (Split-Path -Parent ([IO.Path]::GetFullPath($FixturePath))) 'late-pass-receipt.json'
    $original = $null
    try {
        $null = Write-BrokerReceiptArtifact $receiptPath '{"verdict":"PASS"}' $Failure
        throw 'receipt failure fixture did not inject its required failure'
    } catch {
        $original = $_
    }
    $reported = $null
    try {
        Invoke-BrokerFailureFinalization $lifecycle $original $receiptPath {
            [ordered]@{
                'account-disabled' = $true
                'account-deleted' = $true
                'profile-destroyed' = $true
                'vm-destroyed' = $true
                'vhdx-destroyed' = $true
                'run-root-destroyed' = $true
                'receipt-absent' = -not(Test-Path -LiteralPath $receiptPath)
            }
        } -TestReceiptCleanupFailure:$TestCleanupFailure
    } catch {
        $reported = $_.Exception
    }
    $cleanupErrors = @($lifecycle.Errors | Select-Object -Unique)
    [pscustomobject]@{
        ExitCode = 1
        Json = ([ordered]@{
            test_result='FAILED';trace=@($lifecycle.Trace);receipt_would_finalize=$false
            receipt_absent=-not(Test-Path -LiteralPath $receiptPath)
            cleanup_attempts=$lifecycle.CleanupAttempts;cleanup_observations=$lifecycle.CleanupObservations
            original_failure=$original.Exception.Message;reported_failure=$reported.Message
            inner_failure=if($reported.InnerException){$reported.InnerException.Message}else{$null}
            cleanup_errors=$cleanupErrors
        } | ConvertTo-Json -Compress)
    }
}

function Complete-BrokerLifecycle($Lifecycle) {
    if ($Lifecycle.Failed -or
        $Lifecycle.ForwardIndex -ne $script:BrokerForwardStages.Count -or
        $Lifecycle.CleanupIndex -ne $script:BrokerCleanupStages.Count) {
        throw 'broker lifecycle is not eligible for receipt finalization'
    }
    $null = $Lifecycle.Trace.Add('receipt-finalized')
}

function Invoke-BrokerFixtureStateMachine([string]$FailAfter, [string]$CleanupFailure) {
    $lifecycle = New-BrokerLifecycle
    $cleanupState = [ordered]@{
        'account-disabled' = $false
        'account-deleted' = $false
        'profile-destroyed' = $false
        'vm-destroyed' = $false
        'vhdx-destroyed' = $false
        'run-root-destroyed' = $false
        'receipt-absent' = $true
        'artifact-inventory-cleared' = $false
    }
    $cleanupTarget = ''
    $cleanupMode = ''
    if ($CleanupFailure) {
        $cleanupTarget, $cleanupMode = $CleanupFailure.Split(':', 2)
    }
    try {
        foreach ($stage in $script:BrokerForwardStages) {
            $null = Invoke-BrokerStage $lifecycle $stage { $true } $FailAfter
        }
    } catch {
        $lifecycle.Failed = $true
        $null = $lifecycle.Errors.Add($_.Exception.Message)
    } finally {
        foreach ($stage in $script:BrokerCleanupStages) {
            $null = Invoke-BrokerCleanupStage $lifecycle $stage {
                if ($stage -in @('vm-destroyed','run-root-destroyed')) {
                    $null = Invoke-BoundedCleanupOperation $lifecycle $stage {
                        $attempt = [int]$lifecycle.CleanupAttempts[$stage]
                        if ($stage -ceq $cleanupTarget -and ($cleanupMode -ceq 'always' -or $attempt -eq 1)) {
                            throw "injected cleanup operation failure for $stage"
                        }
                        $cleanupState[$stage] = $true
                        if ($stage -ceq 'run-root-destroyed') { $cleanupState['vhdx-destroyed'] = $true }
                    } { [bool]$cleanupState[$stage] } 3 0
                } else {
                    $lifecycle.CleanupAttempts[$stage] = 1
                    $cleanupState[$stage] = $true
                }
                $true
            } $FailAfter
        }
    }
    try {
        $null = Assert-BrokerCleanupObservations $lifecycle $cleanupState
        Complete-BrokerLifecycle $lifecycle
        [pscustomobject]@{
            ExitCode = 0
            Json = ([ordered]@{
                test_result='SUCCEEDED';trace=@($lifecycle.Trace);receipt_would_finalize=$true
                attempted_cleanup=@($lifecycle.AttemptedCleanup);cleanup_attempts=$lifecycle.CleanupAttempts
                cleanup_observations=$lifecycle.CleanupObservations;cleanup_retry_exhausted=$lifecycle.CleanupRetryExhausted
            } |
                ConvertTo-Json -Compress)
        }
    } catch {
        if ($lifecycle.Errors -notcontains $_.Exception.Message) {
            $null = $lifecycle.Errors.Add($_.Exception.Message)
        }
        [pscustomobject]@{
            ExitCode = 1
            Json = ([ordered]@{
                test_result='FAILED';trace=@($lifecycle.Trace);receipt_would_finalize=$false
                attempted_cleanup=@($lifecycle.AttemptedCleanup);cleanup_attempts=$lifecycle.CleanupAttempts
                cleanup_observations=$lifecycle.CleanupObservations
                cleanup_retry_exhausted=$lifecycle.CleanupRetryExhausted;cleanup_errors=@($lifecycle.Errors)
            } |
                ConvertTo-Json -Compress)
        }
    }
}

function Wait-DirectSession([string]$VMName, [PSCredential]$Credential) {
    $deadline = [DateTime]::UtcNow.AddMinutes(8)
    do {
        try { return New-PSSession -VMName $VMName -Credential $Credential -ErrorAction Stop }
        catch { Start-Sleep -Seconds 3 }
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'PowerShell Direct did not become available before timeout'
}

function Remove-EphemeralVm([string]$VMName, [string]$RunRoot) {
    if ($VMName -and (Get-VM -Name $VMName -ErrorAction SilentlyContinue)) {
        Stop-VM -Name $VMName -TurnOff -Force -ErrorAction SilentlyContinue
        Remove-VM -Name $VMName -Force -ErrorAction Stop
    }
    if ($RunRoot -and (Test-Path -LiteralPath $RunRoot)) {
        Remove-Item -LiteralPath $RunRoot -Recurse -Force
    }
}

function New-FreshGuestDisk {
    param([string]$IsoPath, [string]$DiskPath, [string]$BootstrapPassword)
    $mountedIso = $null
    $mountedVhd = $null
    $applied = $null
    try {
        $mountedIso = Mount-DiskImage -ImagePath $IsoPath -PassThru -ErrorAction Stop
        $isoVolume = $mountedIso | Get-Volume | Where-Object DriveLetter | Select-Object -First 1
        if ($null -eq $isoVolume) { throw 'approved evaluation ISO did not expose a volume' }
        $imagePath = @(
            "$($isoVolume.DriveLetter):\sources\install.wim",
            "$($isoVolume.DriveLetter):\sources\install.esd"
        ) | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
        if (-not $imagePath) { throw 'approved evaluation ISO lacks install.wim/install.esd' }
        $windowsImage = @(Get-WindowsImage -ImagePath $imagePath | Where-Object {
            $_.ImageName -match '(?i)^Windows 11 Enterprise Evaluation$'
        })
        if ($windowsImage.Count -ne 1) { throw 'approved Enterprise Evaluation image index is ambiguous' }

        New-VHD -Path $DiskPath -Dynamic -SizeBytes 96GB -BlockSizeBytes 1MB | Out-Null
        $mountedVhd = Mount-VHD -Path $DiskPath -PassThru -NoDriveLetter
        $disk = $mountedVhd | Get-Disk
        Initialize-Disk -Number $disk.Number -PartitionStyle GPT | Out-Null
        $efi = New-Partition -DiskNumber $disk.Number -Size 260MB -AssignDriveLetter -GptType '{c12a7328-f81f-11d2-ba4b-00a0c93ec93b}'
        $null = Format-Volume -Partition $efi -FileSystem FAT32 -NewFileSystemLabel SYSTEM -Confirm:$false
        $null = New-Partition -DiskNumber $disk.Number -Size 16MB -GptType '{e3c9e316-0b5c-4db8-817d-f92df00215ae}'
        $os = New-Partition -DiskNumber $disk.Number -UseMaximumSize -AssignDriveLetter
        $null = Format-Volume -Partition $os -FileSystem NTFS -NewFileSystemLabel WINDOWS -Confirm:$false
        $osRoot = "$($os.DriveLetter):\"
        $efiRoot = "$($efi.DriveLetter):"
        Expand-WindowsImage -ImagePath $imagePath -Index $windowsImage[0].ImageIndex -ApplyPath $osRoot |
            Out-Null
        & bcdboot.exe "$osRoot`Windows" /s $efiRoot /f UEFI | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'could not create the fresh guest boot files' }

        $escaped = [Security.SecurityElement]::Escape($BootstrapPassword)
        $unattend = @"
<?xml version="1.0" encoding="utf-8"?>
<unattend xmlns="urn:schemas-microsoft-com:unattend">
  <settings pass="oobeSystem">
    <component name="Microsoft-Windows-International-Core" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
      <InputLocale>en-US</InputLocale><SystemLocale>en-US</SystemLocale><UILanguage>en-US</UILanguage><UserLocale>en-US</UserLocale>
    </component>
    <component name="Microsoft-Windows-Shell-Setup" processorArchitecture="amd64" publicKeyToken="31bf3856ad364e35" language="neutral" versionScope="nonSxS" xmlns:wcm="http://schemas.microsoft.com/WMIConfig/2002/State">
      <OOBE><HideEULAPage>true</HideEULAPage><HideOnlineAccountScreens>true</HideOnlineAccountScreens><ProtectYourPC>3</ProtectYourPC></OOBE>
      <UserAccounts><LocalAccounts><LocalAccount wcm:action="add"><Name>ca-bootstrap</Name><Group>Administrators</Group><Password><Value>$escaped</Value><PlainText>true</PlainText></Password></LocalAccount></LocalAccounts></UserAccounts>
    </component>
  </settings>
</unattend>
"@
        $panther = Join-Path $osRoot 'Windows\Panther'
        New-Item -ItemType Directory -Path $panther -Force | Out-Null
        $unattend | Set-Content -LiteralPath (Join-Path $panther 'Unattend.xml') -Encoding utf8NoBOM
        $applied = [pscustomobject]@{
            fresh_iso_applied = $true
            image_name = [string]$windowsImage[0].ImageName
            image_index = [int]$windowsImage[0].ImageIndex
            disk_path = [IO.Path]::GetFullPath($DiskPath)
        }
    } finally {
        if ($mountedVhd) { Dismount-VHD -Path $DiskPath -ErrorAction SilentlyContinue }
        if ($mountedIso) { Dismount-DiskImage -ImagePath $IsoPath -ErrorAction SilentlyContinue }
    }
    if ($null -eq $applied -or -not (Test-Path -LiteralPath $DiskPath -PathType Leaf)) {
        throw 'fresh evaluation image application was not observed'
    }
    $applied
}

function Get-StorePackageEvidence($Contract, [string]$ExpectedBuild) {
    $package = Get-AppxPackage $Contract.application.package_name |
        Sort-Object Version -Descending | Select-Object -First 1
    if ($null -eq $package -or $package.Publisher -cne $Contract.application.publisher -or
        $package.Version.ToString() -cne $ExpectedBuild -or
        $package.PackageFullName -notmatch $Contract.application.package_full_name_regex) {
        throw 'host Store/MSIX Codex package does not match the requested reviewed build'
    }
    $desktop = Join-Path $package.InstallLocation $Contract.application.executable_relative_path
    $runtime = Join-Path $package.InstallLocation $Contract.application.runtime_relative_path
    foreach ($path in @($desktop,$runtime)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-AuthenticodeSignature $path).Status -ne 'Valid') {
            throw 'Store/MSIX executable signature is invalid'
        }
    }
    [pscustomobject]@{
        Package = $package; DesktopPath = $desktop; RuntimePath = $runtime
        DesktopSha256 = Get-Sha256 $desktop; RuntimeSha256 = Get-Sha256 $runtime
    }
}

$loaded = Get-Contract
$contract = $loaded.Contract
if ($ContractOnly -or $PSCmdlet.ParameterSetName -eq 'Contract') {
    [ordered]@{
        verdict='PASS'; broker_sha256=$contract.broker.sha256; driver_sha256=$contract.driver.sha256
        probe_sha256=$contract.probe.sha256; image_sha256=$contract.image.sha256
        provisioning_mode=$contract.image.provisioning_mode; route_corpus_id=$contract.route_corpus.id
    } | ConvertTo-Json -Compress
    exit 0
}
if ($PSCmdlet.ParameterSetName -eq 'CandidateSurfaceFixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'candidate surface fixture mode is test-only' }
    $fixture = Get-Content -LiteralPath $CandidateSurfaceFixturePath -Raw -Encoding utf8 | ConvertFrom-Json
    Assert-ExactFields $fixture @('schema_version','manifest','hooks_manifest_text','paths') 'candidate surface fixture'
    if ($fixture.schema_version -ne 1) { throw 'candidate surface fixture schema is invalid' }
    Assert-BoundedCandidateSurface -Manifest $fixture.manifest -HooksManifestText ([string]$fixture.hooks_manifest_text) -Paths @($fixture.paths) | ConvertTo-Json -Compress
    exit 0
}
if ($PSCmdlet.ParameterSetName -eq 'ReceiptContractFixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'receipt contract fixture mode is test-only' }
    $fixture = Get-Content -LiteralPath $ReceiptContractFixturePath -Raw -Encoding utf8 | ConvertFrom-Json
    New-ReceiptPolicyAndChannel $fixture $contract | ConvertTo-Json -Depth 6 -Compress
    exit 0
}
if ($PSCmdlet.ParameterSetName -eq 'ArchiveExtractionFixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'archive extraction fixture mode is test-only' }
    Expand-BoundedCandidateArchive -ArchivePath $ArchiveExtractionFixturePath -DestinationPath $ArchiveExtractionDestination -Contract $contract |
        ConvertTo-Json -Compress
    exit 0
}
if ($PSCmdlet.ParameterSetName -eq 'CandidateMetadataFixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'candidate metadata fixture mode is test-only' }
    Get-CandidateMetadata $CandidateMetadataFixturePath (Join-Path $loaded.Root '.github\scripts\check_codex_skill_resources.py') |
        ConvertTo-Json -Compress
    exit 0
}
if ($PSCmdlet.ParameterSetName -eq 'Fixture') {
    if ($env:CODEARBITER_DESKTOP_BOUNDARY_TEST -cne '1') { throw 'fixture mode is test-only' }
    $fixture = Get-Content -LiteralPath $FixturePath -Raw -Encoding utf8 | ConvertFrom-Json
    if ($fixture.schema_version -ne 1) { throw 'broker fixture schema is invalid' }
    Assert-ExactFields $fixture @('schema_version','runner_sid','acl_chain','channel','route_response','measurements') 'broker fixture'
    foreach ($aclEvidence in @($fixture.acl_chain)) { Assert-TrustedAclEvidence $aclEvidence $fixture.runner_sid }
    if ((Get-RouteResponseBinding $fixture.route_response) -cne [string]$fixture.channel.response_binding_sha256) {
        throw 'broker fixture route response binding is invalid'
    }
    Assert-ChannelResponse $fixture.channel
    Assert-MeasuredProof $fixture.measurements (2 * @($contract.network.https_fqdns).Count)
    if($TestReceiptFailure){
        $result = Invoke-BrokerReceiptFailureFixture $TestReceiptFailure $FixturePath -TestCleanupFailure:$TestReceiptCleanupFailure
        Write-Output $result.Json
        exit $result.ExitCode
    }
    $result = Invoke-BrokerFixtureStateMachine $TestFailAfter $TestCleanupFailure
    Write-Output $result.Json
    exit $result.ExitCode
}

if (-not $RequestPath -or -not $ReceiptPath) { throw 'RequestPath and ReceiptPath are required' }
if (Test-Path -LiteralPath $ReceiptPath) { throw 'desktop receipt path must not pre-exist' }
if (-not $IsWindows) { throw 'the protected desktop broker requires Windows' }
$hostIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = [Security.Principal.WindowsPrincipal]::new($hostIdentity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'the protected desktop broker requires visible, user-approved elevation'
}
if ((Get-VMHost).EnableEnhancedSessionMode) {
    throw 'enhanced session mode must be disabled to prevent clipboard or drive sharing'
}

$request = Get-Content -LiteralPath $RequestPath -Raw -Encoding utf8 | ConvertFrom-Json
$requestFields = @(
    'candidate_archive','candidate_archive_sha256','candidate_commit','candidate_tree','desktop_build','desktop_runtime_version','workflow_commit','run_id',
    'protected_environment','authentication_mode','user_consent_required','requested_approval',
    'required_effective_approval','requested_sandbox','required_effective_sandbox',
    'persist_auth_artifacts','persist_screenshots','persist_raw_ui_logs','persist_crash_dumps',
    'boundary_contract_sha256','broker_sha256','driver_sha256','probe_sha256','installed_driver',
    'installed_probe','image_path','image_sha256'
)
Assert-ExactFields $request $requestFields 'desktop proof request'
if ($request.authentication_mode -cne 'chatgpt-device' -or $request.user_consent_required -ne $true -or
    $request.requested_approval -cne 'never' -or $request.required_effective_approval -cne 'never' -or
    $request.requested_sandbox -cne 'read-only' -or $request.required_effective_sandbox -cne 'read-only') {
    throw 'desktop proof request violates the device-auth/read-only/never policy'
}
foreach ($field in @('persist_auth_artifacts','persist_screenshots','persist_raw_ui_logs','persist_crash_dumps')) {
    if ($request.$field -ne $false) { throw 'desktop proof request permits prohibited durable evidence' }
}
$installedDriver = Assert-TrustedRunnerPath $request.installed_driver -Leaf
$installedProbe = Assert-TrustedRunnerPath $request.installed_probe -Leaf
$imagePath = Assert-TrustedRunnerPath $request.image_path -Leaf
$protectedWorkingRoot = Assert-TrustedRunnerPath $WorkingRoot
foreach ($pair in @(
    @($request.broker_sha256,$contract.broker.sha256),
    @($request.driver_sha256,$contract.driver.sha256),
    @($request.probe_sha256,$contract.probe.sha256),
    @($request.image_sha256,$contract.image.sha256),
    @($request.boundary_contract_sha256,(Get-Sha256 $ContractPath)),
    @((Get-Sha256 $installedDriver),$contract.driver.sha256),
    @((Get-Sha256 $installedProbe),$contract.probe.sha256),
    @((Get-Sha256 $imagePath),$contract.image.sha256)
)) { if ($pair[0] -cne $pair[1]) { throw 'desktop request boundary or image bytes are not exact' } }
if ($request.candidate_archive_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
    $request.candidate_commit -notmatch '^[0-9a-f]{40}$' -or
    $request.candidate_tree -notmatch '^[0-9a-f]{40}$' -or
    $request.workflow_commit -notmatch '^[0-9a-f]{40}$' -or
    $request.run_id -notmatch '^[1-9][0-9]*$' -or
    $request.desktop_build -notmatch '^[0-9]+(?:\.[0-9]+){3}$' -or
    $request.desktop_runtime_version -notmatch '^[0-9][0-9A-Za-z._-]{0,63}$') {
    throw 'desktop request identities are invalid'
}

$archive = (Resolve-Path -LiteralPath $request.candidate_archive).Path
$candidateHash = Get-Sha256 $archive
if ($candidateHash -cne [string]$request.candidate_archive_sha256) {
    throw 'candidate archive does not match the workflow-authorized digest'
}
$store = Get-StorePackageEvidence $contract $request.desktop_build
$storeDesktopPath = Join-Path $store.Package.InstallLocation $contract.application.executable_relative_path
$storeRuntimePath = Join-Path $store.Package.InstallLocation $contract.application.runtime_relative_path
$storeDesktopSha = Get-Sha256 $storeDesktopPath
$storeRuntimeSha = Get-Sha256 $storeRuntimePath
if (-not (Get-VMSwitch -Name $VmSwitchName -ErrorAction SilentlyContinue)) {
    throw 'fixed CodeArbiter desktop-proof VM switch is missing'
}

$suffix = $request.run_id.Substring([Math]::Max(0, $request.run_id.Length - 10))
$vmName = "ca-desktop-$suffix"
$runRoot = Join-Path $WorkingRoot $vmName
$hostMarketplace = Join-Path $runRoot 'marketplace'
$hostPluginRoot = Join-Path $hostMarketplace 'plugins\ca-codex'
$diskPath = Join-Path $runRoot 'guest.vhdx'
$guestTrustedRoot = 'C:\CodeArbiterTrusted'
$guestRunRoot = 'C:\CodeArbiterProof'
$guestExchangeRoot = 'C:\CodeArbiterExchange'
$guestContract = Join-Path $guestTrustedRoot 'desktop-proof-boundary.json'
$guestDriver = Join-Path $guestTrustedRoot 'Invoke-CodeArbiterDesktopUiDriver.ps1'
$guestProbe = Join-Path $guestTrustedRoot 'Invoke-CodeArbiterDesktopRouteProbe.ps1'
$guestPackage = Join-Path $guestTrustedRoot 'StorePackage'
$proofRepo = Join-Path $guestRunRoot 'repo'
$observationPath = Join-Path $guestExchangeRoot 'driver-observation.json'
$permissionEvidencePath = Join-Path $guestExchangeRoot 'permission-evidence.json'
$inventoryEvidencePath = Join-Path $guestExchangeRoot 'inventory-evidence.json'
$frozenObservationPath = Join-Path $guestTrustedRoot 'frozen-driver-observation.json'
$account = "ca-desktop-disposable-$suffix"
$candidate = $null
$permissionProfile = $null
$bootstrapPassword = (Get-RandomHex 24) + '!aA1'
$desktopPassword = (Get-RandomHex 24) + '!aA1'
$bootstrapSecure = ConvertTo-SecureString $bootstrapPassword -AsPlainText -Force
$bootstrap = [PSCredential]::new('.\ca-bootstrap',$bootstrapSecure)
$challengeKey = Get-RandomHex 32
$challengeNonce = Get-RandomHex 32
$brokerSha = Get-TextSha256 $hostIdentity.User.Value
$session = $null
$vmConnect = $null
$route = $null
$driverObservation = $null
$setup = $null
$networkEvidence = $null
$diskEvidence = $null
$hostIsolation = $null
$preAuthEvidence = $null
$postAuthEvidence = $null
$measurements = $null
$authCompletionObserved = $false
$torn = $null
$lifecycle = New-BrokerLifecycle

try {
    $null = Invoke-BrokerStage $lifecycle 'contract-verified' { $true } ''
    if (Test-Path -LiteralPath $runRoot) { throw 'ephemeral run root already exists' }
    $null = New-Item -ItemType Directory -Path $runRoot -Force
    $null = Assert-TrustedRunnerPath $runRoot
    $archiveEvidence = Expand-BoundedCandidateArchive -ArchivePath $archive -DestinationPath $hostPluginRoot -Contract $contract -ExpectedSha256 ([string]$request.candidate_archive_sha256)
    if ($archiveEvidence.file_count -lt 1 -or $archiveEvidence.total_uncompressed_bytes -lt 1) {
        throw 'candidate archive contains no regular-file payload'
    }
    $null = Assert-TrustedRunnerPath $hostPluginRoot
    $candidate = Get-CandidateMetadata $hostPluginRoot (Join-Path $loaded.Root '.github\scripts\check_codex_skill_resources.py')
    $permissionProfile = New-DesktopProofPermissionProfile $contract $account $candidate.Version $proofRepo
    if ((Get-Sha256 $imagePath) -cne $contract.image.sha256) { throw 'approved image changed after boundary verification' }
    $diskEvidence = New-FreshGuestDisk $imagePath $diskPath $bootstrapPassword
    $null = Invoke-BrokerStage $lifecycle 'iso-applied-to-fresh-vhdx' {
        if ($diskEvidence.fresh_iso_applied -ne $true) { throw 'fresh ISO application was not measured' }
        $true
    } ''
    $null = New-VM -Name $vmName -Generation 2 -VHDPath $diskPath -SwitchName $VmSwitchName -MemoryStartupBytes 8GB
    Set-VM -Name $vmName -ProcessorCount 4 -AutomaticCheckpointsEnabled $false -CheckpointType Disabled
    Set-VMFirmware -VMName $vmName -EnableSecureBoot On -SecureBootTemplate MicrosoftWindows
    Disable-VMIntegrationService -VMName $vmName -Name 'Guest Service Interface'
    $hardDisks = @(Get-VMHardDiskDrive -VMName $vmName)
    $dvdMounts = @(Get-VMDvdDrive -VMName $vmName | Where-Object Path)
    $adapters = @(Get-VMNetworkAdapter -VMName $vmName)
    $guestService = Get-VMIntegrationService -VMName $vmName -Name 'Guest Service Interface'
    $expectedDisk = [IO.Path]::GetFullPath($diskPath)
    $hostProfileRoot = [IO.Path]::GetFullPath([Environment]::GetFolderPath('UserProfile')).TrimEnd('\') + '\'
    $attachedPaths = @($hardDisks.Path) + @($dvdMounts.Path)
    $hostIsolation = [pscustomobject]@{
        enhanced_session_enabled = [bool](Get-VMHost).EnableEnhancedSessionMode
        guest_service_interface_enabled = [bool]$guestService.Enabled
        host_profile_mounted = [bool]@($attachedPaths | Where-Object {
            [IO.Path]::GetFullPath([string]$_).StartsWith($hostProfileRoot,[StringComparison]::OrdinalIgnoreCase)
        }).Count
        host_shared_folders = [bool]$guestService.Enabled
    }
    if ($hardDisks.Count -ne 1 -or [IO.Path]::GetFullPath($hardDisks[0].Path) -cne $expectedDisk -or
        $dvdMounts.Count -ne 0 -or $adapters.Count -ne 1 -or $adapters[0].SwitchName -cne $VmSwitchName -or
        $hostIsolation.enhanced_session_enabled -or $hostIsolation.guest_service_interface_enabled -or
        $hostIsolation.host_profile_mounted -or $hostIsolation.host_shared_folders) {
        throw 'measured Hyper-V isolation does not match the reviewed boundary'
    }
    $null = Invoke-BrokerStage $lifecycle 'isolation-measured' { $true } ''
    $null = Start-VM -Name $vmName
    $session = Wait-DirectSession $vmName $bootstrap
    $vmId = (Get-VM -Name $vmName).Id.Guid.ToString('D')

    $setup = Invoke-Command -Session $session -ArgumentList $account,$desktopPassword,$guestTrustedRoot,$guestRunRoot,$guestExchangeRoot,$proofRepo,$contract.network,$permissionProfile.Toml -ScriptBlock {
        param($Account,$Password,$TrustedRoot,$RunRoot,$ExchangeRoot,$Repo,$Network,$PermissionToml)
        Remove-Item -LiteralPath 'C:\Windows\Panther\Unattend.xml' -Force -ErrorAction SilentlyContinue
        New-Item -ItemType Directory -Path $TrustedRoot,$RunRoot,$ExchangeRoot,$Repo -Force | Out-Null
        if (Get-LocalUser $Account -ErrorAction SilentlyContinue) { throw 'disposable account already exists' }
        $secure = ConvertTo-SecureString $Password -AsPlainText -Force
        New-LocalUser $Account -Password $secure -PasswordNeverExpires -UserMayNotChangePassword | Out-Null
        Add-LocalGroupMember -Group Users -Member $Account
        $sid = (Get-LocalUser $Account).Sid.Value
        $process = Start-Process cmd.exe -ArgumentList '/c exit 0' -Credential ([PSCredential]::new(".\$Account",$secure)) -LoadUserProfile -Wait -PassThru
        if ($process.ExitCode) { throw 'profile initialization failed' }
        $profile = Get-CimInstance Win32_UserProfile | Where-Object SID -eq $sid
        if ($profile.LocalPath -cne "C:\Users\$Account") { throw 'profile path invalid' }
        New-Item -ItemType Directory -Path (Join-Path $profile.LocalPath '.codex') -Force | Out-Null
        $PermissionToml | Set-Content -LiteralPath (Join-Path $profile.LocalPath '.codex\config.toml') -Encoding utf8NoBOM -Force
        'Write-Output "desktop proof fixture"' | Set-Content -LiteralPath (Join-Path $Repo 'desktop-proof-fixture.ps1') -Encoding utf8NoBOM
        foreach ($root in @($TrustedRoot,$RunRoot,$ExchangeRoot)) {
            & icacls.exe $root /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)(F)' '*S-1-5-32-544:(OI)(CI)(F)' | Out-Null
            if ($LASTEXITCODE) { throw "could not establish protected ACL on $root" }
        }
        & icacls.exe $TrustedRoot /grant:r "*$sid`:(OI)(CI)(RX)" | Out-Null
        if ($LASTEXITCODE) { throw 'could not grant disposable identity read-only trusted-root access' }
        & icacls.exe $RunRoot /grant:r "*$sid`:(OI)(CI)(RX)" | Out-Null
        if ($LASTEXITCODE) { throw 'could not grant disposable identity read-only run-root access' }
        & icacls.exe $ExchangeRoot /grant:r "*$sid`:(OI)(CI)(M)" | Out-Null
        if ($LASTEXITCODE) { throw 'could not grant disposable driver access to the observation exchange' }
        $aclEvidence = @{}
        foreach ($item in @(@($TrustedRoot,'trusted'),@($RunRoot,'run'),@($ExchangeRoot,'exchange'))) {
            $acl = Get-Acl -LiteralPath $item[0]
            $identities = @($acl.Access | ForEach-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value } | Sort-Object -Unique)
            $unexpected = @($identities | Where-Object { $_ -notin @('S-1-5-18','S-1-5-32-544',$sid) })
            $desktopRules = @($acl.Access | Where-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -ceq $sid })
            $desktopWritable = @($desktopRules | Where-Object { ([int]$_.FileSystemRights -band [int][Security.AccessControl.FileSystemRights]::Write) -ne 0 }).Count -gt 0
            $expectedWritable = $item[1] -ceq 'exchange'
            $aclEvidence[$item[1]] = $acl.AreAccessRulesCanonical -and $acl.AreAccessRulesProtected -and
                $unexpected.Count -eq 0 -and $desktopRules.Count -ge 1 -and $desktopWritable -eq $expectedWritable
        }
        if (@($aclEvidence.Values | Where-Object { $_ -ne $true }).Count) { throw 'guest trust-root ACL contract is not exact' }

        Get-NetFirewallRule -Direction Outbound -Action Allow -Enabled True -ErrorAction SilentlyContinue |
            Disable-NetFirewallRule | Out-Null
        Set-NetFirewallProfile -Profile Domain,Private,Public -DefaultOutboundAction Block
        $group = 'CodeArbiter Desktop Proof'
        Get-NetFirewallRule -DisplayGroup $group -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        $dns = @(Get-DnsClientServerAddress -AddressFamily IPv4 | ForEach-Object ServerAddresses |
            Where-Object { $_ } | Sort-Object -Unique)
        if (-not $dns.Count) { throw 'guest DNS server inventory is empty' }
        foreach ($protocol in $Network.dns_protocols) {
            New-NetFirewallRule -DisplayName "CA Desktop DNS $protocol" -DisplayGroup $group -Direction Outbound -Action Allow -Enabled True -Profile Any -Program "$env:SystemRoot\System32\svchost.exe" -Service Dnscache -Protocol $protocol -RemotePort $Network.dns_port -RemoteAddress $dns | Out-Null
        }
        $resolvedEndpoints = @()
        $hostLines = @()
        foreach ($fqdn in $Network.https_fqdns) {
            $addresses = @(
                Resolve-DnsName -Name $fqdn -Type A -DnsOnly -ErrorAction Stop
                Resolve-DnsName -Name $fqdn -Type AAAA -DnsOnly -ErrorAction SilentlyContinue
            ) | Where-Object IPAddress | ForEach-Object IPAddress | Sort-Object -Unique
            if (-not $addresses.Count) { throw 'reviewed endpoint did not resolve before DNS shutdown' }
            $resolvedEndpoints += [pscustomobject]@{fqdn=[string]$fqdn;addresses=@($addresses)}
            foreach($address in $addresses){$hostLines += "$address`t$fqdn"}
        }
        $hosts = "$env:SystemRoot\System32\drivers\etc\hosts"
        Add-Content -LiteralPath $hosts -Value @('', '# CodeArbiter desktop proof pinned endpoints') -Encoding ascii
        Add-Content -LiteralPath $hosts -Value $hostLines -Encoding ascii
        Get-NetFirewallRule -DisplayGroup $group -ErrorAction SilentlyContinue | Remove-NetFirewallRule
        Clear-DnsClientCache
        [pscustomobject]@{ sid=$sid; profile=$profile.LocalPath; resolved_endpoints=@($resolvedEndpoints); acl_evidence=$aclEvidence }
    }
    $desktopSid = [string]$setup.sid
    $profile = [string]$setup.profile
    $desktopSha = Get-TextSha256 $desktopSid
    if ($desktopSha -ceq $brokerSha) { throw 'desktop and broker identities match' }
    $null = Invoke-BrokerStage $lifecycle 'identity-created' { $true } ''

    $null = Assert-TrustedRunnerPath $installedDriver -Leaf
    $null = Assert-TrustedRunnerPath $installedProbe -Leaf
    if ((Get-Sha256 $installedDriver) -cne $contract.driver.sha256 -or
        (Get-Sha256 $installedProbe) -cne $contract.probe.sha256) { throw 'trusted boundary program changed before guest transfer' }
    Copy-Item -ToSession $session -LiteralPath $hostMarketplace -Destination $guestRunRoot -Recurse -Force
    Copy-Item -ToSession $session -LiteralPath $ContractPath -Destination $guestContract
    Copy-Item -ToSession $session -LiteralPath $installedDriver -Destination $guestDriver
    Copy-Item -ToSession $session -LiteralPath $installedProbe -Destination $guestProbe
    Copy-Item -ToSession $session -LiteralPath $store.Package.InstallLocation -Destination $guestPackage -Recurse
    $guestDesktopResource = Join-Path $guestPackage $contract.application.executable_relative_path
    $guestRuntimeResource = Join-Path $guestPackage $contract.application.runtime_relative_path
    $guestBoundaryBindings = @{
        $guestContract = Get-Sha256 $ContractPath
        $guestDriver = [string]$contract.driver.sha256
        $guestProbe = [string]$contract.probe.sha256
        $guestDesktopResource = $storeDesktopSha
        $guestRuntimeResource = $storeRuntimeSha
    }
    Assert-GuestTrustedBytes -Session $session -Bindings $guestBoundaryBindings

    $installed = Invoke-Command -Session $session -ArgumentList $account,$desktopPassword,$profile,$guestRunRoot,$guestPackage,$candidate.Version,$contract,$setup.resolved_endpoints -ScriptBlock {
        param($Account,$Password,$Profile,$Root,$PackageRoot,$Version,$Contract,$ResolvedEndpoints)
        $manifest = Join-Path $PackageRoot 'AppxManifest.xml'
        $desktop = Join-Path $PackageRoot $Contract.application.executable_relative_path
        $runtime = Join-Path $PackageRoot $Contract.application.runtime_relative_path
        foreach ($path in @($manifest,$desktop,$runtime)) { if (-not(Test-Path -LiteralPath $path -PathType Leaf)){throw 'copied Store package is incomplete'} }
        $group='CodeArbiter Desktop Proof'
        for($index=0;$index-lt@($ResolvedEndpoints).Count;$index++) {
            $addresses=@($ResolvedEndpoints[$index].addresses)
            New-NetFirewallRule -DisplayName "CA Desktop CLI HTTPS $index" -DisplayGroup $group -Direction Outbound -Action Allow -Enabled True -Profile Any -Program $runtime -Protocol TCP -RemotePort 443 -RemoteAddress $addresses | Out-Null
            New-NetFirewallRule -DisplayName "CA Desktop App HTTPS $index" -DisplayGroup $group -Direction Outbound -Action Allow -Enabled True -Profile Any -Program $desktop -Protocol TCP -RemotePort 443 -RemoteAddress $addresses | Out-Null
        }
        $market=Join-Path $Root 'marketplace'
        if(-not(Test-Path -LiteralPath (Join-Path $market 'plugins\ca-codex') -PathType Container)){throw 'validated candidate marketplace root is missing'}
        New-Item -ItemType Directory (Join-Path $market '.codex-plugin') -Force | Out-Null
        @{name='codearbiter';plugins=@(@{name='ca-codex';source=@{source='local';path='./plugins/ca-codex'};policy=@{installation='AVAILABLE';authentication='ON_INSTALL'};category='Developer Tools'})} |
            ConvertTo-Json -Depth 8 | Set-Content (Join-Path $market '.codex-plugin\marketplace.json') -Encoding utf8
        $secure=ConvertTo-SecureString $Password -AsPlainText -Force
        foreach($spec in @(@("Add-AppxPackage -Register '$manifest' -DisableDevelopmentMode",'Register'),@("& '$runtime' plugin marketplace add '$market'",'Market'),@("& '$runtime' plugin add ca-codex@codearbiter",'Install'))) {
            $task="CodeArbiter-$($spec[1])"; $action=New-ScheduledTaskAction powershell.exe -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$($spec[0])`""
            Register-ScheduledTask $task -Action $action -User $Account -Password $Password -RunLevel Limited -Force | Out-Null
            try { Start-ScheduledTask $task; do{Start-Sleep -Milliseconds 500;$info=Get-ScheduledTaskInfo $task}while($info.LastTaskResult-eq 267009);if($info.LastTaskResult){throw "desktop setup task $task failed"} }
            finally { Unregister-ScheduledTask $task -Confirm:$false -ErrorAction SilentlyContinue }
        }
        $plugin=Join-Path $Profile ".codex\plugins\cache\codearbiter\ca-codex\$Version"
        if(-not(Test-Path $plugin -PathType Container)){throw 'versioned marketplace root missing'}
        $package=Get-AppxPackage -User $Account $Contract.application.package_name | Select-Object -First 1
        [pscustomobject]@{plugin=$plugin;package=$package.PackageFullName;desktop=$desktop;runtime=$runtime}
    }
    if ($installed.package -notmatch $contract.application.package_full_name_regex) {
        throw 'guest Store package identity is invalid'
    }
    $null = Invoke-BrokerStage $lifecycle 'network-policy-installed' { $true } ''

    $preAuthEvidence = Invoke-Command -Session $session -ArgumentList $account,$desktopPassword,$profile,$guestTrustedRoot,$guestExchangeRoot -ScriptBlock {
        param($Account,$Password,$Profile,$TrustedRoot,$ExchangeRoot)
        $script = Join-Path $TrustedRoot 'Measure-PreAuthIsolation.ps1'
        $output = Join-Path $ExchangeRoot 'preauth-isolation.json'
        @"
`$apiVariables=@(Get-ChildItem Env:|Where-Object Name -match '^(OPENAI|CODEX)_API_KEY$').Count
if(-not(Test-Path -LiteralPath '$Profile\.codex' -PathType Container)){throw 'pre-auth Codex root is missing'}
`$credentialOutput=@(cmdkey.exe /list 2>&1);if(`$LASTEXITCODE-ne 0){throw 'pre-auth Credential Manager inventory failed'}
`$credentialTargets=@(`$credentialOutput|Select-String '^\s*Target:').Count
`$mappings=@(Get-SmbMapping -ErrorAction Stop).Count+@(Get-CimInstance Win32_LogicalDisk -ErrorAction Stop|Where-Object DriveType -eq 4).Count
`$authFiles=@(Get-ChildItem -LiteralPath '$Profile\.codex' -Recurse -File -ErrorAction Stop|Where-Object Name -match '^(auth|credentials?|cookies?|sessions?|tokens?)(\.|$)').Count
@{schema_version=1;api_key_variables=`$apiVariables;credential_targets=`$credentialTargets;network_mappings=`$mappings;preexisting_auth_files=`$authFiles}|ConvertTo-Json|Set-Content -LiteralPath '$output' -Encoding utf8NoBOM
"@ | Set-Content -LiteralPath $script -Encoding utf8NoBOM
        $action=New-ScheduledTaskAction powershell.exe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
        Register-ScheduledTask 'CodeArbiter-PreAuthIsolation' -Action $action -User $Account -Password $Password -RunLevel Limited -Force|Out-Null
        try {
            Start-ScheduledTask 'CodeArbiter-PreAuthIsolation'
            $deadline=[DateTime]::UtcNow.AddMinutes(1)
            do{Start-Sleep -Milliseconds 500}while(-not(Test-Path $output)-and[DateTime]::UtcNow-lt$deadline)
            if(-not(Test-Path $output)){throw 'pre-auth isolation measurement timed out'}
            $value=Get-Content -LiteralPath $output -Raw -Encoding utf8|ConvertFrom-Json
            if($value.schema_version-ne 1-or$value.api_key_variables-ne 0-or$value.credential_targets-ne 0-or$value.network_mappings-ne 0-or$value.preexisting_auth_files-ne 0){throw 'disposable profile contains copied credentials, API-key state, or host mappings'}
            $value
        } finally {
            Unregister-ScheduledTask 'CodeArbiter-PreAuthIsolation' -Confirm:$false -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $script,$output -Force -ErrorAction SilentlyContinue
        }
    }

    $authCanaryContent = 'CODEARBITER-DESKTOP-CANARY-' + (Get-RandomHex 16)
    $authCanaryPath = Join-Path (Join-Path $profile '.codex') ([string]$contract.authentication.denial_canary_filename)
    $permissionPlaceholders = Invoke-Command -Session $session -ArgumentList $profile,$authCanaryPath,$authCanaryContent -ScriptBlock {
        param($Profile,$CanaryPath,$CanaryContent)
        $auth = Join-Path $Profile '.codex\auth.json'
        $sidecar = $auth + '.lock'
        '{"desktop_proof_placeholder":true}' | Set-Content -LiteralPath $auth -Encoding utf8NoBOM -NoNewline
        'desktop-proof-placeholder' | Set-Content -LiteralPath $sidecar -Encoding utf8NoBOM -NoNewline
        $CanaryContent | Set-Content -LiteralPath $CanaryPath -Encoding utf8NoBOM -NoNewline
        [pscustomobject]@{auth=$auth;sidecar=$sidecar}
    }
    Assert-GuestTrustedBytes -Session $session -Bindings $guestBoundaryBindings
    $permissionEvidence = Invoke-Command -Session $session -ArgumentList $account,$desktopPassword,$guestDriver,$guestContract,$installed.runtime,$proofRepo,$installed.plugin,$authCanaryPath,$permissionEvidencePath -ScriptBlock {
        param($Account,$Password,$Driver,$Contract,$Runtime,$Repo,$Plugin,$Canary,$Output)
        $args = "-NoProfile -ExecutionPolicy Bypass -File `"$Driver`" -PermissionProbe -RuntimePath `"$Runtime`" -ProofRepoPath `"$Repo`" -SelectedPluginRoot `"$Plugin`" -AuthCanaryPath `"$Canary`" -PermissionEvidencePath `"$Output`" -ContractPath `"$Contract`""
        $action = New-ScheduledTaskAction powershell.exe -Argument $args
        Register-ScheduledTask 'CodeArbiter-PermissionProbe' -Action $action -User $Account -Password $Password -RunLevel Limited -Force | Out-Null
        try {
            Start-ScheduledTask 'CodeArbiter-PermissionProbe'
            $deadline=[DateTime]::UtcNow.AddMinutes(3)
            do{Start-Sleep -Milliseconds 500;$info=Get-ScheduledTaskInfo 'CodeArbiter-PermissionProbe'}while($info.LastTaskResult-eq 267009-and[DateTime]::UtcNow-lt$deadline)
            if($info.LastTaskResult-ne 0-or-not(Test-Path -LiteralPath $Output)){throw 'real Codex permission probe failed'}
            Get-Content -LiteralPath $Output -Raw -Encoding utf8 | ConvertFrom-Json
        } finally { Unregister-ScheduledTask 'CodeArbiter-PermissionProbe' -Confirm:$false -ErrorAction SilentlyContinue }
    }
    if ($permissionEvidence.verdict -cne 'PASS' -or $permissionEvidence.consumer -cne 'codex-sandbox-permission-profile' -or
        $permissionEvidence.hooks_enabled -ne $false -or $permissionEvidence.restricted_filesystem -ne $true -or
        $permissionEvidence.restricted_network -ne $true -or [int]$permissionEvidence.startup_warning_count -ne 0) {
        throw 'production Codex permission probe evidence is not fail-closed'
    }
    Invoke-Command -Session $session -ArgumentList $permissionPlaceholders.auth,$permissionPlaceholders.sidecar -ScriptBlock {
        param($Auth,$Sidecar)
        Remove-Item -LiteralPath $Auth,$Sidecar -Force
        if((Test-Path -LiteralPath $Auth) -or (Test-Path -LiteralPath $Sidecar)){throw 'permission placeholders were not removed before device authorization'}
    }
    $null = Invoke-BrokerStage $lifecycle 'codex-permission-profile-proven' { $true } ''

    $guestAuthRoot = Join-Path $profile '.codex'
    Assert-GuestTrustedBytes -Session $session -Bindings $guestBoundaryBindings
    $prepared = Invoke-Command -Session $session -ArgumentList $guestProbe,$guestContract,$installed.plugin,$desktopSid,$guestAuthRoot -ScriptBlock {
        param($Probe,$Contract,$Plugin,$Sid,$AuthRoot)
        & $Probe -PrepareAudit -PluginRoot $Plugin -DesktopSid $Sid -AuthRoot $AuthRoot -ContractPath $Contract
    } | ConvertFrom-Json
    if ($prepared.verdict -cne 'PASS') { throw 'guest audit preparation failed' }

    Invoke-Command -Session $session -ArgumentList $account,$desktopPassword,$installed.runtime,$guestTrustedRoot,$guestExchangeRoot -ScriptBlock {
        param($Account,$Password,$Runtime,$TrustedRoot,$ExchangeRoot)
        $script=Join-Path $TrustedRoot 'Start-DeviceAuth.ps1';$ready=Join-Path $ExchangeRoot 'device-auth-prompt-ready.json';$done=Join-Path $ExchangeRoot 'device-auth-complete.json'
        @"
`$start=[Diagnostics.ProcessStartInfo]::new();`$start.FileName='$Runtime';`$start.Arguments='login --device-auth';`$start.UseShellExecute=`$false;`$start.RedirectStandardOutput=`$true;`$start.RedirectStandardError=`$true
`$process=[Diagnostics.Process]::new();`$process.StartInfo=`$start;if(-not `$process.Start()){exit 2};`$prompt=`$false
while(-not `$process.StandardOutput.EndOfStream){`$line=`$process.StandardOutput.ReadLine();Write-Host `$line;if(-not `$prompt -and `$line -match 'https://auth\.openai\.com|device'){`$prompt=`$true;@{schema_version=1;prompt_ready=`$true;observed_at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content '$ready' -Encoding utf8NoBOM}}
`$process.WaitForExit();@{schema_version=1;prompt_ready=`$prompt;exit_code=`$process.ExitCode;completed_at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content '$done' -Encoding utf8NoBOM;exit `$process.ExitCode
"@ | Set-Content $script -Encoding utf8NoBOM
        $action=New-ScheduledTaskAction powershell.exe -Argument "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$script`""
        $trigger=New-ScheduledTaskTrigger -AtLogOn -User $Account
        $principal=New-ScheduledTaskPrincipal -UserId $Account -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask 'CodeArbiter-DeviceAuth' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
        $cleanupScript=Join-Path $TrustedRoot 'Clear-OneTimeAutologon.ps1';$cleanupMarker=Join-Path $ExchangeRoot 'autologon-secret-cleared.json'
        @"
`$key='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
'DefaultPassword','DefaultUserName','AutoAdminLogon','ForceAutoLogon','AutoLogonCount'|ForEach-Object{Remove-ItemProperty `$key `$_ -ErrorAction SilentlyContinue}
@{schema_version=1;cleared=`$true;cleared_at=[DateTime]::UtcNow.ToString('o')}|ConvertTo-Json|Set-Content -LiteralPath '$cleanupMarker' -Encoding utf8NoBOM
"@|Set-Content -LiteralPath $cleanupScript -Encoding utf8NoBOM
        $cleanupAction=New-ScheduledTaskAction powershell.exe -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$cleanupScript`""
        $cleanupTrigger=New-ScheduledTaskTrigger -AtLogOn -User $Account
        $cleanupPrincipal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
        Register-ScheduledTask 'CodeArbiter-ClearAutologon' -Action $cleanupAction -Trigger $cleanupTrigger -Principal $cleanupPrincipal -Force|Out-Null
        $key='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
        Set-ItemProperty $key AutoAdminLogon '1';Set-ItemProperty $key AutoLogonCount 1;Set-ItemProperty $key DefaultUserName $Account;Set-ItemProperty $key DefaultPassword $Password;Set-ItemProperty $key ForceAutoLogon '0'
        Restart-Computer -Force
    } -ErrorAction SilentlyContinue
    Remove-PSSession $session -ErrorAction SilentlyContinue; $session=$null
    $vmConnect = Start-Process (Join-Path $env:SystemRoot 'System32\vmconnect.exe') -ArgumentList 'localhost',$vmName -PassThru
    $session = Wait-DirectSession $vmName $bootstrap
    $autologonCleared = Invoke-Command -Session $session -ArgumentList $guestExchangeRoot -ScriptBlock {
        param($ExchangeRoot)
        $key='HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon'
        $marker=Join-Path $ExchangeRoot 'autologon-secret-cleared.json'
        $deadline=[DateTime]::UtcNow.AddSeconds(30)
        do{if(Test-Path $marker){break};Start-Sleep -Milliseconds 250}while([DateTime]::UtcNow-lt$deadline)
        $present=@('DefaultPassword','DefaultUserName','AutoAdminLogon','ForceAutoLogon','AutoLogonCount'|Where-Object{(Get-ItemProperty $key -Name $_ -ErrorAction SilentlyContinue).PSObject.Properties.Name-contains$_})
        $value=if(Test-Path $marker){Get-Content $marker -Raw|ConvertFrom-Json}else{$null}
        Unregister-ScheduledTask 'CodeArbiter-ClearAutologon' -Confirm:$false -ErrorAction SilentlyContinue
        [pscustomobject]@{marker=($null-ne$value-and$value.cleared-eq$true);remaining=@($present).Count}
    }
    if(-not$autologonCleared.marker-or$autologonCleared.remaining-ne 0){throw 'one-time autologon material was not cleared immediately after logon'}
    $null = Invoke-BrokerStage $lifecycle 'autologon-secret-cleared' { $true } ''
    $deadline=[DateTime]::UtcNow.AddSeconds([int]$contract.channel.timeout_seconds)
    do {
        $authState=Invoke-Command -Session $session -ArgumentList $guestExchangeRoot -ScriptBlock {
            param($ExchangeRoot)
            $ready=Join-Path $ExchangeRoot 'device-auth-prompt-ready.json';$done=Join-Path $ExchangeRoot 'device-auth-complete.json'
            [pscustomobject]@{ready=if(Test-Path $ready){Get-Content $ready -Raw|ConvertFrom-Json}else{$null};done=if(Test-Path $done){Get-Content $done -Raw|ConvertFrom-Json}else{$null}}
        }
        if ($null -eq $authState.done) { Start-Sleep -Seconds 2 }
    } while ($null -eq $authState.done -and [DateTime]::UtcNow -lt $deadline)
    if ($null -eq $authState.ready -or $authState.ready.prompt_ready -ne $true -or
        $null -eq $authState.done -or $authState.done.prompt_ready -ne $true -or $authState.done.exit_code -ne 0) {
        throw 'visible ChatGPT device authorization did not complete after a verified prompt-ready pause'
    }
    $null = Invoke-BrokerStage $lifecycle 'device-auth-prompt-ready' { $true } ''
    $authCompletionObserved = (
        $authState.ready.prompt_ready -eq $true -and $authState.done.prompt_ready -eq $true -and
        [int]$authState.done.exit_code -eq 0
    )
    $null = Invoke-BrokerStage $lifecycle 'device-auth-completed' {
        if(-not$authCompletionObserved){throw 'device authorization completion was not observed'}
        $true
    } ''

    Assert-GuestTrustedBytes -Session $session -Bindings $guestBoundaryBindings
    $postAuthEvidence = Invoke-Command -Session $session -ArgumentList $account,$desktopPassword,$profile,$guestDriver,$guestContract,$installed.runtime,$inventoryEvidencePath -ScriptBlock {
        param($Account,$Password,$Profile,$Driver,$Contract,$Runtime,$Output)
        $args = "-NoProfile -ExecutionPolicy Bypass -File `"$Driver`" -InventoryProbe -ProfilePath `"$Profile`" -RuntimePath `"$Runtime`" -InventoryEvidencePath `"$Output`" -ContractPath `"$Contract`""
        $action=New-ScheduledTaskAction powershell.exe -Argument $args
        Register-ScheduledTask 'CodeArbiter-PostAuthInventory' -Action $action -User $Account -Password $Password -RunLevel Limited -Force|Out-Null
        try {
            Start-ScheduledTask 'CodeArbiter-PostAuthInventory'
            $deadline=[DateTime]::UtcNow.AddMinutes(1)
            do{Start-Sleep -Milliseconds 500;$info=Get-ScheduledTaskInfo 'CodeArbiter-PostAuthInventory'}while($info.LastTaskResult-eq 267009-and[DateTime]::UtcNow-lt$deadline)
            if($info.LastTaskResult-ne 0-or-not(Test-Path -LiteralPath $Output)){throw 'production post-auth inventory failed'}
            Get-Content -LiteralPath $Output -Raw -Encoding utf8|ConvertFrom-Json
        } finally { Unregister-ScheduledTask 'CodeArbiter-PostAuthInventory' -Confirm:$false -ErrorAction SilentlyContinue }
    }
    if($postAuthEvidence.storage_backend-cne'file'-or$postAuthEvidence.keyring_target_count-ne 0-or
        $postAuthEvidence.reusable_state_file_count-ne 1-or$postAuthEvidence.doctor_overall_status-notin@('pass','ok')-or
        $postAuthEvidence.doctor_warning_or_failure_count-ne 0){throw 'post-auth storage or Codex doctor diagnostics are not fail-closed'}
    $canaryObserved = Invoke-Command -Session $session -ArgumentList $authCanaryPath,$authCanaryContent -ScriptBlock {
        param($Path,$Content)
        (Get-Content -LiteralPath $Path -Raw -Encoding utf8) -ceq $Content
    }
    if(-not$canaryObserved){throw 'auth-isolation canary changed before desktop proof'}

    Assert-GuestTrustedBytes -Session $session -Bindings $guestBoundaryBindings
    $desktopProcess = Invoke-Command -Session $session -ArgumentList $account,$desktopPassword,$installed.desktop,$proofRepo,$guestDriver,$guestContract,$installed.runtime,$observationPath,$authCanaryPath -ScriptBlock {
        param($Account,$Password,$Desktop,$Repo,$Driver,$Contract,$Runtime,$Observation,$Canary)
        Unregister-ScheduledTask 'CodeArbiter-DeviceAuth' -Confirm:$false -ErrorAction SilentlyContinue
        $launchAction=New-ScheduledTaskAction $Desktop -Argument "--open-project `"$Repo`" --force-renderer-accessibility"
        Register-ScheduledTask 'CodeArbiter-Desktop' -Action $launchAction -User $Account -Password $Password -RunLevel Limited -Force | Out-Null
        Start-ScheduledTask 'CodeArbiter-Desktop'
        $deadline=[DateTime]::UtcNow.AddMinutes(2);$process=$null
        do{Start-Sleep -Seconds 1;$process=Get-Process ChatGPT -ErrorAction SilentlyContinue|Where-Object Path -eq $Desktop|Sort-Object StartTime|Select-Object -First 1}while($null-eq $process-and[DateTime]::UtcNow-lt$deadline)
        if($null-eq$process){throw 'Store desktop process did not start'}
        $args="-NoProfile -ExecutionPolicy Bypass -File `"$Driver`" -ObservationPath `"$Observation`" -RuntimePath `"$Runtime`" -PackagedRuntimePath `"$Runtime`" -ProofRepoPath `"$Repo`" -AuthCanaryPath `"$Canary`" -DesktopProcessId $($process.Id) -ContractPath `"$Contract`""
        $action=New-ScheduledTaskAction powershell.exe -Argument $args
        Register-ScheduledTask 'CodeArbiter-DesktopDriver' -Action $action -User $Account -Password $Password -RunLevel Limited -Force|Out-Null
        Start-ScheduledTask 'CodeArbiter-DesktopDriver'
        [pscustomobject]@{id=$process.Id}
    }
    $deadline=[DateTime]::UtcNow.AddSeconds([int]$contract.channel.timeout_seconds)
    do {
        Start-Sleep -Seconds 2
        $driverState=Invoke-Command -Session $session -ArgumentList $observationPath -ScriptBlock {param($p) if(Test-Path $p){Get-Content $p -Raw}else{$null}}
    } while (-not $driverState -and [DateTime]::UtcNow -lt $deadline)
    if (-not $driverState) { throw 'desktop driver observation timed out' }
    $driverObservation = $driverState | ConvertFrom-Json
    if ($driverObservation.test_result -cne 'SUCCEEDED') { throw 'desktop driver did not observe the approved route dispatch' }
    if ($driverObservation.runtime_version -cne $request.desktop_runtime_version) { throw 'measured desktop runtime version does not match the requested build contract' }
    $frozenObservationSha = Invoke-Command -Session $session -ArgumentList $observationPath,$frozenObservationPath -ScriptBlock {
        param($Source,$Frozen)
        Copy-Item -LiteralPath $Source -Destination $Frozen -Force
        & icacls.exe $Frozen /inheritance:r /grant:r '*S-1-5-18:(F)' '*S-1-5-32-544:(F)' | Out-Null
        if($LASTEXITCODE){throw 'could not freeze the privileged driver observation'}
        (Get-FileHash -Algorithm SHA256 -LiteralPath $Frozen).Hash.ToLowerInvariant()
    }
    Assert-GuestTrustedBytes -Session $session -Bindings $guestBoundaryBindings
    Assert-GuestTrustedBytes -Session $session -Bindings @{$frozenObservationPath=$frozenObservationSha}

    $bootstrapSid = Invoke-Command -Session $session -ScriptBlock { [Security.Principal.WindowsIdentity]::GetCurrent().User.Value }
    $routeJson = Invoke-Command -Session $session -ArgumentList $guestProbe,$guestContract,$installed.plugin,$desktopSid,$guestAuthRoot,[long]$prepared.start_record_id,$frozenObservationPath,$challengeKey,$challengeNonce,$vmId,$bootstrapSid -ScriptBlock {
        param($Probe,$Contract,$Plugin,$Sid,$AuthRoot,$Start,$Observation,$Key,$Nonce,$Vm,$Bootstrap)
        & $Probe -CollectAudit -PluginRoot $Plugin -DesktopSid $Sid -AuthRoot $AuthRoot -StartRecordId $Start -DriverObservationPath $Observation -ChallengeKey $Key -ChallengeNonce $Nonce -VmId $Vm -BootstrapSid $Bootstrap -ContractPath $Contract
    }
    $routeResponseBytes = [Text.Encoding]::UTF8.GetByteCount([string]$routeJson)
    if ($routeResponseBytes -gt [int]$contract.channel.max_message_bytes) {
        throw 'PowerShell Direct evidence response exceeded the byte bound'
    }
    $route = $routeJson | ConvertFrom-Json
    if ($route.test_result -cne 'SUCCEEDED' -or $route.teardown_requested -ne $true) {
        throw 'observable desktop route corpus is incomplete'
    }
    if ((Get-RouteResponseBinding $route) -cne [string]$route.response_binding_sha256) {
        throw 'observable desktop route response binding is invalid'
    }
    Assert-ChannelResponse ([pscustomobject]@{
        key=$challengeKey;nonce=$challengeNonce;vm_id=$vmId;bootstrap_sid=$bootstrapSid
        desktop_sid=$desktopSid;request_sha256=$route.request_sha256
        dispatch_sha256=$route.dispatch_sha256;causal_window_sha256=$route.causal_window_sha256
        auth_canary_content_sha256=$route.auth_canary_content_sha256
        permission_profile_id=$route.permission_profile_id;auth_canary_denied=$route.auth_canary_denied
        response_binding_sha256=$route.response_binding_sha256
        record_ids=@($route.record_ids)
        response_sha256=$route.challenge_response_sha256
    })
    $null = Invoke-BrokerStage $lifecycle 'desktop-route-observed' { $true } ''

    $networkEvidence = Invoke-Command -Session $session -ArgumentList $contract.network,$setup.resolved_endpoints,$installed.desktop,$installed.runtime -ScriptBlock {
        param($Network,$ResolvedEndpoints,$DesktopPath,$RuntimePath)
        $group='CodeArbiter Desktop Proof'
        $outside=@(Get-NetFirewallRule -Direction Outbound -Action Allow -Enabled True|Where-Object DisplayGroup -ne $group)
        $inside=@(Get-NetFirewallRule -DisplayGroup $group -Direction Outbound -Action Allow -Enabled True)
        $expected=@($ResolvedEndpoints).Count*2
        if($outside.Count-or$inside.Count-ne$expected-or@(Get-NetFirewallProfile|Where-Object DefaultOutboundAction-ne Block).Count){throw 'effective guest egress policy is not the exact reviewed allowlist'}
        $records=@()
        foreach($rule in $inside){
            $port=$rule|Get-NetFirewallPortFilter;$app=$rule|Get-NetFirewallApplicationFilter
            $address=$rule|Get-NetFirewallAddressFilter
            $protocol=[string]$port.Protocol;$remotePort=[string]$port.RemotePort;$program=[IO.Path]::GetFullPath([string]$app.Program)
            if($rule.DisplayName-notmatch '^CA Desktop (CLI|App) HTTPS ([0-9]+)$'){throw 'unexpected outbound allow rule exists inside the proof group'}
            $role=$Matches[1];$index=[int]$Matches[2]
            if($index-lt 0-or$index-ge@($ResolvedEndpoints).Count){throw 'HTTPS firewall endpoint index is invalid'}
            $endpoint=$ResolvedEndpoints[$index];$expectedProgram=if($role-ceq'CLI'){$RuntimePath}else{$DesktopPath}
            $remote=@($address.RemoteAddress|Sort-Object);$expectedRemote=@($endpoint.addresses|Sort-Object)
            if($protocol-notin@('TCP','6')-or$remotePort-cne[string]$Network.https_port-or$program-cne[IO.Path]::GetFullPath($expectedProgram)-or($remote-join'|')-cne($expectedRemote-join'|')){throw 'HTTPS firewall filter differs from the reviewed contract'}
            $records+="https|$role|$($endpoint.fqdn)|$remotePort|$program|$($remote-join ',')"
        }
        $hosts=Get-Content -LiteralPath "$env:SystemRoot\System32\drivers\etc\hosts" -Encoding ascii
        foreach($endpoint in $ResolvedEndpoints){foreach($ip in @($endpoint.addresses)){if($hosts-notcontains"$ip`t$($endpoint.fqdn)"){throw 'pinned hosts mapping is missing'}}}
        $canonical='codearbiter.desktop-network.v2|'+(@($records|Sort-Object)-join '|')
        $sha=[Security.Cryptography.SHA256]::Create();try{$digest=-join@($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($canonical))|ForEach-Object{$_.ToString('x2')})}finally{$sha.Dispose()}
        [pscustomobject]@{policy_sha256=$digest;enabled_allow_rules=$inside.Count;outside_allow_rules=$outside.Count}
    }
    $null = Invoke-BrokerStage $lifecycle 'network-policy-measured' { $true } ''

    $receiptDirectory = Split-Path -Parent ([IO.Path]::GetFullPath($ReceiptPath))
    $receiptLeaf = Split-Path -Leaf $ReceiptPath
    $torn = Invoke-BrokerCleanupStage $lifecycle 'account-disabled' {
        $teardownResult = Invoke-Command -Session $session -ArgumentList $account,$desktopSid -ScriptBlock {
            param($Account,$Sid)
            Disable-LocalUser $Account;$disabled=-not(Get-LocalUser $Account).Enabled
            'CodeArbiter-DesktopDriver','CodeArbiter-Desktop','CodeArbiter-DeviceAuth','CodeArbiter-ClearAutologon'|ForEach-Object{Unregister-ScheduledTask $_ -Confirm:$false -ErrorAction SilentlyContinue}
            $line=quser.exe $Account 2>$null|Select-Object -Skip 1|Select-Object -First 1
            if($line){$id=@(($line-replace '^\s*>','').Trim()-split '\s+'|Where-Object{$_-match '^\d+$'})|Select-Object -First 1;if($id){logoff.exe $id;Start-Sleep -Seconds 2}}
            Remove-LocalUser $Account;$deleted=$null-eq(Get-LocalUser $Account -ErrorAction SilentlyContinue)
            $p=Get-CimInstance Win32_UserProfile|Where-Object SID -eq $Sid;if($p){Remove-CimInstance $p}
            [pscustomobject]@{disabled=$disabled;deleted=$deleted;profile_destroyed=$null-eq(Get-CimInstance Win32_UserProfile|Where-Object SID -eq $Sid)}
        }
        if(-not$teardownResult.disabled){throw 'disposable desktop account was not disabled'}
        $teardownResult
    } ''
    $null = Invoke-BrokerCleanupStage $lifecycle 'account-deleted' {
        if($null-eq$torn-or-not$torn.deleted){throw 'disposable desktop account was not deleted'};$true
    } ''
    $null = Invoke-BrokerCleanupStage $lifecycle 'profile-destroyed' {
        if($null-eq$torn-or-not$torn.profile_destroyed){throw 'disposable desktop profile was not destroyed'};$true
    } ''
    $vmDestroyed = Invoke-BrokerCleanupStage $lifecycle 'vm-destroyed' {
        Invoke-BoundedCleanupOperation $lifecycle 'vm-destroyed' {
            if($session){Remove-PSSession $session -ErrorAction SilentlyContinue};$script:session=$null
            if($vmConnect-and-not$vmConnect.HasExited){Stop-Process $vmConnect.Id -Force -ErrorAction SilentlyContinue}
            if(Get-VM $vmName -ErrorAction SilentlyContinue){
                Stop-VM $vmName -TurnOff -Force -ErrorAction SilentlyContinue
                Remove-VM $vmName -Force -ErrorAction Stop
            }
        } { $null-eq(Get-VM $vmName -ErrorAction SilentlyContinue) } 3 500
    } ''
    $runRootDestroyed = Invoke-BrokerCleanupStage $lifecycle 'run-root-destroyed' {
        Invoke-BoundedCleanupOperation $lifecycle 'run-root-destroyed' {
            if(Test-Path -LiteralPath $runRoot){Remove-Item -LiteralPath $runRoot -Recurse -Force -ErrorAction Stop}
        } { -not(Test-Path -LiteralPath $runRoot) } 3 500
    } ''
    $artifactSidecars = @(Get-ChildItem -LiteralPath $receiptDirectory -File -ErrorAction Stop |
        Where-Object { $_.Name.StartsWith($receiptLeaf,[StringComparison]::OrdinalIgnoreCase) }).Count
    $null = Invoke-BrokerCleanupStage $lifecycle 'artifact-inventory-cleared' {
        if($artifactSidecars-ne 0){throw 'durable receipt sidecars exist before finalization'};$true
    } ''
    $finalCleanupObservations = [ordered]@{
        'account-disabled' = [bool]($torn -and $torn.disabled)
        'account-deleted' = [bool]($torn -and $torn.deleted)
        'profile-destroyed' = [bool]($torn -and $torn.profile_destroyed)
        'vm-destroyed' = $null-eq(Get-VM $vmName -ErrorAction SilentlyContinue)
        'vhdx-destroyed' = -not(Test-Path -LiteralPath $diskPath)
        'run-root-destroyed' = -not(Test-Path -LiteralPath $runRoot)
        'receipt-absent' = -not(Test-Path -LiteralPath $ReceiptPath)
    }
    $null = Assert-BrokerCleanupObservations $lifecycle $finalCleanupObservations
    Complete-BrokerLifecycle $lifecycle
    $measurements = [pscustomobject]@{
        fresh_iso_applied = [bool]$diskEvidence.fresh_iso_applied
        enhanced_session_enabled = [bool]$hostIsolation.enhanced_session_enabled
        guest_service_interface_enabled = [bool]$hostIsolation.guest_service_interface_enabled
        host_profile_mounted = [bool]$hostIsolation.host_profile_mounted
        host_shared_folders = [bool]$hostIsolation.host_shared_folders
        network_policy_sha256 = [string]$networkEvidence.policy_sha256
        enabled_allow_rules = [int]$networkEvidence.enabled_allow_rules
        outside_allow_rules = [int]$networkEvidence.outside_allow_rules
        preauth_api_key_variables = [int]$preAuthEvidence.api_key_variables
        preauth_credential_targets = [int]$preAuthEvidence.credential_targets
        preauth_network_mappings = [int]$preAuthEvidence.network_mappings
        preauth_auth_files = [int]$preAuthEvidence.preexisting_auth_files
        auth_storage_mode = [string]$postAuthEvidence.storage_backend
        postauth_credential_targets = [int]$postAuthEvidence.keyring_target_count
        postauth_auth_files = [int]$postAuthEvidence.reusable_state_file_count
        auth_prompt_ready = [bool]$authState.ready.prompt_ready
        auth_completed = [bool]$authCompletionObserved
        app_account_mode = [string]$driverObservation.auth_mode
        permission_profile_id = [string]$driverObservation.permission_profile_id
        permission_consumer = [string]$permissionEvidence.consumer
        permission_restricted_filesystem = [bool]$permissionEvidence.restricted_filesystem
        permission_restricted_network = [bool]$permissionEvidence.restricted_network
        permission_hooks_enabled = [bool]$permissionEvidence.hooks_enabled
        permission_startup_warning_count = [int]$permissionEvidence.startup_warning_count
        permission_windows_sandbox = [string]$driverObservation.windows_sandbox
        guest_acl_boundary = [bool]($setup.acl_evidence.trusted -and $setup.acl_evidence.run -and $setup.acl_evidence.exchange)
        auth_canary_denied = [bool]$driverObservation.auth_canary_denied
        auth_canary_content_observed = [bool]$driverObservation.auth_canary_content_observed
        eligible_runtime_process_count = [int]$driverObservation.eligible_runtime_process_count
        raw_content_persisted = [bool]$driverObservation.raw_content_persisted
        artifact_sidecars = [int]$artifactSidecars
    }
    Assert-MeasuredProof $measurements (2 * @($contract.network.https_fqdns).Count)

    $routeHash=Get-TextSha256 ('codearbiter.desktop-route-set.v2|' + (@($route.route_events|ForEach-Object event_sha256)-join '|'))
    $teardownHash=Get-TextSha256 "codearbiter.desktop-teardown.v2|$desktopSha|$($torn.disabled)|$($torn.deleted)|$($torn.profile_destroyed)|vm-destroyed|run-root-destroyed"
    $receiptContract = New-ReceiptPolicyAndChannel ([pscustomobject]@{
        schema_version = 1
        policy = [pscustomobject]@{
            requested_approval = $request.requested_approval
            effective_approval = $driverObservation.effective_approval
            requested_sandbox = $request.requested_sandbox
            effective_sandbox = $driverObservation.effective_sandbox
            permission_consumer = $measurements.permission_consumer
            restricted_filesystem = $measurements.permission_restricted_filesystem
            restricted_network = $measurements.permission_restricted_network
            hooks_enabled = $measurements.permission_hooks_enabled
            startup_warning_count = $measurements.permission_startup_warning_count
            windows_sandbox = $measurements.permission_windows_sandbox
            guest_acl_boundary = $measurements.guest_acl_boundary
        }
        channel = [pscustomobject]@{
            challenge_nonce = $challengeNonce
            challenge_response_sha256 = $route.challenge_response_sha256
            observed_queries = $driverObservation.app_server_query_count
            observed_messages = $route.observed_messages
            response_utf8_bytes = $routeResponseBytes
            sequence_complete = $route.sequence_complete
            timed_out = $route.timed_out
        }
    }) $contract
    $receipt=[ordered]@{
        schema_version=3;surface='desktop';verdict='PASS';blockers=@()
        candidate=[ordered]@{archive_sha256=$candidateHash;source_commit=$request.candidate_commit;source_tree=$request.candidate_tree;package='ca-codex';package_version=$candidate.Version;resource_manifest_sha256=$candidate.ResourceSha256}
        desktop=[ordered]@{distribution='store-msix';package_identity=$driverObservation.package_full_name;publisher=$driverObservation.package_publisher;build=$request.desktop_build;runtime_version=$driverObservation.runtime_version;desktop_executable_sha256=$driverObservation.desktop_process_sha256;runtime_executable_sha256=$driverObservation.runtime_process_sha256}
        boundary=[ordered]@{contract_sha256=Get-Sha256 $ContractPath;broker_sha256=$contract.broker.sha256;driver_sha256=$contract.driver.sha256;probe_sha256=$contract.probe.sha256;image_id=$contract.image.id;image_sha256=$contract.image.sha256;provisioning_mode=$contract.image.provisioning_mode;receipt_finalizer='outer-broker';receipt_phase='post-teardown'}
        identities=[ordered]@{broker=[ordered]@{kind='github-runner';identity_sha256=$brokerSha};bootstrap=[ordered]@{kind='ephemeral-guest-bootstrap';identity_sha256=Get-TextSha256 $bootstrapSid};desktop=[ordered]@{kind='disposable-windows-account';identity_sha256=$desktopSha;account_name=$account;profile_root=$profile}}
        lifecycle=[ordered]@{probe_teardown_requested=$route.teardown_requested;account_disabled=$torn.disabled;account_deleted=$torn.deleted;profile_destroyed=$torn.profile_destroyed;vm_destroyed=$vmDestroyed;run_root_destroyed=$runRootDestroyed;finalized_after_teardown=($vmDestroyed-and$runRootDestroyed-and$torn.profile_destroyed)}
        isolation=[ordered]@{hypervisor='hyper-v';fresh_iso_applied=$measurements.fresh_iso_applied;enhanced_session_enabled=$measurements.enhanced_session_enabled;guest_service_interface_enabled=$measurements.guest_service_interface_enabled;host_profile_mounted=$measurements.host_profile_mounted;host_shared_folders=$measurements.host_shared_folders;network_policy_sha256=$measurements.network_policy_sha256;enabled_allow_rules=$measurements.enabled_allow_rules;outside_allow_rules=$measurements.outside_allow_rules}
        authentication=[ordered]@{mode='chatgpt-device';prompt_ready_observed=$measurements.auth_prompt_ready;consent_completion_observed=$measurements.auth_completed;app_account_mode=$measurements.app_account_mode;permission_profile_id=$measurements.permission_profile_id;storage_backend=$measurements.auth_storage_mode;keyring_target_count=$measurements.postauth_credential_targets;reusable_state_file_count=$measurements.postauth_auth_files;denial_canary_observed=$measurements.auth_canary_denied;canary_content_observed=$measurements.auth_canary_content_observed;eligible_runtime_process_count=$measurements.eligible_runtime_process_count;autologon_material_cleared=$autologonCleared.marker;api_key_auth_detected=([int]$measurements.preauth_api_key_variables-ne 0);copied_session_source_detected=([int]$measurements.preauth_auth_files-ne 0-or[int]$measurements.preauth_credential_targets-ne 0)}
        policy=$receiptContract.policy
        resources=[ordered]@{marketplace=$contract.marketplace.name;plugin=$contract.marketplace.plugin;version=$candidate.Version;plugin_root=$route.selected_plugin_root;package_sha256=$candidateHash;selection_source='audited-desktop-skill-read';route_corpus_id=$contract.route_corpus.id;request_sha256=$route.request_sha256;thread_id_sha256=$route.thread_id_sha256;dispatch_agent=$route.dispatch_agent;route_events=@($route.route_events);cache_glob_used=$false;path_escape_detected=$false;unresolved_routes=@()}
        channel=$receiptContract.channel
        workflow=[ordered]@{repository='arbiterForge/codeArbiter';path='.github/workflows/codex-desktop-candidate.yml';commit=$request.workflow_commit;run_id=$request.run_id;protected_environment=$request.protected_environment}
        events=[ordered]@{route_events_sha256=$routeHash;security_records_sha256=$route.security_records_sha256;causal_window_sha256=$route.causal_window_sha256;teardown_events_sha256=$teardownHash}
        evidence=[ordered]@{raw_content_persisted=$measurements.raw_content_persisted;auth_profile_destroyed=$torn.profile_destroyed;vm_destroyed=$vmDestroyed;run_root_destroyed=$runRootDestroyed;durable_artifact_inventory=if($measurements.artifact_sidecars-eq 0){'receipt-only'}else{'unexpected-sidecar'}}
    }
    $serialized=$receipt|ConvertTo-Json -Depth 12
    if($serialized-match '(?i)(sk-[A-Za-z0-9_-]{8,}|Bearer\s+\S+|device[_ -]?code|access[_ -]?token|refresh[_ -]?token)'){throw 'receipt contains prohibited credential-shaped material'}
    $null = Write-BrokerReceiptArtifact $ReceiptPath $serialized
} catch {
    $failure = $_
    $lifecycle.Failed = $true
    $catchTorn = $null
    while($lifecycle.CleanupIndex -lt $script:BrokerCleanupStages.Count){
        $cleanupName = $script:BrokerCleanupStages[$lifecycle.CleanupIndex]
        switch($cleanupName){
            'account-disabled' {
                $null = Invoke-BrokerCleanupStage $lifecycle $cleanupName {
                    if($lifecycle.Trace -notcontains 'identity-created'){
                        $catchTorn=[pscustomobject]@{disabled=$true;deleted=$true;profile_destroyed=$true}
                    } elseif($session -and $setup){
                        $catchTorn=Invoke-Command -Session $session -ArgumentList $account,[string]$setup.sid -ScriptBlock {
                            param($Account,$Sid)
                            $user=Get-LocalUser $Account -ErrorAction SilentlyContinue
                            if($user){Disable-LocalUser $Account}
                            $disabled=$null-eq(Get-LocalUser $Account -ErrorAction SilentlyContinue)-or-not(Get-LocalUser $Account).Enabled
                            'CodeArbiter-DesktopDriver','CodeArbiter-Desktop','CodeArbiter-DeviceAuth','CodeArbiter-ClearAutologon'|ForEach-Object{Unregister-ScheduledTask $_ -Confirm:$false -ErrorAction SilentlyContinue}
                            Remove-LocalUser $Account -ErrorAction SilentlyContinue
                            $deleted=$null-eq(Get-LocalUser $Account -ErrorAction SilentlyContinue)
                            $p=Get-CimInstance Win32_UserProfile|Where-Object SID -eq $Sid;if($p){Remove-CimInstance $p}
                            [pscustomobject]@{disabled=$disabled;deleted=$deleted;profile_destroyed=$null-eq(Get-CimInstance Win32_UserProfile|Where-Object SID -eq $Sid)}
                        }
                    } else { throw 'guest identity cleanup could not obtain its production session' }
                    if(-not$catchTorn.disabled){throw 'failed-run account disable was not observed'}
                    $true
                } ''
            }
            'account-deleted' {
                $null = Invoke-BrokerCleanupStage $lifecycle $cleanupName {
                    if($null-eq$catchTorn-or-not$catchTorn.deleted){throw 'failed-run account deletion was not observed'};$true
                } ''
            }
            'profile-destroyed' {
                $null = Invoke-BrokerCleanupStage $lifecycle $cleanupName {
                    if($null-eq$catchTorn-or-not$catchTorn.profile_destroyed){throw 'failed-run profile destruction was not observed'};$true
                } ''
            }
            'vm-destroyed' {
                $null = Invoke-BrokerCleanupStage $lifecycle $cleanupName {
                    Invoke-BoundedCleanupOperation $lifecycle 'vm-destroyed' {
                        if($session){Remove-PSSession $session -ErrorAction SilentlyContinue};$script:session=$null
                        if($vmConnect-and-not$vmConnect.HasExited){Stop-Process $vmConnect.Id -Force -ErrorAction SilentlyContinue}
                        if(Get-VM $vmName -ErrorAction SilentlyContinue){
                            Stop-VM $vmName -TurnOff -Force -ErrorAction SilentlyContinue
                            Remove-VM $vmName -Force -ErrorAction Stop
                        }
                    } { $null-eq(Get-VM $vmName -ErrorAction SilentlyContinue) } 3 500
                } ''
            }
            'run-root-destroyed' {
                $null = Invoke-BrokerCleanupStage $lifecycle $cleanupName {
                    Invoke-BoundedCleanupOperation $lifecycle 'run-root-destroyed' {
                        if(Test-Path -LiteralPath $runRoot){Remove-Item -LiteralPath $runRoot -Recurse -Force -ErrorAction Stop}
                    } { -not(Test-Path -LiteralPath $runRoot) } 3 500
                } ''
            }
            'artifact-inventory-cleared' {
                $null = Invoke-BrokerCleanupStage $lifecycle $cleanupName {
                    if($ReceiptPath-and(Test-Path $ReceiptPath)){Remove-Item $ReceiptPath -Force}
                    if($ReceiptPath-and(Test-Path $ReceiptPath)){throw 'failed-run receipt cleanup was not observed'};$true
                } ''
            }
        }
    }
    Invoke-BrokerFailureFinalization $lifecycle $failure $ReceiptPath {
        if($catchTorn){
            $identityObservation = $catchTorn
        } elseif($torn){
            $identityObservation = $torn
        } elseif($lifecycle.Trace -notcontains 'identity-created'){
            $identityObservation = [pscustomobject]@{disabled=$true;deleted=$true;profile_destroyed=$true}
        } else {
            $identityObservation = [pscustomobject]@{disabled=$false;deleted=$false;profile_destroyed=$false}
        }
        [ordered]@{
            'account-disabled' = [bool]$identityObservation.disabled
            'account-deleted' = [bool]$identityObservation.deleted
            'profile-destroyed' = [bool]$identityObservation.profile_destroyed
            'vm-destroyed' = $null-eq(Get-VM $vmName -ErrorAction SilentlyContinue)
            'vhdx-destroyed' = -not(Test-Path -LiteralPath $diskPath)
            'run-root-destroyed' = -not(Test-Path -LiteralPath $runRoot)
            'receipt-absent' = -not(Test-Path -LiteralPath $ReceiptPath)
        }
    }
} finally {
    $desktopPassword=$null;$bootstrapPassword=$null;$bootstrapSecure=$null;$bootstrap=$null
    $challengeKey=$null;$challengeNonce=$null
}
