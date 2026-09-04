#!/usr/bin/env python3
"""codeArbiter — fail-closed helpers for exact ca-pi npm publication.

The release workflow owns orchestration and credentials. This module validates
the immutable Git/GitHub/package boundary, packs one exact tarball with scripts
disabled, distinguishes registry absence from registry failure, and requires
matching integrity plus npm provenance before success.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path


PACKAGE = "@arbiterforge/ca-pi"
REGISTRY = "https://registry.npmjs.org/"
SCOPED_REGISTRY_OPTION = f"--@arbiterforge:registry={REGISTRY}"
REPOSITORY_URL = "git+https://github.com/arbiterForge/codeArbiter.git"
TAG_RE = re.compile(r"ca-pi-v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
PROVENANCE_PREDICATE = "https://slsa.dev/provenance/v1"
REGISTRY_TIMEOUT_SECONDS = 30
ATTESTATION_MAX_BYTES = 2 * 1024 * 1024
SOURCE_REPOSITORY = "https://github.com/arbiterForge/codeArbiter"
SOURCE_REF = "refs/heads/main"
SOURCE_WORKFLOWS = {
    ".github/workflows/release.yml",
    ".github/workflows/npm-publish.yml",
}


class RegistryUnavailable(ValueError):
    """The registry did not provide usable transport evidence yet."""


def validate_inputs(tag: str, expected_sha: str) -> str:
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError("release tag must be canonical ca-pi-vMAJOR.MINOR.PATCH")
    if SHA_RE.fullmatch(expected_sha) is None:
        raise ValueError("expected SHA must be exactly 40 lowercase hexadecimal characters")
    return ".".join(match.groups())


def validate_sha(value: str, label: str) -> None:
    if SHA_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be exactly 40 lowercase hexadecimal characters")


def validate_package_identity(root: dict, nested: dict, version: str) -> None:
    if root.get("name") != PACKAGE:
        raise ValueError("root package name does not match the public ca-pi package")
    if root.get("version") != version or nested.get("version") != version:
        raise ValueError("tag and synchronized manifest versions do not match")
    if nested.get("name") != PACKAGE or nested.get("private") is not True:
        raise ValueError("nested manifest must retain the private ca-pi package identity")
    repository = root.get("repository")
    if not isinstance(repository, dict) or repository != {
        "type": "git",
        "url": REPOSITORY_URL,
    }:
        raise ValueError("root package repository identity does not match codeArbiter")
    publish = root.get("publishConfig")
    if not isinstance(publish, dict):
        raise ValueError("root publishConfig is missing")
    if publish.get("access") != "public" or publish.get("provenance") is not True:
        raise ValueError("root publishConfig must require public provenance publication")
    if "registry" in publish:
        raise ValueError("publishConfig.registry must not override the approved npm registry")


def validate_project_registry(repo: Path) -> None:
    if (repo / ".npmrc").exists():
        raise ValueError("project .npmrc is forbidden at the publication boundary")


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def validate_git_identity(
    repo: Path, tag: str, expected_sha: str, *, main_ref: str = "origin/main"
) -> None:
    validate_inputs(tag, expected_sha)
    tag_ref = f"refs/tags/{tag}"
    kind = _git(repo, "cat-file", "-t", tag_ref)
    if kind.returncode != 0 or kind.stdout.strip() != "tag":
        raise ValueError("release ref must exist as an annotated tag object")
    peeled = _git(repo, "rev-parse", f"{tag_ref}^{{commit}}")
    if peeled.returncode != 0 or peeled.stdout.strip() != expected_sha:
        raise ValueError("annotated release tag does not peel to the expected commit")
    checked_out = _git(repo, "rev-parse", "HEAD")
    if checked_out.returncode != 0 or checked_out.stdout.strip() != expected_sha:
        raise ValueError("checked-out package does not equal the expected release commit")
    ancestor = _git(repo, "merge-base", "--is-ancestor", expected_sha, main_ref)
    if ancestor.returncode != 0:
        raise ValueError("expected release commit is not contained in protected main")


def validate_main_commit(repo: Path, commit: str, main_ref: str = "origin/main") -> None:
    validate_sha(commit, "attested workflow SHA")
    ancestor = _git(repo, "merge-base", "--is-ancestor", commit, main_ref)
    if ancestor.returncode != 0:
        raise ValueError("attested workflow commit is not contained in protected main")


def validate_release_document(document: dict, tag: str) -> None:
    if document.get("tag_name") != tag:
        raise ValueError("GitHub Release does not name the exact ca-pi tag")
    if document.get("draft") is not False:
        raise ValueError("GitHub Release is missing or remains a draft")


def _registry_document(stdout: str) -> dict:
    try:
        document = json.loads(stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("npm registry returned malformed JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("npm registry returned a non-object response")
    return document


def classify_registry_lookup(
    returncode: int,
    stdout: str,
    stderr: str,
    expected_version: str,
    expected_integrity: str,
) -> str:
    if returncode != 0:
        codes = {
            code.upper()
            for code in re.findall(r"\bE[A-Z0-9_]+\b", f"{stdout}\n{stderr}")
        }
        try:
            error_document = _registry_document(stdout)
        except ValueError:
            error_document = {}
        error = error_document.get("error")
        exact_404 = isinstance(error, dict) and error.get("code") == "E404"
        if codes == {"E404"} and exact_404:
            return "absent"
        retryable_codes = {
            "E429",
            "E500",
            "E502",
            "E503",
            "E504",
            "EAI_AGAIN",
            "EAI_FAIL",
            "ECONNRESET",
            "EHOSTUNREACH",
            "ENETUNREACH",
            "ENOTFOUND",
            "ERR_SOCKET_TIMEOUT",
            "ETIMEDOUT",
        }
        status_text = f"{stdout}\n{stderr}"
        retryable_http_status = re.search(
            r"(?:^|\D)(?:429|5[0-9]{2})(?:\D|$)", status_text
        )
        if (codes and codes <= retryable_codes) or (
            not codes and not exact_404 and retryable_http_status
        ):
            raise RegistryUnavailable("npm registry lookup is temporarily unavailable")
        raise ValueError("npm registry lookup failed without a confirmed 404")
    document = _registry_document(stdout)
    if document.get("version") != expected_version:
        raise ValueError("npm registry version does not match the release")
    dist = document.get("dist")
    if not isinstance(dist, dict) or dist.get("integrity") != expected_integrity:
        raise ValueError("npm registry tarball integrity does not match the packed payload")
    attestations = dist.get("attestations")
    provenance = attestations.get("provenance") if isinstance(attestations, dict) else None
    expected_attestation_url = (
        "https://registry.npmjs.org/-/npm/v1/attestations/"
        f"@arbiterforge%2fca-pi@{expected_version}"
    )
    if not isinstance(attestations, dict) or attestations.get("url") != expected_attestation_url:
        raise ValueError("npm provenance attestation URL is missing or untrusted")
    if not isinstance(provenance, dict) or provenance.get("predicateType") != PROVENANCE_PREDICATE:
        raise ValueError("npm registry has no matching SLSA provenance attestation")
    return "present"


def _integrity_hex(integrity: str) -> str:
    if not integrity.startswith("sha512-"):
        raise ValueError("expected integrity is not SHA-512")
    try:
        digest = base64.b64decode(integrity.removeprefix("sha512-"), validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("expected integrity has malformed base64") from exc
    if len(digest) != 64:
        raise ValueError("expected integrity is not a complete SHA-512 digest")
    return digest.hex()


def validate_attestation_document(
    document: dict,
    version: str,
    integrity: str,
    trusted_sha: str | None,
) -> str:
    if trusted_sha is not None:
        validate_sha(trusted_sha, "trusted workflow SHA")
    attestations = document.get("attestations")
    if not isinstance(attestations, list) or len(attestations) > 8:
        raise ValueError("npm attestation response has an invalid bounded list")
    provenance = [
        item
        for item in attestations
        if isinstance(item, dict) and item.get("predicateType") == PROVENANCE_PREDICATE
    ]
    if len(provenance) != 1:
        raise ValueError("npm response must contain exactly one SLSA provenance attestation")
    try:
        encoded = provenance[0]["bundle"]["dsseEnvelope"]["payload"]
        payload = base64.b64decode(encoded, validate=True)
        if len(payload) > ATTESTATION_MAX_BYTES:
            raise ValueError("npm provenance payload exceeds the evidence bound")
        statement = json.loads(payload.decode("utf-8"))
    except (KeyError, TypeError, UnicodeDecodeError, binascii.Error, json.JSONDecodeError) as exc:
        raise ValueError("npm provenance bundle is malformed") from exc
    if not isinstance(statement, dict) or statement.get("_type") != "https://in-toto.io/Statement/v1":
        raise ValueError("npm provenance statement type is not trusted")
    if statement.get("predicateType") != PROVENANCE_PREDICATE:
        raise ValueError("npm provenance statement predicate is not trusted")
    expected_subject = {
        "name": f"pkg:npm/%40arbiterforge/ca-pi@{version}",
        "digest": {"sha512": _integrity_hex(integrity)},
    }
    if statement.get("subject") != [expected_subject]:
        raise ValueError("npm provenance subject does not match the exact package tarball")
    try:
        build = statement["predicate"]["buildDefinition"]
        workflow = build["externalParameters"]["workflow"]
        dependencies = build["resolvedDependencies"]
        builder = statement["predicate"]["runDetails"]["builder"]["id"]
    except (KeyError, TypeError) as exc:
        raise ValueError("npm provenance source identity is incomplete") from exc
    if not isinstance(workflow, dict):
        raise ValueError("npm provenance workflow identity is not approved")
    if workflow != {
        "repository": SOURCE_REPOSITORY,
        "ref": SOURCE_REF,
        "path": workflow.get("path"),
    } or workflow.get("path") not in SOURCE_WORKFLOWS:
        raise ValueError("npm provenance workflow identity is not approved")
    if not isinstance(dependencies, list) or len(dependencies) != 1:
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    dependency = dependencies[0]
    if not isinstance(dependency, dict) or dependency.get("uri") != (
        f"git+{SOURCE_REPOSITORY}@{SOURCE_REF}"
    ):
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    digest = dependency.get("digest")
    if not isinstance(digest, dict) or set(digest) != {"gitCommit"}:
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    source_sha = digest["gitCommit"]
    if not isinstance(source_sha, str):
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    validate_sha(source_sha, "attested workflow SHA")
    if trusted_sha is not None and source_sha != trusted_sha:
        raise ValueError("npm provenance does not bind the trusted workflow commit")
    if builder != "https://github.com/actions/runner/github-hosted":
        raise ValueError("npm provenance builder is not GitHub-hosted")
    return source_sha


def _signature_failure_detail(evidence: object) -> str:
    """Expose only fixed categories, never registry text or npm stderr."""
    if not isinstance(evidence, dict):
        return "schema=invalid"
    allowed = (
        "EINTEGRITYSIGNATURE", "EATTESTATIONVERIFY", "E503", "E502",
        "E504", "E429", "ETIMEDOUT", "ECONNRESET", "EAI_AGAIN",
    )

    def code(item: object) -> str:
        value = item.get("code") if isinstance(item, dict) else None
        return value if isinstance(value, str) and value in allowed else "unknown"

    invalid = evidence.get("invalid")
    if not isinstance(invalid, list):
        invalid_detail = "malformed"
    elif len(invalid) > 8:
        invalid_detail = "over-limit"
    else:
        invalid_detail = ",".join(sorted({code(item) for item in invalid})) or "none"
    missing = evidence.get("missing")
    missing_detail = ("yes" if missing else "no") if isinstance(missing, list) else "malformed"
    error_detail = code(evidence.get("error")) if "error" in evidence else "none"
    return f"invalid={invalid_detail}; missing={missing_detail}; error={error_detail}"


def verify_registry_authenticity(npm: str, version: str) -> dict:
    """Use npm's supported Sigstore verifier; do not hand-roll bundle crypto."""

    with tempfile.TemporaryDirectory(prefix="codearbiter-npm-signatures-") as tmp:
        root = Path(tmp)
        user_config = root / "user.npmrc"
        global_config = root / "global.npmrc"
        user_config.write_text("", encoding="utf-8")
        global_config.write_text("", encoding="utf-8")
        npm_env = {
            key: value
            for key, value in os.environ.items()
            if not key.lower().startswith("npm_config_")
            and key.upper() not in {"NODE_AUTH_TOKEN", "NPM_TOKEN"}
        }
        npm_env.update(
            {
                "NPM_CONFIG_CACHE": str(root / "cache"),
                "NPM_CONFIG_LOGS_DIR": str(root / "logs"),
                "NPM_CONFIG_USERCONFIG": str(user_config),
                "NPM_CONFIG_GLOBALCONFIG": str(global_config),
            }
        )
        (root / "package.json").write_text(
            json.dumps(
                {
                    "name": "codearbiter-npm-signature-verifier",
                    "version": "1.0.0",
                    "private": True,
                },
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
        try:
            installed = subprocess.run(
                [
                    npm,
                    "install",
                    "--ignore-scripts",
                    "--no-audit",
                    "--no-fund",
                    "--save-exact",
                    f"{PACKAGE}@{version}",
                    f"--registry={REGISTRY}",
                    SCOPED_REGISTRY_OPTION,
                ],
                cwd=root,
                env=npm_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
            if installed.returncode != 0:
                raise ValueError("npm signature verification install failed")
            audited = subprocess.run(
                [
                    npm,
                    "audit",
                    "signatures",
                    "--json",
                    "--include-attestations",
                    f"--registry={REGISTRY}",
                    SCOPED_REGISTRY_OPTION,
                ],
                cwd=root,
                env=npm_env,
                text=True,
                capture_output=True,
                check=False,
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError("npm signature verification timed out") from exc
        try:
            evidence = json.loads(audited.stdout)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("npm signature verification returned malformed evidence") from exc
        if (
            audited.returncode != 0
            or not isinstance(evidence, dict)
            or evidence.get("invalid") != []
            or evidence.get("missing") != []
        ):
            raise ValueError(
                "npm signature or provenance verification failed: "
                + _signature_failure_detail(evidence)
            )
        verified = evidence.get("verified")
        if not isinstance(verified, list) or len(verified) != 1:
            raise ValueError("npm signature verification did not identify one exact package")
        package = verified[0]
        if not isinstance(package, dict) or {
            "name": package.get("name"),
            "version": package.get("version"),
            "location": package.get("location"),
            "registry": package.get("registry"),
        } != {
            "name": PACKAGE,
            "version": version,
            "location": f"node_modules/{PACKAGE}",
            "registry": REGISTRY,
        }:
            raise ValueError("npm signature verification returned the wrong package identity")
        bundles = package.get("attestationBundles")
        if not isinstance(bundles, list) or len(bundles) > 8:
            raise ValueError("npm signature verification returned invalid attestation evidence")
        provenance = [
            item
            for item in bundles
            if isinstance(item, dict) and item.get("predicateType") == PROVENANCE_PREDICATE
        ]
        if len(provenance) != 1:
            raise ValueError("npm signature verification returned ambiguous provenance evidence")
        return {"attestations": provenance}


def parse_pack_report(stdout: str) -> tuple[str, str]:
    try:
        report = json.loads(stdout)
        item = report[0]
        filename = item["filename"]
        integrity = item["integrity"]
    except (IndexError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("npm pack returned malformed artifact evidence") from exc
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or re.fullmatch(r"[A-Za-z0-9._-]+\.tgz", filename) is None
    ):
        raise ValueError("npm pack returned an unsafe tarball path")
    if (
        not isinstance(integrity, str)
        or re.fullmatch(r"sha512-[A-Za-z0-9+/]+={0,2}", integrity) is None
    ):
        raise ValueError("npm pack did not return SHA-512 integrity")
    return filename, integrity


def registry_lookup(npm: str, version: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [
                npm,
                "view",
                f"{PACKAGE}@{version}",
                "version",
                "dist",
                "--json",
                f"--registry={REGISTRY}",
                SCOPED_REGISTRY_OPTION,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=REGISTRY_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RegistryUnavailable("npm registry lookup timed out") from exc


def prepare(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    version = validate_inputs(args.tag, args.expected_sha)
    validate_sha(args.trusted_sha, "trusted workflow SHA")
    validate_git_identity(repo, args.tag, args.expected_sha)
    validate_project_registry(repo)
    root = json.loads((repo / args.root_manifest).read_text(encoding="utf-8"))
    nested = json.loads((repo / args.plugin_manifest).read_text(encoding="utf-8"))
    validate_package_identity(root, nested, version)
    release = json.loads(Path(args.release_json).read_text(encoding="utf-8"))
    validate_release_document(release, args.tag)
    packed = subprocess.run(
        [
            args.npm,
            "pack",
            "--ignore-scripts",
            "--json",
            f"--registry={REGISTRY}",
            SCOPED_REGISTRY_OPTION,
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if packed.returncode != 0:
        raise ValueError("npm pack failed")
    tarball, integrity = parse_pack_report(packed.stdout)
    lookup = registry_lookup(args.npm, version)
    state = classify_registry_lookup(
        lookup.returncode, lookup.stdout, lookup.stderr, version, integrity
    )
    if state == "present":
        verified_document = verify_registry_authenticity(args.npm, version)
        source_sha = validate_attestation_document(
            verified_document, version, integrity, None
        )
        validate_main_commit(repo, source_sha, args.trusted_sha)
    output = Path(args.output)
    with output.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(f"version={version}\n")
        stream.write(f"tarball={repo / tarball}\n")
        stream.write(f"integrity={integrity}\n")
        stream.write(f"skip={'true' if state == 'present' else 'false'}\n")
        stream.write(f"publication_mode={'existing' if state == 'present' else 'new'}\n")
    return 0


def verify(args: argparse.Namespace) -> int:
    version = validate_inputs(args.tag, args.expected_sha)
    validate_sha(args.trusted_sha, "trusted workflow SHA")
    for attempt in range(args.attempts):
        try:
            lookup = registry_lookup(args.npm, version)
            state = classify_registry_lookup(
                lookup.returncode,
                lookup.stdout,
                lookup.stderr,
                version,
                args.integrity,
            )
        except RegistryUnavailable:
            if attempt + 1 >= args.attempts:
                raise
            state = "unavailable"
        if state == "present":
            verified_document = verify_registry_authenticity(args.npm, version)
            source_sha = validate_attestation_document(
                verified_document,
                version,
                args.integrity,
                args.trusted_sha if args.publication_mode == "new" else None,
            )
            if args.publication_mode == "existing":
                validate_main_commit(Path(args.repo), source_sha, args.trusted_sha)
            print(f"verified {PACKAGE}@{version} integrity and provenance")
            return 0
        if attempt + 1 < args.attempts:
            time.sleep(args.delay_seconds)
    raise ValueError("npm publication did not become observable before the evidence deadline")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--tag", required=True)
    common.add_argument("--expected-sha", required=True)
    common.add_argument("--trusted-sha", required=True)
    common.add_argument("--npm", default="npm")
    sub.add_parser("validate", parents=[common])
    prepare_parser = sub.add_parser("prepare", parents=[common])
    prepare_parser.add_argument("--repo", default=".")
    prepare_parser.add_argument("--release-json", required=True)
    prepare_parser.add_argument("--output", required=True)
    prepare_parser.add_argument("--root-manifest", required=True)
    prepare_parser.add_argument("--plugin-manifest", required=True)
    verify_parser = sub.add_parser("verify", parents=[common])
    verify_parser.add_argument("--repo", default=".")
    verify_parser.add_argument("--integrity", required=True)
    verify_parser.add_argument(
        "--publication-mode", required=True, choices=("new", "existing")
    )
    verify_parser.add_argument("--attempts", type=int, default=12)
    verify_parser.add_argument("--delay-seconds", type=float, default=5.0)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "validate":
            validate_inputs(args.tag, args.expected_sha)
            validate_sha(args.trusted_sha, "trusted workflow SHA")
            return 0
        return prepare(args) if args.command == "prepare" else verify(args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"refusing npm publication: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
