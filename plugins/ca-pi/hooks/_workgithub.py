"""Explicit GitHub issue effects for portable native work.

The native record owns the pre-send claim and remote binding. This module owns
one fixed HTTPS transport; no repository file contains a token or executable
provider template. An uncertain create is never posted a second time.
"""

from __future__ import annotations

import json
import base64
import binascii
from datetime import datetime, timezone
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
_REPO_PATH = r"/repos/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9_.-]{0,99}"
_PROJECT_READ = """query($project: ID!, $issue: ID!, $after: String) {
  project: node(id: $project) { __typename ... on ProjectV2 { id } }
  issue: node(id: $issue) { ... on Issue {
    id
    projectItems(first: 100, after: $after) {
      nodes { id project { id } content { ... on Issue { id } } }
      pageInfo { hasNextPage endCursor }
    }
  } }
}"""
_PROJECT_ADD = """mutation($project: ID!, $issue: ID!) {
  addProjectV2ItemById(input: { projectId: $project, contentId: $issue }) {
    item { id }
  }
}"""
_PROJECT_FIELD_READ = """query($project: ID!, $issue: ID!, $item: ID!, $field: ID!, $after: String) {
  project: node(id: $project) { ... on ProjectV2 { id } }
  issue: node(id: $issue) { ... on Issue { id } }
  field: node(id: $field) { __typename ... on ProjectV2SingleSelectField {
    id dataType project { id } options { id }
  } }
  item: node(id: $item) { ... on ProjectV2Item {
    id project { id } content { ... on Issue { id } }
    fieldValues(first: 100, after: $after) {
      nodes { __typename ... on ProjectV2ItemFieldSingleSelectValue {
        optionId field { ... on ProjectV2SingleSelectField { id } }
      } }
      pageInfo { hasNextPage endCursor }
    }
  } }
}"""
_PROJECT_FIELD_UPDATE = """mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
  updateProjectV2ItemFieldValue(input: {
    projectId: $project, itemId: $item, fieldId: $field,
    value: { singleSelectOptionId: $option }
  }) { projectV2Item { id } }
}"""
_PROJECT_FIELDS = """query($project: ID!) {
  project: node(id: $project) { __typename ... on ProjectV2 {
    id fields(first: 100) {
      nodes { __typename ... on ProjectV2SingleSelectField {
        id name options { id name }
      } }
      pageInfo { hasNextPage }
    }
  } }
}"""
_PROJECT_USER_LOOKUP = """query($login: String!, $number: Int!) {
  owner: user(login: $login) { projectV2(number: $number) { id url } }
}"""
_PROJECT_ORG_LOOKUP = """query($login: String!, $number: Int!) {
  owner: organization(login: $login) { projectV2(number: $number) { id url } }
}"""
_GLOBAL_NODE_ID = re.compile(r"[A-Za-z0-9_+/=-]{8,256}\Z")
_OPTION_ID = re.compile(r"[A-Za-z0-9_+/=-]{1,128}\Z")
_PROJECT_URL_PATH = re.compile(r"/(users|orgs)/([A-Za-z0-9][A-Za-z0-9-]{0,38})/projects/([1-9][0-9]{0,8})\Z")


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
        allowed = {
            "GET": (rf"{_REPO_PATH}", rf"{_REPO_PATH}/issues/[1-9][0-9]*",
                    rf"{_REPO_PATH}/pulls/[1-9][0-9]*",
                    rf"{_REPO_PATH}/pulls/[1-9][0-9]*/files\?per_page=100&page=([1-9]|[12][0-9]|30)",
                    rf"{_REPO_PATH}/contents/\.codearbiter/work/WORK-[A-F0-9]{{32}}\.html\?ref=[a-f0-9]{{40}}"),
            "POST": (rf"{_REPO_PATH}/issues",),
            "PATCH": (rf"{_REPO_PATH}/issues/[1-9][0-9]*",),
        }
        if not any(re.fullmatch(pattern, path) for pattern in allowed.get(method, ())):
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
                if type(value) is not dict and not ("/files?" in path and type(value) is list):
                    raise WorkSyncError("INVALID_REMOTE_RESPONSE", "GitHub returned an unexpected response")
                return response.status, value
        except error.HTTPError as exc:
            exc.close()
            raise WorkSyncError("GITHUB_HTTP", f"GitHub API returned HTTP {exc.code}") from exc

    def graphql(self, query, variables, token):
        variable_sets = {
            _PROJECT_READ: {"project", "issue", "after"},
            _PROJECT_ADD: {"project", "issue"},
            _PROJECT_FIELD_READ: {"project", "issue", "item", "field", "after"},
            _PROJECT_FIELD_UPDATE: {"project", "item", "field", "option"},
            _PROJECT_FIELDS: {"project"},
            _PROJECT_USER_LOOKUP: {"login", "number"},
            _PROJECT_ORG_LOOKUP: {"login", "number"},
        }
        if query not in variable_sets or type(variables) is not dict:
            raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub GraphQL operation is outside the fixed Projects contract")
        if set(variables) != variable_sets[query]:
            raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub GraphQL variables are outside the fixed Projects contract")
        for key in ("project", "issue", "item", "field"):
            if key in variables and (type(variables[key]) is not str or _GLOBAL_NODE_ID.fullmatch(variables[key]) is None):
                raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub GraphQL node ID is invalid")
        if ("after" in variables and variables["after"] is not None
                and (type(variables["after"]) is not str or len(variables["after"]) > 512)):
            raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub GraphQL cursor is invalid")
        if "option" in variables and (type(variables["option"]) is not str
                                      or _OPTION_ID.fullmatch(variables["option"]) is None):
            raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub GraphQL option ID is invalid")
        if "login" in variables and (type(variables["login"]) is not str
                                     or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,38}", variables["login"]) is None):
            raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub Projects owner is invalid")
        if "number" in variables and (type(variables["number"]) is not int
                                      or not 1 <= variables["number"] <= 999_999_999):
            raise WorkSyncError("UNSUPPORTED_REQUEST", "GitHub Projects number is invalid")
        payload = json.dumps({"query": query, "variables": variables}, separators=(",", ":")).encode("utf-8")
        req = request.Request(_BASE + "/graphql", data=payload, method="POST", headers={
            "Accept": "application/vnd.github+json", "Content-Type": "application/json",
            "Authorization": "Bearer " + token, "User-Agent": "codeArbiter-work",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        try:
            with self._opener.open(req, timeout=15) as response:
                raw = response.read((1 << 20) + 1)
                if len(raw) > 1 << 20:
                    raise WorkSyncError("REMOTE_RESPONSE_TOO_LARGE", "GitHub Projects response exceeds the read bound")
                value = json.loads(raw)
                if response.status != 200 or type(value) is not dict or value.get("errors") or type(value.get("data")) is not dict:
                    raise WorkSyncError("INVALID_REMOTE_RESPONSE", "GitHub Projects returned an error or incomplete response")
                return value
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


def _verified_issue_data(transport, config, work_id, number, token):
    if type(number) is not int or number < 1:
        raise WorkSyncError("INVALID_REMOTE_RESPONSE", "GitHub did not return a valid issue number")
    status, issue = transport.request("GET", _issue_path(config["repository"], number), None, token)
    want_url = f"https://github.com/{config['repository']}/issues/{number}"
    markers = re.findall(r"<!-- codearbiter-work: (WORK-[A-F0-9]{32}) -->",
                         str(issue.get("body", "")))
    if (status != 200 or issue.get("number") != number
            or str(issue.get("html_url", "")).casefold() != want_url.casefold()
            or markers != [work_id]
            or issue.get("pull_request") is not None
            or issue.get("state") not in ("open", "closed")):
        raise WorkSyncError("REMOTE_BINDING_UNVERIFIED", "GitHub issue readback did not match this work identity")
    return want_url, issue


def _verified_issue(transport, config, work_id, number, token):
    url, issue = _verified_issue_data(transport, config, work_id, number, token)
    return url, issue["state"]


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
    work_path = f".codearbiter/work/{work['work_id']}.html"
    changed = False
    for page in range(1, 31):
        files_status, files = transport.request(
            "GET", f"/repos/{repo}/pulls/{pull_number}/files?per_page=100&page={page}", None, token)
        if files_status != 200 or type(files) is not list or len(files) > 100:
            raise WorkSyncError("MERGE_UNVERIFIED", "Merged PR files cannot be verified")
        if any(type(item) is dict and item.get("filename") == work_path
               and item.get("status") in ("added", "modified", "renamed") for item in files):
            changed = True
            break
        if len(files) < 100:
            break
    if not changed:
        raise WorkSyncError("MERGE_UNVERIFIED", "Merged PR did not change the selected work item")
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
            or effect.get("kind") != (work.get("provider_effect") or {}).get("kind")
            or effect.get("desired_state") != (work.get("provider_effect") or {}).get("desired_state")
            or effect.get("remote_issue_number") != (work.get("provider_effect") or {}).get("remote_issue_number")
            or effect.get("binding_generation") != config["binding_generation"]):
        raise WorkSyncError("MERGE_UNVERIFIED", "Merged work intent does not match the selected pending effect")
    return sha


def sync(root, client, work_id, transport=None, token_lookup=None, pull_number=None):
    """Send one explicit pending issue effect; uncertain results are not retried."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    config, work = _selected(Path(root), client, work_id)
    effect = work.get("provider_effect") or {}
    if effect.get("status") != "pending":
        raise WorkSyncError("EFFECT_NOT_PENDING", "No pending issue effect can be sent; reconcile uncertain outcomes first")
    if effect.get("kind") not in ("create_issue", "status_update"):
        raise WorkSyncError("UNSUPPORTED_EFFECT", "The pending issue effect is unsupported")
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
    if effect["kind"] == "status_update":
        number = effect.get("remote_issue_number")
        url, observed = _verified_issue(transport, config, work_id, number, token)
        if url != effect.get("remote_issue_url"):
            raise WorkSyncError("REMOTE_BINDING_UNVERIFIED", "The bound issue URL changed")
        if observed != effect.get("remote_state"):
            client.call("work-effect-conflict", {
                "operation_id": "github-conflict-" + secrets.token_hex(12), "work_id": work_id,
                "binding_generation": config["binding_generation"], "remote_state": observed,
                "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})
            raise WorkSyncError("REMOTE_CONFLICT", "GitHub issue status changed since the last verified observation; review it before restaging")
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
    try:
        if effect["kind"] == "create_issue":
            body = work["intent"] + "\n\n" + _MARKER.format(work_id)
            status, created = transport.request("POST", _issue_path(config["repository"]),
                                                {"title": work["title"], "body": body}, token)
            if status != 201:
                raise WorkSyncError("OUTCOME_UNKNOWN", "GitHub create did not return a confirmed issue")
            number = created.get("number")
        else:
            number = effect["remote_issue_number"]
            status, _ = transport.request("PATCH", _issue_path(config["repository"], number),
                                          {"state": effect["desired_state"]}, token)
            if status != 200:
                raise WorkSyncError("OUTCOME_UNKNOWN", "GitHub status update did not return a confirmed issue")
        url, remote_state = _verified_issue(transport, config, work_id, number, token)
        if effect["kind"] == "status_update" and remote_state != effect["desired_state"]:
            raise WorkSyncError("OUTCOME_UNKNOWN", "GitHub status readback differs from the requested state")
    except Exception as exc:
        raise WorkSyncError("OUTCOME_UNKNOWN", "GitHub send or readback is uncertain; inspect the remote issue before any retry") from exc
    return client.call("work-effect-record", {
        "operation_id": "github-record-" + secrets.token_hex(12), "work_id": work_id,
        "binding_generation": config["binding_generation"], "attempt_id": attempt,
        "remote_issue_number": number, "remote_issue_url": url, "remote_state": remote_state,
        "expected": {"revision": claimed["revision"], "model_sha256": claimed["model_sha256"]}})


def reconcile_issue(root, client, work_id, number, transport=None, token_lookup=None):
    """Bind an exact existing issue after a lost response; never create here."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    config, work = _selected(Path(root), client, work_id)
    effect = work.get("provider_effect") or {}
    if (effect.get("kind") != "create_issue" or effect.get("status") != "outcome_unknown"
            or effect.get("binding_generation") != config["binding_generation"]):
        raise WorkSyncError("EFFECT_NOT_UNKNOWN", "Selected work has no matching uncertain create to reconcile")
    token = _credential(config, token_lookup)
    url, remote_state = _verified_issue(transport, config, work_id, number, token)
    return client.call("work-effect-record", {
        "operation_id": "github-reconcile-" + secrets.token_hex(12), "work_id": work_id,
        "binding_generation": config["binding_generation"], "attempt_id": effect["attempt_id"],
        "remote_issue_number": number, "remote_issue_url": url, "remote_state": remote_state,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})


def adopt_issue(root, client, work_id, number, transport=None, token_lookup=None,
                operation_id=None):
    """Bind an already correlated issue without a create request or merge claim."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    config, work = _selected(Path(root), client, work_id)
    effect = work.get("provider_effect") or {}
    if effect and (effect.get("kind") != "create_issue" or effect.get("status") != "pending"):
        raise WorkSyncError("EFFECT_ALREADY_SENT", "Existing issue binding or uncertain send must be reconciled first")
    token = _credential(config, token_lookup)
    url, remote_state = _verified_issue(transport, config, work_id, number, token)
    return client.call("work-effect-adopt", {
        "operation_id": operation_id or "github-adopt-" + secrets.token_hex(12),
        "work_id": work_id, "binding_generation": config["binding_generation"],
        "remote_issue_number": number, "remote_issue_url": url, "remote_state": remote_state,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})


def reconcile_status(root, client, work_id, transport=None, token_lookup=None, accept_remote=False):
    """Read back an uncertain status update without issuing another PATCH."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    config, work = _selected(Path(root), client, work_id)
    effect = work.get("provider_effect") or {}
    if (effect.get("kind") != "status_update" or effect.get("status") != "outcome_unknown"
            or effect.get("binding_generation") != config["binding_generation"]):
        raise WorkSyncError("EFFECT_NOT_UNKNOWN", "Selected work has no uncertain status update to reconcile")
    token = _credential(config, token_lookup)
    number = effect["remote_issue_number"]
    url, remote_state = _verified_issue(transport, config, work_id, number, token)
    if url != effect["remote_issue_url"]:
        raise WorkSyncError("REMOTE_BINDING_UNVERIFIED", "The bound issue URL changed")
    if remote_state != effect["desired_state"]:
        if not accept_remote:
            raise WorkSyncError("OUTCOME_UNKNOWN", f"Remote issue is {remote_state}; inspect it, then use --accept-remote to record a conflict without resending")
        return client.call("work-effect-conflict", {
            "operation_id": "github-accept-remote-" + secrets.token_hex(12), "work_id": work_id,
            "binding_generation": config["binding_generation"], "attempt_id": effect["attempt_id"],
            "remote_state": remote_state,
            "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})
    return client.call("work-effect-record", {
        "operation_id": "github-reconcile-status-" + secrets.token_hex(12), "work_id": work_id,
        "binding_generation": config["binding_generation"], "attempt_id": effect["attempt_id"],
        "remote_issue_number": number, "remote_issue_url": url, "remote_state": remote_state,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})


def _project_selected(root, client, work_id):
    issue_config, work = _selected(Path(root), client, work_id)
    project_config = client.call("work-project-get", {})
    if (project_config["repository"].casefold() != issue_config["repository"].casefold()
            or project_config["credential_ref"] != issue_config["credential_ref"]):
        raise WorkSyncError("PROJECT_BINDING_CHANGED", "Project configuration differs from the selected issue provider")
    issue_effect = work.get("provider_effect") or {}
    project_effect = work.get("project_effect") or {}
    if (type(issue_effect.get("remote_issue_number")) is not int
            or issue_effect.get("remote_issue_number") != project_effect.get("remote_issue_number")):
        raise WorkSyncError("EFFECT_NOT_BOUND", "Project effect requires the same verified issue binding")
    if project_effect.get("binding_generation") != project_config["binding_generation"]:
        raise WorkSyncError("PROJECT_BINDING_CHANGED", "Project intent belongs to an older configuration")
    return issue_config, project_config, work


def _project_issue(transport, issue_config, work, token):
    number = work["provider_effect"]["remote_issue_number"]
    url, issue = _verified_issue_data(transport, issue_config, work["work_id"], number, token)
    if url != work["provider_effect"]["remote_issue_url"]:
        raise WorkSyncError("REMOTE_BINDING_UNVERIFIED", "Bound issue URL differs from GitHub readback")
    node_id = issue.get("node_id")
    if type(node_id) is not str or _GLOBAL_NODE_ID.fullmatch(node_id) is None:
        raise WorkSyncError("REMOTE_BINDING_UNVERIFIED", "GitHub did not return a valid issue node")
    return node_id


def _graph_data(response):
    if type(response) is not dict or response.get("errors") or type(response.get("data")) is not dict:
        raise WorkSyncError("INVALID_REMOTE_RESPONSE", "GitHub Projects returned a partial or malformed GraphQL result")
    return response["data"]


def discover_project(root, client, project_url, transport=None, token_lookup=None):
    """Resolve one explicit GitHub Projects v2 URL through its owning user or org."""
    if type(project_url) is not str or len(project_url) > 256:
        raise WorkSyncError("INVALID_PROJECT_URL", "Supply a GitHub Projects v2 board URL")
    parsed = parse.urlsplit(project_url)
    match = _PROJECT_URL_PATH.fullmatch(parsed.path)
    if (parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.query or parsed.fragment or match is None):
        raise WorkSyncError("INVALID_PROJECT_URL", "Supply a canonical GitHub Projects v2 board URL")
    owner_kind, login, number_text = match.groups()
    config = client.call("work-provider-get", {})
    if (config.get("adapter") != "github" or type(config.get("repository")) is not str
            or _REPOSITORY.fullmatch(config["repository"]) is None
            or _origin_repository(Path(root)).casefold() != config["repository"].casefold()):
        raise WorkSyncError("PROVIDER_BINDING_CHANGED", "A selected GitHub issue provider is required")
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    token = _credential(config, token_lookup)
    query = _PROJECT_USER_LOOKUP if owner_kind == "users" else _PROJECT_ORG_LOOKUP
    data = _graph_data(transport.graphql(query, {"login": login, "number": int(number_text)}, token))
    owner = data.get("owner")
    project = owner.get("projectV2") if type(owner) is dict else None
    if (type(project) is not dict or type(project.get("id")) is not str
            or _GLOBAL_NODE_ID.fullmatch(project["id"]) is None
            or project.get("url") != project_url):
        raise WorkSyncError("REMOTE_BINDING_UNVERIFIED", "GitHub Projects URL did not resolve to the selected board")
    return {"project_node_id": project["id"], "project_url": project_url}


def _find_project_item(transport, project_id, issue_id, token):
    found = None
    cursor = None
    for _ in range(30):
        response = transport.graphql(_PROJECT_READ, {
            "project": project_id, "issue": issue_id, "after": cursor}, token)
        data = _graph_data(response)
        project = data.get("project")
        issue = data.get("issue")
        connection = issue.get("projectItems") if type(issue) is dict else None
        if (type(project) is not dict or project.get("__typename") != "ProjectV2"
                or project.get("id") != project_id or type(issue) is not dict
                or issue.get("id") != issue_id or type(connection) is not dict):
            raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Project or issue node did not match the configured binding")
        nodes, page = connection.get("nodes"), connection.get("pageInfo")
        if type(nodes) is not list or len(nodes) > 100 or type(page) is not dict or type(page.get("hasNextPage")) is not bool:
            raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project item listing is malformed")
        for item in nodes:
            if (type(item) is not dict or type(item.get("project")) is not dict
                    or type(item.get("content")) is not dict):
                raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project item listing contains an invalid node")
            if item["content"].get("id") != issue_id:
                raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Project item contains a different issue")
            if item["project"].get("id") == project_id:
                item_id = item.get("id")
                if type(item_id) is not str or _GLOBAL_NODE_ID.fullmatch(item_id) is None:
                    raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project item ID is invalid")
                if found is not None and found != item_id:
                    raise WorkSyncError("PROJECT_CONFLICT", "Issue has more than one item in the selected Project")
                found = item_id
        if not page["hasNextPage"]:
            return found
        next_cursor = page.get("endCursor")
        if type(next_cursor) is not str or not 1 <= len(next_cursor) <= 512 or next_cursor == cursor:
            raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project item cursor did not advance")
        cursor = next_cursor
    raise WorkSyncError("PROJECT_SCAN_LIMIT", "Issue has more than 3000 Project items; no mutation was attempted")


def _record_project(client, work, project_config, attempt_id, item_id, observed_option_id=None):
    request = {
        "operation_id": "github-project-record-" + secrets.token_hex(12),
        "work_id": work["work_id"], "binding_generation": project_config["binding_generation"],
        "attempt_id": attempt_id, "remote_item_id": item_id,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}}
    if observed_option_id is not None:
        request["observed_option_id"] = observed_option_id
    return client.call("work-project-record", request)


def project_fields(root, client, work_id, transport=None, token_lookup=None):
    """Read bounded single-select field and option IDs from the selected board."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    issue_config, project_config, work = _project_selected(root, client, work_id)
    effect = work["project_effect"]
    if type(effect.get("remote_item_id")) is not str or _GLOBAL_NODE_ID.fullmatch(effect["remote_item_id"]) is None:
        raise WorkSyncError("PROJECT_ITEM_UNVERIFIED", "Project field discovery requires an attached item")
    token = _credential(project_config, token_lookup)
    issue_id = _project_issue(transport, issue_config, work, token)
    project_id = project_config["project_node_id"]
    if _find_project_item(transport, project_id, issue_id, token) != effect["remote_item_id"]:
        raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Selected Project item no longer contains the bound issue")
    data = _graph_data(transport.graphql(_PROJECT_FIELDS, {"project": project_id}, token))
    project = data.get("project")
    fields = project.get("fields") if type(project) is dict else None
    if (type(project) is not dict or project.get("__typename") != "ProjectV2"
            or project.get("id") != project_id or type(fields) is not dict
            or type(fields.get("nodes")) is not list or len(fields["nodes"]) > 100
            or type(fields.get("pageInfo")) is not dict
            or type(fields["pageInfo"].get("hasNextPage")) is not bool):
        raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project field listing is malformed")
    if fields["pageInfo"]["hasNextPage"]:
        raise WorkSyncError("PROJECT_SCAN_LIMIT", "Project field listing exceeds the read bound")
    selected = []
    field_ids = set()
    for field in fields["nodes"]:
        if type(field) is not dict:
            raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project field listing contains an invalid node")
        if field.get("__typename") != "ProjectV2SingleSelectField":
            continue
        field_id, name, options = field.get("id"), field.get("name"), field.get("options")
        if (type(field_id) is not str or _GLOBAL_NODE_ID.fullmatch(field_id) is None
                or field_id in field_ids or type(name) is not str or len(name) > 256
                or type(options) is not list or len(options) > 50):
            raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project single-select field is malformed")
        field_ids.add(field_id)
        choices = []
        option_ids = set()
        for option in options:
            option_id = option.get("id") if type(option) is dict else None
            option_name = option.get("name") if type(option) is dict else None
            if (type(option_id) is not str or _OPTION_ID.fullmatch(option_id) is None
                    or option_id in option_ids or type(option_name) is not str or len(option_name) > 256):
                raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project single-select option is malformed")
            option_ids.add(option_id)
            choices.append({"option_id": option_id, "name": option_name})
        selected.append({"field_id": field_id, "name": name, "options": choices})
    return {"work_id": work_id, "project_node_id": project_id,
            "remote_item_id": effect["remote_item_id"], "fields": selected}


def observe_project_field(root, client, work_id, field_id, transport=None, token_lookup=None):
    """Read one attached item's current single-select option without a write."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    issue_config, project_config, work = _project_selected(root, client, work_id)
    effect = work["project_effect"]
    if type(effect.get("remote_item_id")) is not str or _GLOBAL_NODE_ID.fullmatch(effect["remote_item_id"]) is None:
        raise WorkSyncError("PROJECT_ITEM_UNVERIFIED", "Project field read requires an attached item")
    if type(field_id) is not str or _GLOBAL_NODE_ID.fullmatch(field_id) is None:
        raise WorkSyncError("INVALID_PROJECT_FIELD", "Project field ID is invalid")
    token = _credential(project_config, token_lookup)
    issue_id = _project_issue(transport, issue_config, work, token)
    project_id, item_id = project_config["project_node_id"], effect["remote_item_id"]
    if _find_project_item(transport, project_id, issue_id, token) != item_id:
        raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Selected Project item no longer contains the bound issue")
    option_id = _read_project_option(transport, project_id, issue_id, item_id,
                                     field_id, None, token)
    return {"work_id": work_id, "project_node_id": project_id,
            "remote_item_id": item_id, "field_id": field_id, "option_id": option_id}


def stage_project_field(root, client, work_id, field_id, option_id, operation_id,
                        transport=None, token_lookup=None):
    """Observe the current remote value and stage one explicit desired option."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    issue_config, project_config, work = _project_selected(root, client, work_id)
    effect = work["project_effect"]
    if effect.get("status") not in ("synchronized", "conflict"):
        raise WorkSyncError("EFFECT_NOT_BOUND", "Selected Project item is not ready for a field update")
    if (type(field_id) is not str or _GLOBAL_NODE_ID.fullmatch(field_id) is None
            or type(option_id) is not str or _OPTION_ID.fullmatch(option_id) is None):
        raise WorkSyncError("INVALID_PROJECT_FIELD", "Project field or option ID is invalid")
    token = _credential(project_config, token_lookup)
    issue_id = _project_issue(transport, issue_config, work, token)
    project_id, item_id = project_config["project_node_id"], effect["remote_item_id"]
    if _find_project_item(transport, project_id, issue_id, token) != item_id:
        raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Selected Project item no longer contains the bound issue")
    observed = _read_project_option(transport, project_id, issue_id, item_id,
                                    field_id, option_id, token)
    return client.call("work-project-stage-field", {
        "operation_id": operation_id, "work_id": work_id,
        "binding_generation": project_config["binding_generation"],
        "field_id": field_id, "desired_option_id": option_id,
        "expected_remote_option_id": observed,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})


def sync_project(root, client, work_id, transport=None, token_lookup=None):
    """Attach one already bound issue to an explicitly configured GitHub Project."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    issue_config, project_config, work = _project_selected(root, client, work_id)
    if work["project_effect"]["status"] != "pending":
        raise WorkSyncError("EFFECT_NOT_PENDING", "Project effect is not pending; reconcile an uncertain result first")
    token = _credential(project_config, token_lookup)
    issue_id = _project_issue(transport, issue_config, work, token)
    project_id = project_config["project_node_id"]
    # Complete discovery before the pre-send claim. An incomplete listing
    # cannot justify adding a second remote item.
    existing = _find_project_item(transport, project_id, issue_id, token)
    attempt = "github-project-attempt-" + secrets.token_hex(12)
    claimed = client.call("work-project-claim", {
        "operation_id": "github-project-claim-" + secrets.token_hex(12),
        "work_id": work_id, "binding_generation": project_config["binding_generation"],
        "attempt_id": attempt,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})
    if (client.call("work-project-get", {})["binding_generation"] != project_config["binding_generation"]
            or _origin_repository(Path(root)).casefold() != project_config["repository"].casefold()):
        raise WorkSyncError("PROJECT_BINDING_CHANGED", "Project binding changed after the pre-send claim")
    try:
        if existing is None:
            response = transport.graphql(_PROJECT_ADD, {
                "project": project_id, "issue": issue_id}, token)
            data = _graph_data(response)
            added = data.get("addProjectV2ItemById")
            item = added.get("item") if type(added) is dict else None
            item_id = item.get("id") if type(item) is dict else None
            if type(item_id) is not str or _GLOBAL_NODE_ID.fullmatch(item_id) is None:
                raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project mutation did not return an item ID")
            observed = _find_project_item(transport, project_id, issue_id, token)
            if observed != item_id:
                raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Project readback did not match the added item")
        else:
            item_id = existing
    except Exception as exc:
        raise WorkSyncError("OUTCOME_UNKNOWN", "Project add or readback is uncertain; reconcile before retrying") from exc
    return _record_project(client, claimed, project_config, attempt, item_id)


def reconcile_project(root, client, work_id, transport=None, token_lookup=None):
    """Resolve a lost Project response by readback only; never send a second add."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    issue_config, project_config, work = _project_selected(root, client, work_id)
    effect = work["project_effect"]
    if effect["status"] != "outcome_unknown":
        raise WorkSyncError("EFFECT_NOT_UNKNOWN", "Selected work has no uncertain Project item to reconcile")
    token = _credential(project_config, token_lookup)
    issue_id = _project_issue(transport, issue_config, work, token)
    item_id = _find_project_item(transport, project_config["project_node_id"], issue_id, token)
    if item_id is None:
        raise WorkSyncError("PROJECT_ITEM_UNVERIFIED", "No matching Project item was found; outcome remains unknown")
    return _record_project(client, work, project_config, effect["attempt_id"], item_id)


def _read_project_option(transport, project_id, issue_id, item_id, field_id, desired_option_id, token):
    found = False
    value = None
    cursor = None
    for _ in range(30):
        response = transport.graphql(_PROJECT_FIELD_READ, {
            "project": project_id, "issue": issue_id, "item": item_id,
            "field": field_id, "after": cursor}, token)
        data = _graph_data(response)
        project = data.get("project")
        issue = data.get("issue")
        item = data.get("item")
        field = data.get("field")
        if (type(project) is not dict or project.get("id") != project_id
                or type(issue) is not dict or issue.get("id") != issue_id
                or type(field) is not dict or field.get("__typename") != "ProjectV2SingleSelectField"
                or field.get("id") != field_id or field.get("dataType") != "SINGLE_SELECT"
                or type(field.get("project")) is not dict
                or field["project"].get("id") != project_id
                or type(item) is not dict or item.get("id") != item_id
                or type(item.get("project")) is not dict
                or item["project"].get("id") != project_id
                or type(item.get("content")) is not dict
                or item["content"].get("id") != issue_id):
            raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Project option field does not belong to the selected issue item")
        options = field.get("options")
        if type(options) is not list or len(options) > 256:
            raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project option listing is malformed or exceeds the bound")
        option_ids = set()
        for option in options:
            option_id = option.get("id") if type(option) is dict else None
            if type(option_id) is not str or _OPTION_ID.fullmatch(option_id) is None or option_id in option_ids:
                raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project option identity is invalid or duplicated")
            option_ids.add(option_id)
        if desired_option_id is not None and desired_option_id not in option_ids:
            raise WorkSyncError("PROJECT_OPTION_UNAVAILABLE", "Selected option does not belong to this Project field")
        connection = item.get("fieldValues")
        nodes = connection.get("nodes") if type(connection) is dict else None
        page = connection.get("pageInfo") if type(connection) is dict else None
        if type(nodes) is not list or len(nodes) > 100 or type(page) is not dict or type(page.get("hasNextPage")) is not bool:
            raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project field listing is malformed")
        for node in nodes:
            if type(node) is not dict:
                raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project field listing contains an invalid node")
            if node.get("__typename") != "ProjectV2ItemFieldSingleSelectValue":
                continue
            node_field = node.get("field")
            if type(node_field) is not dict:
                raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project option field has no identity")
            if node_field.get("id") == field_id:
                option_id = node.get("optionId")
                if found or option_id is not None and (type(option_id) is not str or _OPTION_ID.fullmatch(option_id) is None):
                    raise WorkSyncError("PROJECT_CONFLICT", "Selected Project option field has ambiguous values")
                found, value = True, option_id
        if not page["hasNextPage"]:
            return value
        next_cursor = page.get("endCursor")
        if type(next_cursor) is not str or not 1 <= len(next_cursor) <= 512 or next_cursor == cursor:
            raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project field cursor did not advance")
        cursor = next_cursor
    raise WorkSyncError("PROJECT_SCAN_LIMIT", "Project item has more than 3000 field values")


def _conflict_project_field(client, work, project_config, observed):
    effect = work["project_effect"]
    request = {"operation_id": "github-project-conflict-" + secrets.token_hex(12),
               "work_id": work["work_id"], "binding_generation": project_config["binding_generation"],
               "observed_option_id": observed,
               "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}}
    if effect["status"] == "outcome_unknown":
        request["attempt_id"] = effect["attempt_id"]
    return client.call("work-project-conflict", request)


def sync_project_field(root, client, work_id, transport=None, token_lookup=None):
    """Update one selected option after checking its saved remote baseline."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    issue_config, project_config, work = _project_selected(root, client, work_id)
    effect = work["project_effect"]
    if effect["kind"] != "set_single_select" or effect["status"] != "pending":
        raise WorkSyncError("EFFECT_NOT_PENDING", "No pending Project option effect is selected")
    token = _credential(project_config, token_lookup)
    issue_id = _project_issue(transport, issue_config, work, token)
    project_id, item_id, field_id = (project_config["project_node_id"],
                                     effect["remote_item_id"], effect["field_id"])
    if _find_project_item(transport, project_id, issue_id, token) != item_id:
        raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Selected Project item no longer contains the bound issue")
    observed = _read_project_option(transport, project_id, issue_id, item_id, field_id,
                                    effect["desired_option_id"], token)
    if observed != effect["expected_remote_option_id"] and observed != effect["desired_option_id"]:
        _conflict_project_field(client, work, project_config, observed)
        raise WorkSyncError("REMOTE_CONFLICT", "Project option changed before send; inspect it before restaging")
    attempt = "github-project-attempt-" + secrets.token_hex(12)
    claimed = client.call("work-project-claim", {
        "operation_id": "github-project-claim-" + secrets.token_hex(12),
        "work_id": work_id, "binding_generation": project_config["binding_generation"],
        "attempt_id": attempt,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})
    if (client.call("work-project-get", {})["binding_generation"] != project_config["binding_generation"]
            or _origin_repository(Path(root)).casefold() != project_config["repository"].casefold()):
        raise WorkSyncError("PROJECT_BINDING_CHANGED", "Project binding changed after the pre-send claim")
    try:
        if observed != effect["desired_option_id"]:
            response = transport.graphql(_PROJECT_FIELD_UPDATE, {
                "project": project_id, "item": item_id, "field": field_id,
                "option": effect["desired_option_id"]}, token)
            data = _graph_data(response)
            update = data.get("updateProjectV2ItemFieldValue")
            updated = update.get("projectV2Item") if type(update) is dict else None
            if type(updated) is not dict or updated.get("id") != item_id:
                raise WorkSyncError("INVALID_REMOTE_RESPONSE", "Project field update returned a different item")
        readback = _read_project_option(transport, project_id, issue_id, item_id, field_id,
                                        effect["desired_option_id"], token)
        if readback != effect["desired_option_id"]:
            raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Project option readback differs from requested value")
    except Exception as exc:
        raise WorkSyncError("OUTCOME_UNKNOWN", "Project field update or readback is uncertain; reconcile before retrying") from exc
    return _record_project(client, claimed, project_config, attempt, item_id, readback)


def reconcile_project_field(root, client, work_id, transport=None, token_lookup=None):
    """Read an uncertain option result without another update mutation."""
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    issue_config, project_config, work = _project_selected(root, client, work_id)
    effect = work["project_effect"]
    if effect["kind"] != "set_single_select" or effect["status"] != "outcome_unknown":
        raise WorkSyncError("EFFECT_NOT_UNKNOWN", "No uncertain Project field update is selected")
    token = _credential(project_config, token_lookup)
    issue_id = _project_issue(transport, issue_config, work, token)
    if _find_project_item(transport, project_config["project_node_id"], issue_id, token) != effect["remote_item_id"]:
        raise WorkSyncError("PROJECT_BINDING_UNVERIFIED", "Selected Project item no longer contains the bound issue")
    observed = _read_project_option(transport, project_config["project_node_id"], issue_id,
                                    effect["remote_item_id"], effect["field_id"],
                                    effect["desired_option_id"], token)
    if observed != effect["desired_option_id"]:
        if observed == effect["expected_remote_option_id"]:
            raise WorkSyncError("PROJECT_FIELD_UNVERIFIED", "Field still has its prior value; the lost send remains uncertain")
        _conflict_project_field(client, work, project_config, observed)
        raise WorkSyncError("REMOTE_CONFLICT", "Project option differs from the uncertain send; inspect it before restaging")
    return _record_project(client, work, project_config, effect["attempt_id"],
                           effect["remote_item_id"], observed)


def observe_pull(root, client, work_id, number, transport=None, token_lookup=None,
                 credential_ref="CODEARBITER_GITHUB_TOKEN", operation_id=None):
    """Read a PR containing this canonical work item; persist only the observation."""
    if type(number) is not int or number < 1:
        raise WorkSyncError("INVALID_PULL", "Supply a positive GitHub PR number")
    if credential_ref not in ("GH_TOKEN", "GITHUB_TOKEN", "CODEARBITER_GITHUB_TOKEN"):
        raise WorkSyncError("INVALID_CREDENTIAL_REFERENCE", "Unsupported owning-process credential reference")
    transport = transport if transport is not None else GithubTransport()
    token_lookup = token_lookup if token_lookup is not None else os.environ.get
    repo = _origin_repository(Path(root))
    work = client.call("work-get", {"work_id": work_id})
    token = _credential({"credential_ref": credential_ref}, token_lookup)
    try:
        status, pull = transport.request("GET", f"/repos/{repo}/pulls/{number}", None, token)
        head = pull.get("head") if isinstance(pull, dict) else None
        base = pull.get("base") if isinstance(pull, dict) else None
        base_repo = base.get("repo") if isinstance(base, dict) else None
        sha = head.get("sha") if isinstance(head, dict) else None
        url = f"https://github.com/{repo}/pull/{number}"
        if (status != 200 or pull.get("number") != number or pull.get("state") not in ("open", "closed")
                or not isinstance(base_repo, dict)
                or str(base_repo.get("full_name", "")).casefold() != repo.casefold()
                or str(pull.get("html_url", "")).casefold() != url.casefold()
                or type(sha) is not str or re.fullmatch(r"[a-f0-9]{40}", sha) is None
                or pull.get("state") == "open" and pull.get("merged_at")):
            raise WorkSyncError("PULL_BINDING_UNVERIFIED", "GitHub PR identity or state does not match the selected repository")
        work_path = f".codearbiter/work/{work_id}.html"
        found = False
        for page in range(1, 31):
            files_status, files = transport.request("GET", f"/repos/{repo}/pulls/{number}/files?per_page=100&page={page}", None, token)
            if files_status != 200 or type(files) is not list or len(files) > 100:
                raise WorkSyncError("PULL_BINDING_UNVERIFIED", "GitHub PR files cannot be verified")
            if any(type(item) is dict and item.get("filename") == work_path
                   and item.get("status") in ("added", "modified", "renamed") for item in files):
                found = True
                break
            if len(files) < 100:
                break
        if not found:
            raise WorkSyncError("PULL_BINDING_UNVERIFIED", "GitHub PR does not change this canonical work item within the bounded file listing")
        path = f"/repos/{repo}/contents/.codearbiter/work/{work_id}.html?ref={sha}"
        content_status, content = transport.request("GET", path, None, token)
        if (content_status != 200 or content.get("encoding") != "base64"
                or type(content.get("content")) is not str):
            raise WorkSyncError("PULL_BINDING_UNVERIFIED", "PR head has no readable canonical work item")
        raw = base64.b64decode("".join(content["content"].split()), validate=True)
        if len(raw) > 1 << 20:
            raise ValueError("PR work item is too large")
        start = b'<script id="ca-artifact-model" type="application/json">\n'
        end = b"\n</script>"
        if raw.count(start) != 1 or raw.count(end) != 1:
            raise ValueError("PR work item has no unique model")
        remote = json.loads(raw.split(start, 1)[1].split(end, 1)[0])
        if (not isinstance(remote, dict) or remote.get("kind") != "work"
                or remote.get("artifact_id") != work_id
                or not isinstance(remote.get("normative"), dict)
                or remote["normative"].get("project_id") != work["project_id"]):
            raise ValueError("PR work item identity differs")
    except WorkSyncError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError, binascii.Error) as exc:
        raise WorkSyncError("PULL_BINDING_UNVERIFIED", "PR head cannot be bound to this canonical work item") from exc
    except Exception as exc:
        raise WorkSyncError("PULL_OBSERVATION_UNAVAILABLE", "GitHub PR read failed; no delivery observation was recorded") from exc
    state = "merged" if pull.get("merged_at") else pull["state"]
    observed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return client.call("work-update", {"operation_id": operation_id or "github-observe-" + secrets.token_hex(12),
        "work_id": work_id, "action": "observe-delivery", "repository": repo,
        "pull_number": number, "pull_state": state, "observed_at": observed_at,
        "expected": {"revision": work["revision"], "model_sha256": work["model_sha256"]}})
