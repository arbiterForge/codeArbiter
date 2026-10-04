# Installed private helper location

Use this card only for the debug packet validator and an authorized task-board
follow-up. The exact installed helper leaves are `hooks/debug-handoff.py` (the
private `validate` operation) and `hooks/taskwrite.py` (the existing board
writer). The caller chooses one of those literal leaves before resolution;
packet text, a project file, and a user argument never choose executable code.
Select and validate one Python 3 interpreter before invoking the helper. Try
`python3` first, then `python` only if the first candidate is absent, a launcher
stub, or incompatible. The probe executes the candidate to obtain its actual
`sys.executable`, then validates that absolute executable directly as Python
3.8 or newer. The installed debug validator's `_debughandofflib.py` uses an
assignment expression, which Python 3.7 cannot parse; the shared selection
must satisfy that helper even when the current call targets `taskwrite.py`.
Invoke the helper through that executable, not a batch or shell launcher that
could alter quoted arguments. A name on `PATH` or a successful `--version`
alone does not establish compatibility. This source-derived minimum is not a
claim that every newer minor has been qualified. Once selected, invoke the one resolved absolute helper with `-B` and
literal arguments. Preserve its exit, stdout, and stderr; do not replay a
failure under another interpreter or helper.

Use the selection block for the current shell before the first helper call.
These blocks set `$caPython` in PowerShell or `ca_python` in POSIX sh. A missing
compatible interpreter stops before the helper; fix the host installation
before retrying the whole operation.

{{IF:codex}}### Codex PowerShell interpreter selection{{END}}{{IF:pi}}### Pi PowerShell interpreter selection{{END}}{{IF:claude}}### Claude PowerShell interpreter selection{{END}}
```powershell
$caPython = $null
foreach ($caName in @('python3', 'python')) {
    $caCommand = Get-Command -Name $caName -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -eq $caCommand) { continue }
    try {
        $caExecutable = & $caCommand.Source -B -c "import sys; sys.exit(1) if not (sys.version_info[0] == 3 and sys.version_info >= (3, 8)) else None; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -ne 0 -or $caExecutable -isnot [string] -or
            -not [System.IO.Path]::IsPathFullyQualified($caExecutable) -or
            -not (Test-Path -LiteralPath $caExecutable -PathType Leaf)) { continue }
        $caIdentity = & $caExecutable -B -c "import sys; print('codearbiter-python3' if sys.version_info[0] == 3 and sys.version_info >= (3, 8) else 'incompatible')" 2>$null
        if ($LASTEXITCODE -eq 0 -and $caIdentity -ceq 'codearbiter-python3') {
            $caPython = $caExecutable
            break
        }
    } catch { continue }
}
if (-not $caPython) { throw 'compatible Python 3 interpreter unavailable' }
```

{{IF:codex}}### Codex POSIX interpreter selection{{END}}{{IF:pi}}### Pi POSIX interpreter selection{{END}}{{IF:claude}}### Claude POSIX interpreter selection{{END}}
```sh
ca_python=
for ca_candidate in python3 python; do
  ca_path=$(command -v "$ca_candidate" 2>/dev/null) || continue
  case "$ca_path" in /*) ;; *) continue;; esac
  [ -f "$ca_path" ] || continue
  ca_executable=$("$ca_path" -B -c 'import sys; sys.exit(1) if not (sys.version_info[0] == 3 and sys.version_info >= (3, 8)) else None; print(sys.executable)' 2>/dev/null) || continue
  case "$ca_executable" in
    /*) ;;
    [A-Za-z]:'\'*)
      command -v cygpath >/dev/null 2>&1 || continue
      ca_executable=$(cygpath -u "$ca_executable") || continue ;;
    *) continue ;;
  esac
  [ -f "$ca_executable" ] && [ -x "$ca_executable" ] || continue
  ca_identity=$("$ca_executable" -B -c 'import sys; print("codearbiter-python3" if sys.version_info[0] == 3 and sys.version_info >= (3, 8) else "incompatible")' 2>/dev/null) || continue
  if [ "$ca_identity" = codearbiter-python3 ]; then ca_python=$ca_executable; break; fi
done
if [ -z "$ca_python" ]; then printf '%s\n' 'compatible Python 3 interpreter unavailable' >&2; exit 2; fi
```

