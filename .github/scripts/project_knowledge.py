"""Read current project context for source conformance tests through its owner."""
import atexit
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
    from knowledge import current_records
    if _knowledgelib.context_format(str(root)) != "html":
        return None
    return current_records(root, document, client=client or native_client(root))


def context_text(document, *, root=None, client=None, commands_only=False):
    import test_artifact_authoring  # Select the canonical bridge import location.
    import _knowledgelib
    from knowledge import context_text as read_context
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    native = client
    if native is None and _knowledgelib.context_format(str(root)) == "html":
        native = native_client(root)
    return read_context(root, document, client=native, commands_only=commands_only)


def active_document_aliases(root=None):
    """Resolve declared knowledge paths through the active format owner."""
    import test_artifact_authoring  # Select the canonical bridge import location.
    import _knowledgelib
    root = Path(root) if root is not None else Path(__file__).resolve().parents[2]
    if _knowledgelib.context_format(str(root)) != "html":
        return {}
    return {path: (document, _knowledgelib.LEGACY_PATHS[document])
            for paths in (_knowledgelib.LEGACY_PATHS, _knowledgelib.HTML_PATHS)
            for document, path in paths.items()}
