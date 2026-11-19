"""Closed compatibility declaration shared by generation and release observation.

Validating the declaration never authorizes removing a route. Named user approval
and fresh publication evidence remain separate requirements for a future change.
"""

_REMOVAL_POLICY = {
    "minimumVersion": {"claude": "3.0.0", "codex": "1.0.0", "pi": "1.0.0"},
    "decision": "separately-approved-named-removal",
    "evidence": "fresh-exact-confirmed-non-draft-release",
}


def validate_removal_policy(value):
    if not isinstance(value, dict) or value != _REMOVAL_POLICY:
        raise ValueError("compatibility.removalRequires must declare the supported version floors, "
                         "separately approved named removal and fresh exact non-draft release evidence")
    return value


def removal_policy_text(value):
    policy = validate_removal_policy(value)
    floors = policy["minimumVersion"]
    return (
        f"ca retains these routes through every 2.x release, with no removal before a separately "
        f"approved {floors['claude']}. ca-codex and ca-pi retain them through every later 0.x release, "
        f"with no removal before a separately approved {floors['codex']} and {floors['pi']} respectively. "
        "Passing a version floor never authorizes removal: removal needs a new governed decision "
        "naming the affected route and fresh compatibility evidence for the exact confirmed "
        "non-draft release. This declaration does not approve a removal or infer publication "
        "from a version, tag or draft."
    )