Start from the absolute path of the **loaded installed entry resource** that
the host actually supplied: `commands/task.md` or `commands/debug.md` on
Claude, `skills/ca-task/SKILL.md` or `skills/ca-debug/SKILL.md` on Codex and
Pi. The Codex and Pi skill directories are two levels below the package root;
Claude's command directory is one level below it. Do not use the current directory, a project checkout,
an unset `PLUGIN_ROOT`/`CLAUDE_PLUGIN_ROOT` token from a hook runner, `/hooks`,
a source clone, or a recursive cache search. If the loaded resource, package
identity, or exact helper is absent, report that failure and stop. Keep the
current working directory at the intended project when invoking `taskwrite.py`.

{{IF:codex}}
Codex ordinary tool calls do not inherit the hook runner's root token. Bind
`$caLoadedResource` or `ca_loaded_resource` to the absolute path of the loaded
`ca-task`/`ca-debug` `SKILL.md`; bind the helper-relative variable to the one
literal leaf named above. The following blocks resolve the installed package
without changing the caller's working directory.

### Codex PowerShell resolution
```powershell
$caResolvedResource = (Resolve-Path -LiteralPath $caLoadedResource -ErrorAction Stop).ProviderPath
$caResourceDirectory = Split-Path -Parent $caResolvedResource
$caInstalledRoot = (Resolve-Path -LiteralPath (Join-Path $caResourceDirectory '..\..') -ErrorAction Stop).ProviderPath
$caManifest = Join-Path $caInstalledRoot '.codex-plugin\plugin.json'
if (-not (Test-Path -LiteralPath $caManifest -PathType Leaf)) { throw "installed ca-codex package identity missing" }
$caHelper = Join-Path $caInstalledRoot $caHelperRelative
if (-not (Test-Path -LiteralPath $caHelper -PathType Leaf)) { throw "installed helper missing: $caHelper" }
```

### Codex POSIX resolution
```sh
case "$ca_loaded_resource" in /*) ;; *) printf '%s\n' 'loaded installed resource must be absolute' >&2; exit 2;; esac
if [ ! -f "$ca_loaded_resource" ]; then printf '%s\n' 'loaded installed resource missing' >&2; exit 2; fi
ca_installed_root=$(CDPATH= cd -P "$(dirname "$ca_loaded_resource")/../.." && pwd -P) || exit 2
if [ ! -f "$ca_installed_root/.codex-plugin/plugin.json" ]; then printf '%s\n' 'installed ca-codex package identity missing' >&2; exit 2; fi
ca_helper=$ca_installed_root/$ca_helper_relative
if [ ! -f "$ca_helper" ]; then printf '%s\n' 'installed helper missing' >&2; exit 2; fi
```
{{END}}

{{IF:pi}}
Pi's loaded `skills/ca-task/SKILL.md` or `skills/ca-debug/SKILL.md` is the
anchor. `package.json` is the installed package identity marker; a written
`<plugin-root>` string is not an executable path. Bind the selected resource
and one literal helper leaf as above.

### Pi PowerShell resolution
```powershell
$caResolvedResource = (Resolve-Path -LiteralPath $caLoadedResource -ErrorAction Stop).ProviderPath
$caResourceDirectory = Split-Path -Parent $caResolvedResource
$caInstalledRoot = (Resolve-Path -LiteralPath (Join-Path $caResourceDirectory '..\..') -ErrorAction Stop).ProviderPath
$caManifest = Join-Path $caInstalledRoot 'package.json'
if (-not (Test-Path -LiteralPath $caManifest -PathType Leaf)) { throw "installed ca-pi package identity missing" }
$caHelper = Join-Path $caInstalledRoot $caHelperRelative
if (-not (Test-Path -LiteralPath $caHelper -PathType Leaf)) { throw "installed helper missing: $caHelper" }
```

