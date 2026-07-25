# Shared test builders for the pruner suite. Bulky transcripts are generated
# here (into tempdirs by the callers) rather than checked in.
import json
import os

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

# Every key os.path.expanduser("~") consults. On POSIX it reads HOME; on Windows
# ntpath reads USERPROFILE first (then HOMEDRIVE+HOMEPATH) and IGNORES HOME — so a
# test that only sets HOME silently writes state/backups/logs into the developer's
# real ~ on Windows, and then fails on re-run from that leftover state.
_HOME_KEYS = ("HOME", "USERPROFILE", "HOMEDRIVE", "HOMEPATH")


def redirect_home(path):
    """Point expanduser('~') at `path` on every platform. Returns a token to pass
    back to restore_home() in tearDown."""
    saved = {k: os.environ.get(k) for k in _HOME_KEYS}
    os.environ["HOME"] = path
    os.environ["USERPROFILE"] = path
    os.environ.pop("HOMEDRIVE", None)
    os.environ.pop("HOMEPATH", None)
    return saved


def restore_home(saved):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as f:
        return f.read()


HOOKS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def durable_plugin_copy(tmpdir):
    """Copy the real plugin's top-level `hooks/*.py` payload into `tmpdir` and
    return the copy's plugin root.

    Since 2026-07-25 the statusline pin writers REFUSE a non-durable plugin root
    (a git worktree), and codeArbiter's own checkout is very often exactly that:
    subagents run in `<repo>/.claude/worktrees/<id>/`. A test that drove the REAL
    plugin root would therefore heal or decline depending on where the suite
    happened to be run from — green in CI, red on a maintainer's machine, for
    reasons having nothing to do with the behaviour under test.

    Copying into a plain temp dir makes "durable" a property of the FIXTURE
    rather than of the developer's checkout. Only top-level `.py` files are
    copied: that is the whole import surface `wire-statusline.py` needs
    (`_hooklib`, `hostapi`, `_gitexec`, `_durabilitylib`, `_host`), and it keeps
    the copy cheap enough to run in setUp."""
    root = os.path.join(tmpdir, "durable-plugin", "ca")
    hooks = os.path.join(root, "hooks")
    os.makedirs(hooks, exist_ok=True)
    for name in os.listdir(HOOKS):
        src = os.path.join(HOOKS, name)
        if name.endswith(".py") and os.path.isfile(src):
            with open(src, "rb") as f:
                data = f.read()
            with open(os.path.join(hooks, name), "wb") as f:
                f.write(data)
    return root


def _line(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def make_transcript(n_pairs=5, result_bytes=20000, trailing_newline=True,
                    final_assistant=True):
    """Build a realistic transcript: user prompt, then n_pairs of
    assistant(tool_use) / user(tool_result + toolUseResult), each result
    `result_bytes` of filler, optionally a final assistant text turn.
    Returns bytes."""
    big = "X" * result_bytes
    lines = [_line({"type": "user", "uuid": "u0", "parentUuid": None,
                    "sessionId": "s", "message": {"role": "user", "content": "go"}})]
    prev = "u0"
    for i in range(n_pairs):
        au, uu, tid = f"a{i}", f"ru{i}", f"toolu_{i}"
        lines.append(_line({
            "type": "assistant", "uuid": au, "parentUuid": prev, "requestId": f"r{i}",
            "sessionId": "s", "message": {"role": "assistant", "content": [
                {"type": "thinking", "thinking": "reasoning " * 50, "signature": "sig"},
                {"type": "text", "text": "running tool"},
                {"type": "tool_use", "id": tid, "name": "Bash", "input": {"command": "echo hi"}},
            ]}}))
        lines.append(_line({
            "type": "user", "uuid": uu, "parentUuid": au, "sessionId": "s",
            "toolUseResult": {"status": "ok", "exitCode": 0, "stdout": big, "prompt": big},
            "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": tid,
                 "content": [{"type": "text", "text": big}]},
            ]}}))
        prev = uu
    if final_assistant:
        lines.append(_line({
            "type": "assistant", "uuid": "afinal", "parentUuid": prev, "requestId": "rf",
            "sessionId": "s", "message": {"role": "assistant",
                                          "content": [{"type": "text", "text": "all done"}]}}))
    data = "\n".join(lines)
    if trailing_newline:
        data += "\n"
    return data.encode("utf-8")
