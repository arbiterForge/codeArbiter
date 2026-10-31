"""Explicit GitHub issue effects for portable native work.

The native record owns the pre-send claim and remote binding. This module owns
one fixed HTTPS transport; no repository file contains a token or executable
provider template. An uncertain create is never posted a second time.
"""

from __future__ import annotations

import json
import base64
import binascii
import os
from pathlib import Path
import re
import secrets
import subprocess
from urllib import error, parse, request

from _gitexec import git_executable, root_bound_git_env


_REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\Z")
_BASE = "https://api.github.com"
_MARKER = "<!-- codearbiter-work: {} -->"


class WorkSyncError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GithubTransport:
    """Bounded official GitHub API transport; redirects never receive tokens."""

    def __init__(self):
        self._opener = request.build_opener(_NoRedirect)

    def request(self, method, path, body, token):
        if (method not in ("GET", "POST") or not path.startswith("/repos/") or "#" in path
                or ("?" in path and re.fullmatch(
                    r"/repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/contents/\.codearbiter/work/WORK-[A-F0-9]{32}\.html\?ref=[a-f0-9]{40}", path) is None)):
            raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub operation is outside the fixed issue endpoint")
        payload = None if body is None else json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = request.Request(_BASE + path, data=payload, method=method, headers={
            "Accept": "application/vnd.github+json", "Content-Type": "application/json",
            "Authorization": "Bearer " + token, "User-Agent": "codeArbiter-work",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with self._opener.open(req, timeout=15) as response:
                data = response.read((1 << 20) + 1)
                if len(data) > 1 << 20:
                    raise WorkSyncError("REMOTE_RESPONSE_TOO_LARGE", "GitHub response exceeds the issue read bound")
                value = json.loads(data)
                if type(value) is not dict:
                    raise WorkSyncError("INVALID_REMOTE_RESPONSE", "GitHub returned no issue object")
                return response.status, value
        except error.HTTPError as exc:
            exc.close()
            raise WorkSyncError("GITHUB_HTTP", f"GitHub API returned HTTP {exc.code}") from exc


def _origin_repository(root):
    result = subprocess.run([git_executable(), "remote", "get-url", "origin"], cwd=root,
                            env=root_bound_git_env(), capture_output=True,
                            text=True, encoding="utf-8")
    if result.returncode != 0:
        raise WorkSyncError("ORIGIN_UNAVAILABLE", "Git origin is unavailable; no provider effect was claimed")
    value = result.stdout.strip()
    if value.startswith("git@github.com:"):
        repo = value[len("git@github.com:"):]
    else:
        parsed = parse.urlsplit(value)
        try:
            port = parsed.port
        except ValueError as exc:
            raise WorkSyncError("UNSUPPORTED_ORIGIN", "Git origin has an invalid port") from exc
        if (parsed.scheme not in ("https", "ssh") or parsed.hostname != "github.com"
                or parsed.password or port or parsed.query or parsed.fragment
                or (parsed.username not in (None, "git") if parsed.scheme == "ssh" else parsed.username is not None)):
            raise WorkSyncError("UNSUPPORTED_ORIGIN", "Git origin is not a supported GitHub repository")
        repo = parsed.path.lstrip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]
    if _REPOSITORY.fullmatch(repo) is None:
        raise WorkSyncError("UNSUPPORTED_ORIGIN", "Git origin is not a supported GitHub repository")
    return repo


def _selected(root, client, work_id):
    config = client.call("work-provider-get", {})
    if config["adapter"] != "github" or _REPOSITORY.fullmatch(config["repository"]) is None:
        raise WorkSyncError("UNSUPPORTED_PROVIDER", "Only the fixed GitHub Issues adapter is supported")
    if _origin_repository(root).casefold() != config["repository"].casefold():
        raise WorkSyncError("PROVIDER_BINDING_CHANGED", "Git origin differs from the configured repository")
    work = client.call("work-get", {"work_id": work_id})
    return config, work


def _credential(config, token_lookup):
    token = token_lookup(config["credential_ref"])
    if not isinstance(token, str) or not token:
        raise WorkSyncError("CREDENTIAL_UNAVAILABLE", "The approved owning-process GitHub credential is unavailable")
    return token


def _issue_path(repository, number=None):
    path = "/repos/" + repository + "/issues"
    return path if number is None else path + "/" + str(number)


def _verified_issue(transport, config, work_id, number, token):
    if type(number) is not int or number < 1:
        raise WorkSyncError("INVALID_REMOTE_RESPONSE", "GitHub did not return a valid issue number")
    status, issue = transport.request("GET", _issue_path(config["repository"], number), None, token)
    want_url = f"https://github.com/{config['repository']}/issues/{number}"
    if (status != 200 or issue.get("number") != number
            or str(issue.get("html_url", "")).casefold() != want_url.casefold()
            or _MARKER.format(work_id) not in str(issue.get("body", ""))):
        raise WorkSyncError("REMOTE_BINDING_UNVERIFIED", "GitHub issue readback did not match this work identity")
    return want_url


def _verified_merge(root, transport, config, work, pull_number, token):
    """Observe a merged default-branch PR containing this pending work intent."""
    if type(pull_number) is not int or pull_number < 1:
        raise WorkSyncError("EFFECT_WAITING_FOR_MERGE", "Supply the merged PR number before a contingent effect")
    repo = config["repository"]
    status, pull = transport.request("GET", f"/repos/{repo}/pulls/{pull_number}", None, token)
    sha = pull.get("merge_commit_sha")
    base = pull.get("base") or {}
    base_repo = base.get("repo") if isinstance(base, dict) else None
    if (status != 200 or not pull.get("merged_at") or type(sha) is not str
            or re.fullmatch(r"[a-f0-9]{40}", sha) is None
            or not isinstance(base, dict)
            or not isinstance(base_repo, dict)
            or str(base_repo.get("full_name", "")).casefold() != repo.casefold()):
        raise WorkSyncError("MERGE_UNVERIFIED", "GitHub has no matching merged PR for this repository")
    status, repository = transport.request("GET", f"/repos/{repo}", None, token)
    if status != 200 or base.get("ref") != repository.get("default_branch"):
        raise WorkSyncError("MERGE_UNVERIFIED", "The PR did not merge into the repository default branch")
    result = subprocess.run([git_executable(), "merge-base", "--is-ancestor", sha, "HEAD"],
                            cwd=root, env=root_bound_git_env(), capture_output=True)
    if result.returncode != 0:
        raise WorkSyncError("MERGE_UNVERIFIED", "The observed merge commit is absent from this checkout's HEAD ancestry")
    path = f"/repos/{repo}/contents/.codearbiter/work/{work['work_id']}.html?ref={sha}"
    status, content = transport.request("GET", path, None, token)
    if status != 200 or content.get("encoding") != "base64" or type(content.get("content")) is not str:
        raise WorkSyncError("MERGE_UNVERIFIED", "Merged PR has no readable canonical work item")
    try:
        raw = base64.b64decode("".join(content["content"].split()), validate=True)
        if len(raw) > 1 << 20:
            raise ValueError("merged work is too large")
        start = b'<script id="ca-artifact-model" type="application/json">\n'
        end = b"\n</script>"
        if raw.count(start) != 1 or raw.count(end) != 1:
            raise ValueError("merged work has no unique model")
        model = json.loads(raw.split(start, 1)[1].split(end, 1)[0])
        effect = model["execution"]["provider_effect"]
    except (ValueError, KeyError, TypeError, IndexError, AttributeError, binascii.Error) as exc:
        raise WorkSyncError("MERGE_UNVERIFIED", "Merged work model cannot be verified") from exc
    if (not isinstance(model, dict) or not isinstance(effect, dict)
            or not isinstance(model.get("normative"), dict)
            or model.get("artifact_id") != work["work_id"]
            or model["normative"].get("project_id") != work["project_id"]
            or model["normative"].get("title") != work["title"]
            or model["normative"].get("summary") != work["intent"]
            or effect.get("status") != "pending"
            or effect.get("binding_generation") != config["binding_generation"]):
        raise WorkSyncError("MERGE_UNVERIFIED", "Merged work intent does not match the selected pending effect")
    return sha


def sync(root, client, work_id, transport=None, token_lookup=None, pull_number=None):
    """Send one explicit pending create; a lost result remains outcome_unknown."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    config, work = _selected(Path(root), client, work_id)
    effect = work.get("provider_effect") or {}
    if effect.get("status") != "pending":
        raise WorkSyncError("EFFECT_NOT_PENDING", "No pending create can be sent; reconcile uncertain outcomes first")
    if effect.get("binding_generation") != config["binding_generation"]:
        raise WorkSyncError("PROVIDER_BINDING_CHANGED", "Pending intent belongs to an older provider binding")
    if config["effect_timing"] == "after_merge" and pull_number is None:
        raise WorkSyncError("EFFECT_WAITING_FOR_MERGE", "Contingent issue creation waits for observed merge")
    token = _credential(config, token_lookup)
    merge_sha = None
    if config["effect_timing"] == "after_merge":
        merge_sha = _verified_merge(Path(root), transport, config, work, pull_number, token)
    elif pull_number is not None:
        raise WorkSyncError("INVALID_MERGE_PROOF", "Immediate effects do not use a merge PR number")
    attempt = "github-attempt-" + secrets.token_hex(12)
    claim = {
        "operation_id": "github-claim-" + secrets.token_hex(12), "work_id": work_id,
        "binding_generation": config["binding_generation"], "attempt_id": attempt,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}}
    if merge_sha is not None:
        claim.update(merge_pull_number=pull_number, merge_commit_sha=merge_sha)
    claimed = client.call("work-effect-claim", claim)
    # A changed destination after the claim leaves the conservative unknown
    # state in place; it cannot redirect an in-flight issue creation.
    if client.call("work-provider-get", {})["binding_generation"] != config["binding_generation"]:
        raise WorkSyncError("PROVIDER_BINDING_CHANGED", "Provider changed after the pre-send claim; reconcile before retrying")
    if _origin_repository(Path(root)).casefold() != config["repository"].casefold():
        raise WorkSyncError("PROVIDER_BINDING_CHANGED", "Git origin changed after the pre-send claim; reconcile before retrying")
    body = work["intent"] + "\n\n" + _MARKER.format(work_id)
    try:
        status, created = transport.request("POST", _issue_path(config["repository"]),
                                            {"title": work["title"], "body": body}, token)
        if status != 201:
            raise WorkSyncError("OUTCOME_UNKNOWN", "GitHub create did not return a confirmed issue")
        number = created.get("number")
        url = _verified_issue(transport, config, work_id, number, token)
    except Exception as exc:
        raise WorkSyncError("OUTCOME_UNKNOWN", "GitHub create or readback is uncertain; inspect the remote issue before any retry") from exc
    return client.call("work-effect-record", {
        "operation_id": "github-record-" + secrets.token_hex(12), "work_id": work_id,
        "binding_generation": config["binding_generation"], "attempt_id": attempt,
        "remote_issue_number": number, "remote_issue_url": url,
        "expected": {"revision": claimed["revision"], "model_sha256": claimed["model_sha256"]}})


def reconcile_issue(root, client, work_id, number, transport=None, token_lookup=None):
    """Bind an exact existing issue after a lost response; never create here."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    config, work = _selected(Path(root), client, work_id)
    effect = work.get("provider_effect") or {}
    if effect.get("status") != "outcome_unknown" or effect.get("binding_generation") != config["binding_generation"]:
        raise WorkSyncError("EFFECT_NOT_UNKNOWN", "Selected work has no matching uncertain create to reconcile")
    token = _credential(config, token_lookup)
    url = _verified_issue(transport, config, work_id, number, token)
    return client.call("work-effect-record", {
        "operation_id": "github-reconcile-" + secrets.token_hex(12), "work_id": work_id,
        "binding_generation": config["binding_generation"], "attempt_id": effect["attempt_id"],
        "remote_issue_number": number, "remote_issue_url": url,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})