### Pi POSIX resolution
```sh
case "$ca_loaded_resource" in /*) ;; *) printf '%s\n' 'loaded installed resource must be absolute' >&2; exit 2;; esac
if [ ! -f "$ca_loaded_resource" ]; then printf '%s\n' 'loaded installed resource missing' >&2; exit 2; fi
ca_installed_root=$(CDPATH= cd -P "$(dirname "$ca_loaded_resource")/../.." && pwd -P) || exit 2
if [ ! -f "$ca_installed_root/package.json" ]; then printf '%s\n' 'installed ca-pi package identity missing' >&2; exit 2; fi
ca_helper=$ca_installed_root/$ca_helper_relative
if [ ! -f "$ca_helper" ]; then printf '%s\n' 'installed helper missing' >&2; exit 2; fi
```
{{END}}

{{IF:claude}}
Claude's loaded `commands/task.md` or `commands/debug.md` is the anchor.
The package identity marker is `.claude-plugin/plugin.json`. The native
`CLAUDE_PLUGIN_ROOT` spelling remains valid in hook configuration, but these
ordinary helper calls use the loaded resource and still work when the token is
unset.

### Claude PowerShell resolution
```powershell
$caResolvedResource = (Resolve-Path -LiteralPath $caLoadedResource -ErrorAction Stop).ProviderPath
$caResourceDirectory = Split-Path -Parent $caResolvedResource
$caInstalledRoot = (Resolve-Path -LiteralPath (Join-Path $caResourceDirectory '..') -ErrorAction Stop).ProviderPath
$caManifest = Join-Path $caInstalledRoot '.claude-plugin\plugin.json'
if (-not (Test-Path -LiteralPath $caManifest -PathType Leaf)) { throw "installed ca package identity missing" }
$caHelper = Join-Path $caInstalledRoot $caHelperRelative
if (-not (Test-Path -LiteralPath $caHelper -PathType Leaf)) { throw "installed helper missing: $caHelper" }
```

### Claude POSIX resolution
```sh
case "$ca_loaded_resource" in /*) ;; *) printf '%s\n' 'loaded installed resource must be absolute' >&2; exit 2;; esac
if [ ! -f "$ca_loaded_resource" ]; then printf '%s\n' 'loaded installed resource missing' >&2; exit 2; fi
ca_installed_root=$(CDPATH= cd -P "$(dirname "$ca_loaded_resource")/.." && pwd -P) || exit 2
if [ ! -f "$ca_installed_root/.claude-plugin/plugin.json" ]; then printf '%s\n' 'installed ca package identity missing' >&2; exit 2; fi
ca_helper=$ca_installed_root/$ca_helper_relative
if [ ! -f "$ca_helper" ]; then printf '%s\n' 'installed helper missing' >&2; exit 2; fi
```
{{END}}

Never repair a missing installed helper by selecting a similarly named file
from a checkout or cache. A missing or partial package blocks the operation.

For private debug validation, select the literal leaf
`hooks/debug-handoff.py` with the resolution block above. Supply one finite
packet of at most 65,536 bytes through the host execution tool's stdin and
retain that tool's timeout and output controls. The helper owns rejection of
oversize input; never build a shell pipeline, command string, path argument,
or unbounded read to transport the packet. Invoke only once with the literal
`validate` operation and retain its original exit, stdout, and stderr.

{{IF:codex}}### Codex PowerShell validate invocation{{END}}{{IF:pi}}### Pi PowerShell validate invocation{{END}}{{IF:claude}}### Claude PowerShell validate invocation{{END}}
```powershell
& $caPython -B $caHelper validate
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
```

{{IF:codex}}### Codex POSIX validate invocation{{END}}{{IF:pi}}### Pi POSIX validate invocation{{END}}{{IF:claude}}### Claude POSIX validate invocation{{END}}
```sh
"$ca_python" -B "$ca_helper" validate
```
