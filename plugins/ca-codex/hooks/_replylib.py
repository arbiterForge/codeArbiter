#!/usr/bin/env python3
# codeArbiter — forgiving, low-friction capture of authority replies.
"""Canonicalize typed authority replies and expand short reply codes.

Authority still comes only from the host's own user-input seam; this module
never confers it. It removes what hosts and keyboards add around a reply
(spacing, invisible characters, code formatting, quotes, a closing period)
and lets the user type a four-character code instead of a long token. Every
result is either the exact reply that was armed or text that cannot match
one, so the adapters, route registry and engine see nothing new.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat
import tempfile
import time
import unicodedata

REGISTRY_PARENT = Path(tempfile.gettempdir())
FORMAT = "codearbiter.reply-code/0.1.0"
CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_RE = re.compile(r"[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}")
CODE_TTL_SECONDS = 24 * 60 * 60
MAX_INPUT = 4096
ROUTES = frozenset({"approval", "prerequisite", "reconciliation"})
VERBS = frozenset({
    "approve", "approve-sprint", "satisfy-prerequisite",
    "reconcile", "reconcile-task", "reconcile-scope",
})
MODES = {"delegate": "delegate", "delegate-methods": "delegate", "approve-only": "approve-only"}
STATES = frozenset({"PENDING", "REVIEW", "BLOCKED"})
ID_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,127}")
DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−﹘﹣"), "-")
QUOTE_PAIRS = (("`", "`"), ('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"),
               ("«", "»"))
# Word positions per verb and word count: I = identifier, M = sprint mode,
# S = reconciliation state, X = secret (4-char code or long token).
GRAMMAR = {
    ("approve", 2): "X", ("approve", 3): "IX",
    ("approve-sprint", 3): "MX", ("approve-sprint", 5): "IIMX",
    ("satisfy-prerequisite", 2): "X", ("satisfy-prerequisite", 4): "IIX",
    ("reconcile", 2): "X", ("reconcile", 3): "SX",
    ("reconcile-task", 5): "IISX", ("reconcile-scope", 4): "IIX",
}
SHORT_ROUTE = {"approve": "approval", "approve-sprint": "approval",
               "satisfy-prerequisite": "prerequisite", "reconcile": "reconciliation",
               "reconcile-task": "reconciliation", "reconcile-scope": "reconciliation"}


class ReplyCodeError(RuntimeError):
    pass


def _clean(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw)
    text = "".join(ch for ch in text if ch != "­" and unicodedata.category(ch) != "Cf")
    text = " ".join(text.translate(DASHES).split())
    for _ in range(2):
        if text.startswith("```") and text.endswith("```") and len(text) >= 6:
            inner = text[3:-3].strip()
            words = inner.split(" ")
            if len(words) > 1 and words[0].lower() not in VERBS and words[1].lower() in VERBS:
                inner = " ".join(words[1:])  # a fence language tag
            text = inner.strip()
            continue
        for opening, closing in QUOTE_PAIRS:
            if len(text) >= 2 and text.startswith(opening) and text.endswith(closing):
                text = text[len(opening):-len(closing)].strip()
                break
        else:
            break
    if text.endswith((".", "!")):
        text = text[:-1].rstrip()
    return text


def canonicalize(raw):
    """Return the canonical reply for a reply-shaped prompt, else ``raw`` itself."""
    if not isinstance(raw, str) or not raw or len(raw) > MAX_INPUT:
        return raw
    text = _clean(raw)
    words = text.split(" ")
    verb = words[0].lower() if words and words[0] else ""
    if verb not in VERBS:
        return raw
    words[0] = verb
    shape = GRAMMAR.get((verb, len(words)))
    if shape is None:
        return raw
    for index, kind in enumerate(shape, start=1):
        word = words[index]
        if kind == "I" and word.isascii() and ID_RE.fullmatch(word):
            words[index] = word.upper()
        elif kind == "M":
            words[index] = MODES.get(word.lower(), word.lower()) if len(words) == 3 else word.lower()
        elif kind == "S" and word.isascii():
            words[index] = word.upper()
        elif kind == "X" and len(word) == 4 and word.isascii() and CODE_RE.fullmatch(word.upper()):
            words[index] = word.upper()
    return " ".join(words)


def looks_like_reply(raw) -> bool:
    """Whether a prompt starts with a reply verb once cleaned (a near-miss candidate)."""
    if not isinstance(raw, str) or not raw or len(raw) > MAX_INPUT:
        return False
    first = _clean(raw).split(" ", 1)[0].lower()
    return first in VERBS


def describe(raw) -> str:
    """A bounded, escaped description of a prompt for the near-miss log."""
    if not isinstance(raw, str):
        return "non-string prompt"
    digest = hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()
    head = raw[:200].encode("unicode_escape").decode("ascii")[:800]
    unusual = [f"{i}:U+{ord(ch):04X}" for i, ch in enumerate(raw[:MAX_INPUT])
               if not (32 <= ord(ch) < 127)][:40]
    return f"len={len(raw)} sha256={digest} head={head!r} nonascii={','.join(unusual)}"[:1200]


def _canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _identity(root: Path) -> dict[str, str]:
    root = Path(root).resolve(strict=True)
    info = root.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
        raise ReplyCodeError("reply code target is not a real directory")
    return {"path": str(root),
            "filesystem_id": f"{int(getattr(info, 'st_dev', 0))}:{int(getattr(info, 'st_ino', 0))}"}


def _registry() -> Path:
    namespace = f"uid-{os.getuid()}" if hasattr(os, "getuid") else "current-user"
    root = REGISTRY_PARENT.resolve(strict=True) / f"codearbiter-reply-codes-{namespace}"
    root.mkdir(mode=0o700, exist_ok=True)
    info = root.lstat()
    reparse = getattr(info, "st_file_attributes", 0) & 0x400
    if stat.S_ISLNK(info.st_mode) or reparse or not stat.S_ISDIR(info.st_mode):
        raise ReplyCodeError("reply code registry is unsafe")
    if hasattr(os, "getuid"):
        if info.st_uid != os.getuid():
            raise ReplyCodeError("reply code registry has another owner")
        os.chmod(root, 0o700)
    return root


def _key(route: str, artifact_id: str, repository: dict[str, str]) -> str:
    return _digest(_canonical({"route": route, "artifact_id": artifact_id, "repository": repository}))


def _entries(now: int | None = None):
    """Yield (path, value, live) for every intact entry."""
    now = int(time.time()) if now is None else now
    for path in _registry().glob("*.json"):
        try:
            raw = path.read_bytes()
            if len(raw) > 16384:
                continue
            value = json.loads(raw.decode("utf-8"))
            unsigned = {k: v for k, v in value.items() if k != "integrity_sha256"}
            if (value.get("format") != FORMAT
                    or value.get("integrity_sha256") != _digest(_canonical(unsigned))
                    or not isinstance(value.get("repository"), dict)):
                continue
            if _identity(Path(value["repository"].get("path", ""))) != value["repository"]:
                continue
            yield path, value, int(value.get("expires_at", 0)) > now
        except (OSError, UnicodeError, ValueError, TypeError, ReplyCodeError):
            continue


def _write(path: Path, value: dict) -> None:
    data = _canonical(value)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.stem}.", suffix=".tmp", dir=path.parent)
    try:
        try:
            view = memoryview(data)
            while view:
                written = os.write(fd, view)
                if written <= 0:
                    raise OSError("short reply-code write")
                view = view[written:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def issue_code(root, route: str, artifact_id: str, full_reply: str, *,
               names: list[str], short_prefix: list[str]) -> dict[str, str]:
    """Issue a unique four-character code expanding to ``full_reply``."""
    if route not in ROUTES or not isinstance(full_reply, str) or canonicalize(full_reply) != full_reply:
        raise ReplyCodeError("reply code request is invalid")
    repository = _identity(Path(root))
    path = _registry() / f"{_key(route, artifact_id, repository)}.json"
    live = {value.get("short_reply") for other, value, alive in _entries() if alive and other != path}
    for _ in range(64):
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
        short = " ".join([*short_prefix, code])
        if short not in live and canonicalize(short) == short:
            break
    else:
        raise ReplyCodeError("no free reply code")
    value = {"format": FORMAT, "route": route, "artifact_id": artifact_id, "repository": repository,
             "short_reply": short, "full_reply": full_reply, "names": list(names),
             "expires_at": int(time.time()) + CODE_TTL_SECONDS}
    value["integrity_sha256"] = _digest(_canonical(value))
    _write(path, value)
    return {"code": code, "short_reply": short}


def offer_code(root, route: str, artifact_id: str, full_reply: str, *,
               names: list[str], short_prefix: list[str]) -> dict[str, str]:
    """Arm-result fields for a short code; empty when one cannot be issued.

    The code is a convenience: failing to issue one never blocks arming, and
    the full reply always remains accepted."""
    try:
        issued = issue_code(root, route, artifact_id, full_reply, names=names, short_prefix=short_prefix)
    except (ReplyCodeError, OSError):
        return {}
    return {"code": issued["code"], "short_reply": issued["short_reply"]}


def retire_code(root, route: str, artifact_id: str) -> None:
    try:
        repository = _identity(Path(root))
        key = _key(route, artifact_id, repository)
    except (ReplyCodeError, OSError):
        return
    for name in (f"{key}.json", f"ask-{key}.ask"):
        try:
            (_registry() / name).unlink()
        except (FileNotFoundError, ReplyCodeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Click-to-approve through the host's own question dialog (Claude Code).
#
# The model passes an armed envelope to the host question tool unchanged. The
# host renders it and returns the user's selection; the model cannot author
# that answer. PreToolUse proves the call carried no pre-filled answer, and
# PostToolUse accepts only the exact armed Approve option for that same call.
# The result is the request's short reply, applied through the normal adapter.
# ---------------------------------------------------------------------------
ASK_FORMAT = "codearbiter.reply-ask/0.1.0"
ASK_TOOL = "AskUserQuestion"
ASK_CLEAN_TTL_SECONDS = 60 * 60
NOT_YET = "Not yet"


def _questions_sha256(questions) -> str:
    return _digest(_canonical(questions))


def ask_envelope(root, route: str, artifact_id: str, *, question: str, header: str,
                 description: str, code_fields: dict[str, str]) -> dict:
    """Arm a question-dialog envelope for an already issued short code."""
    if not code_fields.get("short_reply"):
        return {}
    label = f"Approve {code_fields['code']}"
    questions = [{
        "question": question, "header": header[:12], "multiSelect": False,
        "options": [
            {"label": label, "description": description},
            {"label": NOT_YET, "description": "Records nothing. You can still type the reply later."},
        ],
    }]
    try:
        repository = _identity(Path(root))
        value = {"format": ASK_FORMAT, "route": route, "artifact_id": artifact_id,
                 "repository": repository, "questions_sha256": _questions_sha256(questions),
                 "question": question, "label": label, "short_reply": code_fields["short_reply"],
                 "expires_at": int(time.time()) + CODE_TTL_SECONDS}
        value["integrity_sha256"] = _digest(_canonical(value))
        _write(_registry() / f"ask-{_key(route, artifact_id, repository)}.ask", value)
    except (ReplyCodeError, OSError):
        return {}
    return {"questions": questions}


def _ask_entries():
    now = int(time.time())
    for path in _registry().glob("ask-*.ask"):
        try:
            raw = path.read_bytes()
            if len(raw) > 16384:
                continue
            value = json.loads(raw.decode("utf-8"))
            unsigned = {k: v for k, v in value.items() if k != "integrity_sha256"}
            if (value.get("format") != ASK_FORMAT
                    or value.get("integrity_sha256") != _digest(_canonical(unsigned))
                    or int(value.get("expires_at", 0)) <= now
                    or _identity(Path(value["repository"]["path"])) != value["repository"]):
                continue
            yield path, value
        except (OSError, UnicodeError, ValueError, TypeError, KeyError, ReplyCodeError):
            continue


def _armed_ask(tool_input):
    questions = tool_input.get("questions") if isinstance(tool_input, dict) else None
    if not isinstance(questions, list):
        return None, None
    digest = _questions_sha256(questions)
    for path, value in _ask_entries():
        if value["questions_sha256"] == digest:
            return path, value
    return None, None


def _call_key(payload) -> str | None:
    session = payload.get("session_id")
    call = payload.get("tool_use_id")
    if not (isinstance(session, str) and session and isinstance(call, str) and call):
        return None
    return _digest(_canonical({"session": session, "call": call}))


def observe_ask_pre(payload) -> None:
    """PreToolUse: refuse an armed envelope that carries a pre-filled answer."""
    path, value = _armed_ask(payload.get("tool_input"))
    if value is None:
        return
    tool_input = payload["tool_input"]
    key = _call_key(payload)
    if key is None or set(tool_input) - {"questions", "metadata"}:
        # Pre-filled answers or unexpected fields: this request can never be
        # approved by click. The typed code still works.
        path.unlink(missing_ok=True)
        raise ReplyCodeError("an armed approval question must be passed unchanged, with no answers")
    marker = {"format": ASK_FORMAT, "call": key, "questions_sha256": value["questions_sha256"],
              "expires_at": int(time.time()) + ASK_CLEAN_TTL_SECONDS}
    marker["integrity_sha256"] = _digest(_canonical(marker))
    _write(_registry() / f"call-{key}.clean", marker)


def observe_ask_post(payload) -> dict | None:
    """PostToolUse: the armed short reply and its repository when the user chose Approve."""
    path, value = _armed_ask(payload.get("tool_input"))
    if value is None:
        return None
    key = _call_key(payload)
    if key is None:
        return None
    marker_path = _registry() / f"call-{key}.clean"
    try:
        marker = json.loads(marker_path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    finally:
        marker_path.unlink(missing_ok=True)
    unsigned = {k: v for k, v in marker.items() if k != "integrity_sha256"}
    if (marker.get("integrity_sha256") != _digest(_canonical(unsigned))
            or marker.get("questions_sha256") != value["questions_sha256"]
            or int(marker.get("expires_at", 0)) <= int(time.time())):
        return None
    response = payload.get("tool_response")
    answers = response.get("answers") if isinstance(response, dict) else None
    if not isinstance(answers, dict) or answers.get(value["question"]) != value["label"]:
        return None
    path.unlink(missing_ok=True)
    return {"root": value["repository"]["path"], "route": value["route"], "prompt": value["short_reply"]}


def _short_form(canonical: str):
    """Split a canonical short reply into (lookup key, named IDs, stated mode/state) or None."""
    words = canonical.split(" ")
    shape = GRAMMAR.get((words[0], len(words))) if words else None
    if not shape or not CODE_RE.fullmatch(words[-1]):
        return None
    verb = words[0]
    names = [w for w, kind in zip(words[1:], shape) if kind == "I"]
    stated = [w for w, kind in zip(words[1:], shape) if kind in "MS"]
    if verb == "approve-sprint" and len(words) == 5:
        stated = [MODES.get(stated[0], stated[0])]
    prefix = {"reconcile-task": "reconcile", "reconcile-scope": "reconcile"}.get(verb, verb)
    return " ".join([prefix, *stated, words[-1]]), names, stated


DIAGNOSTICS = Path(".codearbiter/.markers/reply-diagnostics.log")
DIAGNOSTICS_CAP = 256 * 1024


def prepare(raw, route: str) -> dict[str, object]:
    """The text an adapter should match, plus a notice owned by ``route``.

    ``attempted`` is true when the prompt is reply-shaped for this route, so
    the adapter reports a miss instead of staying silent.
    """
    canonical = canonicalize(raw)
    first = canonical.split(" ", 1)[0] if isinstance(canonical, str) and canonical is not raw else ""
    if not first and looks_like_reply(raw):
        first = _clean(raw).split(" ", 1)[0].lower()
    mine = SHORT_ROUTE.get(first) == route
    expanded = expand(canonical) if mine else {"text": canonical, "notice": ""}
    return {"text": expanded["text"], "notice": expanded["notice"] if mine else "", "attempted": mine}


def miss_notice(example: str) -> str:
    return (f"codeArbiter: that reply did not match an armed request. Send only the reply line, "
            f"for example `{example}`; nothing else in the message.")


def record_near_miss(root, raw, reason: str) -> None:
    """Append one bounded, escaped line for a reply-shaped prompt that missed."""
    try:
        state = Path(root) / ".codearbiter"
        if not (state / "CONTEXT.md").is_file():
            return
        markers = state / ".markers"
        markers.mkdir(exist_ok=True)
        path = markers / DIAGNOSTICS.name
        if path.is_symlink() or (path.exists() and path.stat().st_size > DIAGNOSTICS_CAP):
            return
        line = f"{int(time.time())} {reason[:120]} {describe(raw)}\n"
        with open(path, "a", encoding="ascii", errors="backslashreplace") as stream:
            stream.write(line)
    except OSError:
        pass


def expand(canonical: str) -> dict[str, str]:
    """Expand a canonical short reply to its exact armed full reply."""
    if not isinstance(canonical, str):
        return {"text": canonical, "notice": ""}
    parsed = _short_form(canonical)
    if parsed is None:
        return {"text": canonical, "notice": ""}
    key, names, _stated = parsed
    code = key.rsplit(" ", 1)[-1]
    candidates = [(value, alive) for _path, value, alive in _entries()
                  if value.get("short_reply", "").rsplit(" ", 1)[-1] == code
                  and value.get("route") == SHORT_ROUTE[canonical.split(" ")[0]]]
    if not candidates:
        return {"text": canonical, "notice": f"codeArbiter: reply code {code} matches no armed request."}
    exact = [(value, alive) for value, alive in candidates if value.get("short_reply") == key]
    if not exact:
        expected = candidates[0][0].get("short_reply")
        return {"text": canonical,
                "notice": f"codeArbiter: reply code {code} was armed as `{expected}`; resend exactly that."}
    value, alive = exact[0]
    if not alive:
        return {"text": canonical, "notice": f"codeArbiter: reply code {code} has expired; ask for a new one."}
    if names and names != value.get("names", [])[:len(names)] and names != value.get("names", []):
        return {"text": canonical,
                "notice": (f"codeArbiter: reply code {code} belongs to {' '.join(value.get('names', []))}, "
                           f"not {' '.join(names)}.")}
    return {"text": value["full_reply"], "notice": ""}
