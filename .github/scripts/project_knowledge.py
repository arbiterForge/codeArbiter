"""Read current project context for source conformance tests through its owner."""
import atexit
import shlex
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _installation():
    # Reuse the same source-built, manifest-verified installation as the
    # knowledge CLI tests. Never decode native HTML with a second parser.
    from test_artifact_authoring import build_installation
    owner, installation = build_installation()
    atexit.register(owner.cleanup)
    return installation


def native_client(root=None):
    from test_artifact_authoring import ArtifactClient
    return ArtifactClient(Path(root) if root is not None else Path(__file__).resolve().parents[2],
                          _installation())


def active_records(document, *, root=None, client=None):
    import test_artifact_authoring  # Adds the canonical bridge import location.
    import _knowledgelib
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    if _knowledgelib.context_format(str(root)) != "html":
        return None
    client = client or native_client(root)
    artifact = _knowledgelib.artifact_id(document)
    from knowledge import _records
    # The owning CLI batches active records with revision binding and bounded
    # pagination. Reuse it rather than launching a native read per record.
    records = _records(client, artifact, "records")
    if not records:
        raise AssertionError(f"current knowledge {artifact} has no readable content")
    return records


def context_text(document, *, root=None, client=None, commands_only=False):
    records = active_records(document, root=root, client=client)
    if records is None:
        import _knowledgelib
        root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
        return (root / _knowledgelib.LEGACY_PATHS[document]).read_text(encoding="utf-8")
    parts = []
    for record in records:
        if commands_only and record.get("type") != "command":
            continue
        if record.get("type") == "command":
            command = record["command"]
            argv = list(command["argv"])
            if argv[0] == "npm" and command["cwd"] != ".":
                argv[1:1] = ["--prefix", command["cwd"]]
            parts.append(shlex.join(argv))
        elif record.get("statement"):
            parts.append(record["statement"])
    return "\n\n".join(parts)
