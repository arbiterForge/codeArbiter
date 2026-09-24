#!/usr/bin/env python3
"""Promote one qualified Codex cohort through immutable Git distribution refs."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("packager", HERE / "build-host-packages.py")
PACKAGER = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(PACKAGER)
MARKETPLACE_REF = "refs/heads/ca-codex-marketplace"
LEDGER_PATH = ".agents/plugins/codex-distribution-tags.json"

def _catalog_version(raw: bytes) -> str:
    try:
        catalog = json.loads(raw)
        plugins = catalog["plugins"]
        matches = [entry for entry in plugins if entry.get("name") == "ca-codex"]
        source = matches[0]["source"] if len(matches) == 1 else None
        package = source.get("package") if isinstance(source, dict) else None
        version = source.get("version") if isinstance(source, dict) else None
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("current Codex marketplace catalog is malformed") from exc
    if package != "@arbiterforge/ca-codex" or PACKAGER.semver_key(version) is None:
        raise ValueError("current Codex marketplace version is not a qualified SemVer ref")
    return version

def _git(repo: Path, *args: str, env=None, check=True, text=True):
    return subprocess.run(["git", *args], cwd=repo, env=env, check=check,
                          capture_output=True, text=text,
                          encoding="utf-8" if text else None)

def _remote_commit(repo: Path, ref: str) -> str | None:
    result = _git(repo, "ls-remote", "publication", ref)
    rows = [line.split() for line in result.stdout.splitlines() if line.strip()]
    if not rows: return None
    if len(rows) != 1 or len(rows[0]) != 2 or rows[0][1] != ref:
        raise ValueError(f"remote ref lookup is ambiguous: {ref}")
    if re.fullmatch(r"[0-9a-f]{40}", rows[0][0]) is None:
        raise ValueError(f"remote ref does not resolve to a full commit: {ref}")
    return rows[0][0]

def _commit_tree(repo: Path, tree: str, *, message: str, parents: list[str]) -> str:
    environment = dict(os.environ)
    environment.update({"GIT_AUTHOR_NAME":"codeArbiter release",
        "GIT_AUTHOR_EMAIL":"release@codearbiter.invalid","GIT_AUTHOR_DATE":"2000-01-01T00:00:00Z",
        "GIT_COMMITTER_NAME":"codeArbiter release","GIT_COMMITTER_EMAIL":"release@codearbiter.invalid",
        "GIT_COMMITTER_DATE":"2000-01-01T00:00:00Z"})
    args = ["commit-tree", tree]
    for parent in parents: args.extend(("-p", parent))
    done = subprocess.run(["git", *args], cwd=repo, env=environment, input=message+"\n",
                          check=True, capture_output=True, text=True, encoding="utf-8")
    commit = done.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None: raise ValueError("invalid Git commit identity")
    return commit

def _source_object(repo: Path, commit: str, path: str) -> bytes:
    observed = _git(repo, "show", f"{commit}:{path}", text=False, check=False)
    if observed.returncode != 0: raise ValueError(f"qualified source commit omits {path}")
    return observed.stdout

def _ledger(previous: bytes | None, *, ref: str, commit: str, source_commit: str,
            cohort_sha256: str, archive_sha256: str,
            npm_sha256: str, npm_integrity: str) -> bytes:
    data = ({"format":"codearbiter.codex-distribution-tags/0.1.0","tags":{}}
            if previous is None else json.loads(previous))
    if set(data) != {"format","tags"} or data["format"] != "codearbiter.codex-distribution-tags/0.1.0" or not isinstance(data["tags"], dict):
        raise ValueError("remote Codex distribution ledger is malformed")
    record = {"commit":commit,"source_commit":source_commit,"cohort_sha256":cohort_sha256,
              "archive_sha256":archive_sha256,"npm_sha256":npm_sha256,
              "npm_integrity":npm_integrity}
    if ref in data["tags"] and data["tags"][ref] != record:
        raise ValueError("same-version Codex distribution ledger record differs")
    data["tags"][ref] = record
    return (json.dumps(data,sort_keys=True,separators=(",",":"))+"\n").encode()

def promote(*, package_root: Path, cohort_sha256: str, source_repo: Path,
            source_commit: str, remote_url: str, catalog_url: str, version: str,
            work: Path, push: bool, advance_channel: bool=False,
            expected_marketplace_head: str | None=None,
            expected_npm_integrity: str | None=None,
            expected_npm_sha256: str | None=None) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{40}", source_commit) is None: raise ValueError("source commit must be a full lowercase commit id")
    if not remote_url or "\n" in remote_url or "\r" in remote_url: raise ValueError("publication remote URL is invalid")
    if PACKAGER.semver_key(version) is None: raise ValueError("Codex distribution version must be SemVer")
    work = work.absolute()
    if work.exists() or work.is_symlink(): raise ValueError("Codex distribution work path already exists")
    work.mkdir(); distribution = work / "distribution"
    staged = PACKAGER.stage_codex_marketplace_distribution(package_root=package_root,
        package_cohort_sha256=cohort_sha256, output=distribution)
    if staged.get("source_commit") != source_commit: raise ValueError("Codex distribution cohort is bound to a different source commit")
    npm = PACKAGER.build_codex_npm_package(
        package_root=package_root, package_cohort_sha256=cohort_sha256,
        output=work / "npm",
    )
    if npm.get("source_commit") != source_commit or npm.get("version") != version:
        raise ValueError("Codex npm package is bound to a different source or version")
    if advance_channel and (
        expected_npm_integrity != npm.get("integrity")
        or expected_npm_sha256 != npm.get("sha256")
    ):
        raise ValueError("verified Codex npm package identity drifted before channel advance")
    manifest = json.loads((distribution/"plugins/ca-codex/.codex-plugin/plugin.json").read_text())
    if manifest.get("version") != version: raise ValueError("Codex distribution version does not match the qualified package")
    catalog_path = ".agents/plugins/marketplace.json"
    catalog_source = _source_object(source_repo, source_commit, catalog_path)
    if catalog_source != (distribution/catalog_path).read_bytes() or hashlib.sha256(catalog_source).hexdigest() != staged["catalog_sha256"]:
        raise ValueError("qualified catalog bytes differ from exact source commit")

    _git(distribution,"init","--quiet"); _git(distribution,"remote","add","publication",remote_url)
    _git(distribution,"add","--all"); tree = _git(distribution,"write-tree").stdout.strip()
    distribution_commit = _commit_tree(distribution,tree,message=(f"codeArbiter ca-codex {version} qualified distribution\n\n"
        f"source-commit: {source_commit}\npackage-cohort-sha256: {cohort_sha256}\narchive-sha256: {staged['archive_sha256']}"),parents=[])
    distribution_ref = f"refs/tags/ca-codex-dist-v{version}"
    existing_distribution = _remote_commit(distribution,distribution_ref)
    if existing_distribution is not None and existing_distribution != distribution_commit:
        raise ValueError("same-version Codex distribution ref already names different bytes")
    existing_marketplace = _remote_commit(distribution,MARKETPLACE_REF)
    expected = None if expected_marketplace_head == "absent" else expected_marketplace_head
    if expected_marketplace_head is not None and existing_marketplace != expected:
        raise ValueError("Codex marketplace expected head drifted")
    catalog = PACKAGER.promoted_codex_catalog(
        catalog_source, package="@arbiterforge/ca-codex", version=version,
        registry="https://registry.npmjs.org",
    )
    catalog_commit = None
    if advance_channel:
        if existing_distribution != distribution_commit:
            raise ValueError("immutable Codex distribution tag must exist before channel advance")
        existing_catalog = previous_ledger = None
        if existing_marketplace is not None:
            _git(distribution,"fetch","--quiet","--no-tags","publication",f"{MARKETPLACE_REF}:refs/remotes/codearbiter/marketplace")
            old = _git(distribution,"show",f"{existing_marketplace}:{catalog_path}",text=False,check=False)
            existing_catalog = old.stdout if old.returncode == 0 else None
            old = _git(distribution,"show",f"{existing_marketplace}:{LEDGER_PATH}",text=False,check=False)
            previous_ledger = old.stdout if old.returncode == 0 else None
            current_version = _catalog_version(existing_catalog) if existing_catalog is not None else None
            if current_version is None or PACKAGER.semver_key(version) < PACKAGER.semver_key(current_version):
                raise ValueError("Codex marketplace channel cannot roll back to an older version")
        ledger = _ledger(previous_ledger,ref=distribution_ref,commit=distribution_commit,
            source_commit=source_commit,cohort_sha256=cohort_sha256,
            archive_sha256=str(staged["archive_sha256"]),
            npm_sha256=str(npm["sha256"]),npm_integrity=str(npm["integrity"]))
        if existing_catalog == catalog and previous_ledger == ledger:
            catalog_commit = existing_marketplace
        else:
            (distribution/catalog_path).write_bytes(catalog)
            ledger_file=distribution/LEDGER_PATH; ledger_file.parent.mkdir(parents=True,exist_ok=True); ledger_file.write_bytes(ledger)
            _git(distribution,"read-tree","--empty"); _git(distribution,"add","--force",catalog_path,LEDGER_PATH)
            catalog_tree=_git(distribution,"write-tree").stdout.strip()
            catalog_commit=_commit_tree(distribution,catalog_tree,message=f"Promote ca-codex {version} qualified distribution",
                parents=([existing_marketplace] if existing_marketplace else [])+[distribution_commit])
    result={**staged,"source_commit":source_commit,"distribution_ref":distribution_ref,
        "distribution_commit":distribution_commit,"marketplace_ref":MARKETPLACE_REF,
        "marketplace_previous_commit":existing_marketplace,"marketplace_commit":catalog_commit,
        "promoted_catalog_sha256":hashlib.sha256(catalog).hexdigest(),
        "npm_file":npm["file"],"npm_sha256":npm["sha256"],
        "npm_integrity":npm["integrity"]}
    if push:
        if existing_distribution is None: _git(distribution,"push","publication",f"{distribution_commit}:{distribution_ref}")
        if _remote_commit(distribution,distribution_ref) != distribution_commit: raise RuntimeError("Codex distribution tag readback drifted")
        if advance_channel and existing_marketplace != catalog_commit:
            lease=f"--force-with-lease={MARKETPLACE_REF}:{existing_marketplace or '0000000000000000000000000000000000000000'}"
            _git(distribution,"push",lease,"publication",f"{catalog_commit}:{MARKETPLACE_REF}")
        if advance_channel and _remote_commit(distribution,MARKETPLACE_REF) != catalog_commit: raise RuntimeError("Codex marketplace channel readback drifted")
    return result

def main(argv=None):
    p=argparse.ArgumentParser()
    for name in ("cohort-sha256","source-commit","remote-url","catalog-url","version"): p.add_argument("--"+name,required=True)
    for name in ("package-root","source-repo","work"): p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--push",action="store_true"); p.add_argument("--advance-channel",action="store_true"); p.add_argument("--expected-marketplace-head")
    p.add_argument("--expected-npm-integrity"); p.add_argument("--expected-npm-sha256")
    a=p.parse_args(argv)
    print(json.dumps(promote(package_root=a.package_root,cohort_sha256=a.cohort_sha256,source_repo=a.source_repo,
        source_commit=a.source_commit,remote_url=a.remote_url,catalog_url=a.catalog_url,version=a.version,work=a.work,
        push=a.push,advance_channel=a.advance_channel,expected_marketplace_head=a.expected_marketplace_head,
        expected_npm_integrity=a.expected_npm_integrity,expected_npm_sha256=a.expected_npm_sha256),indent=2)); return 0
if __name__ == "__main__": raise SystemExit(main())
