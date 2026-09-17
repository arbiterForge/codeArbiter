#!/usr/bin/env python3
"""Validate the reference artifacts with local Draft 2020-12 schemas.

Requires jsonschema and referencing in the caller's Python environment.
Does not install dependencies, access the network, or modify artifacts.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from artifact_io import load


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError as exc:
        raise SystemExit(
            "Schema validation requires jsonschema and referencing. "
            "The separate inspect_artifacts.py utility needs only Python's standard library."
        ) from exc

    root = args.directory.resolve()
    documents = {}
    registry = Registry()
    for name in ("common", "spec", "plan"):
        path = root / "schemas" / f"{name}.schema.json"
        schema = json.loads(path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
        documents[name] = schema
    for kind in ("spec", "plan"):
        model, _, _ = load(root / f"{kind}.html")
        validator = Draft202012Validator(documents[kind], registry=registry)
        errors = sorted(validator.iter_errors(model), key=lambda e: str(list(e.path)))
        if errors:
            raise SystemExit("\n".join(f"{kind}: {list(e.path)}: {e.message}" for e in errors))
    print(json.dumps({"spec": "pass", "plan": "pass", "schema_dialect": "2020-12", "network": "not used"}, indent=2))


if __name__ == "__main__":
    main()
