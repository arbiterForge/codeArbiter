#!/usr/bin/env python3
# codeArbiter — bind cross-host coverage identities before Vitest merges blobs.
# snapshot(repo, tree) -> inert provenance; normalize(inputs, expected) -> blobs/status.
# CI artifacts are data, never executable input. Only coverage schema slots change.
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

MAX_BYTES = 16 * 1024 * 1024
MAX_NODES = 1_000_000
HOSTS = frozenset(("ubuntu-latest", "windows-latest"))
TREES = frozenset(("plugins/ca/tools", "plugins/ca-pi/tools"))


def require(condition):
    if not condition:
        raise ValueError("coverage-input-invalid")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result)
        result[key] = value
    return result


def regular(path):
    path = Path(path).absolute()
    require(not any(parent.is_symlink() for parent in (path, *path.parents)))
    require(path.is_file() and path.stat().st_size <= MAX_BYTES)
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    require(len(data) <= MAX_BYTES)
    return data


def read_json(path):
    return json.loads(regular(path), object_pairs_hook=unique_pairs,
                      parse_constant=lambda _: require(False))


def git(repo, *arguments):
    result = subprocess.run(["git", "-C", str(repo), *arguments], capture_output=True, timeout=30)
    require(result.returncode == 0 and len(result.stdout) <= MAX_BYTES)
    return result.stdout


def relative_path(path):
    require(isinstance(path, str) and len(path) <= 1024)
    require(not path.startswith("/") and "\\" not in path and ":" not in path)
    require(all(part not in ("", ".", "..") for part in path.split("/")))
    require(not any(ord(char) < 32 for char in path))
    return path


def snapshot(repo, tree):
    require(tree in TREES)
    repo = Path(repo).absolute()
    require(not any(parent.is_symlink() for parent in (repo, *repo.parents)))
    repo = repo.resolve()
    require(Path(git(repo, "rev-parse", "--show-toplevel").decode().strip()).resolve() == repo.resolve())
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    require(re.fullmatch(r"[a-f0-9]{40,64}", head))
    tracked = git(repo, "ls-tree", "-r", "--name-only", head, "--", tree).decode().splitlines()
    config_paths = {f"{tree}/package.json", f"{tree}/package-lock.json", f"{tree}/vitest.config.ts"}
    config_paths.update(path for path in tracked if path.endswith((".ts", ".mjs", ".json")))
    if tree == "plugins/ca-pi/tools":
        config_paths.update(("core/hosts.json", "plugins/ca/hooks/secret-detection-corpus.json",
                             "plugins/ca-pi/extensions/codearbiter-child.js"))
    config, sources = {}, {}
    config_text = regular(repo / tree / "vitest.config.ts").decode("utf-8")
    includes = re.findall(r'\binclude\s*:\s*\[([^\]]*)\]', config_text)
    excludes = re.findall(r'\bexclude\s*:\s*\[([^\]]*)\]', config_text)
    expected_include = '["src/**/*.ts"]' if tree == "plugins/ca-pi/tools" else '["*.ts"]'
    require(len(includes) == 1 and json.loads("[" + includes[0] + "]") == json.loads(expected_include))
    require(excludes == [] if tree == "plugins/ca-pi/tools" else
            len(excludes) == 1 and json.loads("[" + excludes[0] + "]") == ["*.test.ts", "*.config.ts"])
    for path in sorted(config_paths):
        relative_path(path)
        value = regular(repo / path)
        require(value == git(repo, "show", f"{head}:{path}"))
        config[path] = digest(value)
        if path.startswith(tree + "/") and path.endswith(".ts"):
            local = path[len(tree) + 1:]
            included = local.startswith("src/") if tree == "plugins/ca-pi/tools" else (
                "/" not in local and not local.endswith((".test.ts", ".config.ts")))
            if included:
                sources[local] = digest(value)
    require(sources)
    lock = read_json(repo / tree / "package-lock.json")
    version = lock["packages"]["node_modules/vitest"]["version"]
    require(isinstance(version, str))
    return {"schema": 1, "head": head, "tree": tree, "vitest": version,
            "root": (repo / tree).as_posix(), "config": config, "sources": sources}


def decode_coverage(graph):
    require(isinstance(graph, list) and 0 < len(graph) <= MAX_NODES)
    require(isinstance(graph[0], list) and len(graph[0]) == 6)
    budget = [MAX_NODES]

    def decode(reference, ancestors=(), depth=0):
        require(isinstance(reference, str) and re.fullmatch(r"0|[1-9][0-9]*", reference))
        require(len(reference) <= 7)
        index = int(reference)
        require(index < len(graph) and index not in ancestors and depth <= 64)
        budget[0] -= 1
        require(budget[0] >= 0)
        value = graph[index]
        if isinstance(value, (dict, list)):
            ancestors = (*ancestors, index)
            def child(item):
                budget[0] -= 1
                require(budget[0] >= 0)
                require(not isinstance(item, (dict, list)))
                return decode(item, ancestors, depth + 1) if isinstance(item, str) else item
            return {key: child(item) for key, item in value.items()} if isinstance(value, dict) else [child(item) for item in value]
        return value

    coverage = decode(graph[0][3])
    version = decode(graph[0][0])
    require(isinstance(coverage, dict) and 0 < len(coverage) <= 2048)
    return coverage, version


def canonical_path(path, root, sources):
    require(isinstance(path, str) and isinstance(root, str))
    path, root = path.replace("\\", "/"), root.replace("\\", "/")
    require(re.fullmatch(r"(?:[A-Za-z]:)?/[^\x00-\x1f]+", root))
    require(not root.endswith("/") and "//" not in root)
    require(all(part not in (".", "..") for part in root.split("/")))
    require(path.startswith(root + "/"))
    suffix = relative_path(path[len(root) + 1:])
    require(suffix in sources)
    return suffix


def validate_file(value):
    require(isinstance(value, dict))
    for counts, maps in (("s", "statementMap"), ("f", "fnMap"), ("b", "branchMap")):
        require(isinstance(value.get(counts), dict) and isinstance(value.get(maps), dict))
        require(set(value[counts]) == set(value[maps]))
        for key, count in value[counts].items():
            require(re.fullmatch(r"0|[1-9][0-9]*", key))
            values = count if counts == "b" else [count]
            require(isinstance(values, list) and all(type(n) is int and abs(n) <= 2**53 - 1 for n in values))
            for index, number in enumerate(values):
                if number < 0:
                    branch = value[maps][key]
                    # ast-v8-to-istanbul computes implicit-else hits by
                    # parent-minus-consequent, which can be negative. Preserve
                    # observations only in that exact producer shape; below,
                    # normalize proves addition cannot erase a positive hit.
                    require(counts == "b" and isinstance(branch, dict) and branch.get("type") == "if"
                            and len(values) == 2 and index == 1
                            and branch.get("locations", [None, None])[1] == {"start": {}, "end": {}})
            if counts == "b":
                require(isinstance(value[maps][key], dict))
                locations = value[maps][key].get("locations")
                require(isinstance(locations, list) and len(locations) == len(values))
    def location(node):
        require(isinstance(node, dict) and "start" in node and "end" in node)
        for kind in ("start", "end"):
            point = node[kind]
            require(isinstance(point, dict) and set(point) == {"line", "column"})
            require(type(point["line"]) is int and 1 <= point["line"] <= 10_000_000)
            column = point["column"]
            # V8's open-ended Infinity column is serialized as JSON null in
            # real Vitest 4.1.9 blobs; preserve that exact end-only convention.
            require((kind == "end" and column is None) or
                    (type(column) is int and 0 <= column <= 10_000_000))
        require(node["end"]["line"] >= node["start"]["line"])
        if node["end"]["line"] == node["start"]["line"] and node["end"]["column"] is not None:
            require(node["end"]["column"] >= node["start"]["column"])
    for node in value["statementMap"].values():
        location(node)
    for node in value["fnMap"].values():
        require(isinstance(node, dict) and isinstance(node.get("name"), str))
        location(node.get("decl"))
        location(node.get("loc"))
    for node in value["branchMap"].values():
        require(isinstance(node, dict) and isinstance(node.get("type"), str))
        location(node.get("loc"))
        require(isinstance(node.get("locations"), list) and node["locations"])
        for index, point in enumerate(node["locations"]):
            # Istanbul's implicit else has no source position. Real V8 blobs
            # encode exactly the second arm of a two-arm if this way.
            if node["type"] == "if" and len(node["locations"]) == 2 and index == 1 and point == {"start": {}, "end": {}}:
                continue
            location(point)


def append_graph(graph, value):
    index = len(graph)
    require(index < MAX_NODES)
    graph.append(None)
    if isinstance(value, dict):
        graph[index] = {key: append_graph(graph, item) if isinstance(item, (dict, list, str)) else item for key, item in value.items()}
    elif isinstance(value, list):
        graph[index] = [append_graph(graph, item) if isinstance(item, (dict, list, str)) else item for item in value]
    else:
        graph[index] = value
    return str(index)


def normalize(inputs, expected):
    require(0 < len(inputs) <= len(HOSTS))
    seen, baseline, result, prior_counts = set(), None, [], {}
    for graph, proof in inputs:
        require(isinstance(proof, dict) and proof.get("host") in HOSTS and proof["host"] not in seen)
        seen.add(proof["host"])
        for field in ("schema", "head", "tree", "vitest", "config", "sources"):
            require(proof.get(field) == expected[field])
        coverage, version = decode_coverage(graph)
        require(version == expected["vitest"])
        normalized, maps, names = {}, {}, set()
        for path, value in coverage.items():
            require(isinstance(value, dict) and value.get("path") == path)
            suffix = canonical_path(path, proof.get("root"), expected["sources"])
            require(suffix.casefold() not in names)
            names.add(suffix.casefold())
            validate_file(value)
            if suffix in prior_counts:
                prior = prior_counts[suffix]
                for field in ("s", "f", "b"):
                    require(set(prior[field]) == set(value[field]))
                    for key, number in value[field].items():
                        left = prior[field][key] if field == "b" else [prior[field][key]]
                        right = number if field == "b" else [number]
                        require(len(left) == len(right))
                        for a, b in zip(left, right):
                            require(abs(a + b) <= 2**53 - 1)
                            require(((a + b) > 0) == (a > 0 or b > 0))
            prior_counts[suffix] = value
            canonical = expected["root"].replace("\\", "/") + "/" + suffix
            normalized[canonical] = {**value, "path": canonical}
            maps[suffix] = {key: value[key] for key in ("statementMap", "fnMap", "branchMap")}
        require(set(maps) == set(expected["sources"]))
        if baseline is None:
            baseline = maps
        else:
            require(maps == baseline)
        # Append a private coverage subgraph: never mutate shared string refs
        # that may also identify test modules, errors, or environment modules.
        output = copy.deepcopy(graph)
        output[0][3] = append_graph(output, normalized)
        result.append(output)
    return result, "UNION" if seen == HOSTS else "PARTIAL"


def write_new(path, value):
    path = Path(path).absolute()
    require(not any(parent.is_symlink() for parent in (path, *path.parents)))
    encoded = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= MAX_BYTES)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(encoded)


def prepare(repo, tree, host, output, check=False):
    require(host in HOSTS and output.name == f"{host}.provenance.json")
    proof = {**snapshot(repo, tree), "host": host}
    if not check:
        write_new(output, proof)
        return "PREPARED"
    require(read_json(output) == proof)
    blob = output.with_name(f"{host}.json")
    receipt = {"schema": 1, "host": host, "snapshot_sha256": digest(regular(output)),
               "blob_sha256": digest(regular(blob))}
    write_new(output.with_name(f"{host}.checked.json"), receipt)
    return "CHECKED"


def verify(repo, tree, directory, output):
    require(directory.is_dir() and not directory.is_symlink())
    require(not output.exists() and not output.is_symlink())
    entries = {path.name for path in directory.iterdir()}
    hosts = [host for host in sorted(HOSTS) if f"{host}.json" in entries]
    required = {f"{host}{suffix}" for host in hosts for suffix in (".json", ".provenance.json", ".checked.json")}
    require(entries == required and hosts)
    inputs = []
    for host in hosts:
        blob, proof = directory / f"{host}.json", directory / f"{host}.provenance.json"
        receipt = read_json(directory / f"{host}.checked.json")
        require(receipt == {"schema": 1, "host": host, "snapshot_sha256": digest(regular(proof)), "blob_sha256": digest(regular(blob))})
        provenance = read_json(proof)
        require(provenance.get("host") == host)
        inputs.append((read_json(blob), provenance))
    normalized, status = normalize(inputs, snapshot(repo, tree))
    # Complete validation and serialization before exposing any normalized blob.
    payloads = [json.dumps(graph, separators=(",", ":"), allow_nan=False).encode() for graph in normalized]
    require(all(len(payload) <= MAX_BYTES for payload in payloads))
    require(not any(parent.is_symlink() for parent in (output, *output.parents)))
    output.mkdir(parents=False, exist_ok=False)
    for host, payload in zip(hosts, payloads):
        with (output / f"{host}.json").open("xb") as stream:
            stream.write(payload)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--tree", choices=sorted(TREES), required=True)
    parser.add_argument("--host", choices=sorted(HOSTS))
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        if args.mode == "prepare":
            require(args.host is not None and args.input is None)
            status = prepare(args.repo, args.tree, args.host, args.output, args.check)
        else:
            require(args.input is not None and args.host is None and not args.check)
            status = verify(args.repo, args.tree, args.input, args.output)
        print(f"coverage-identity: {status}")
        return 0
    except (ValueError, TypeError, KeyError, IndexError, OSError, RecursionError, subprocess.SubprocessError):
        print("coverage-identity: INVALID", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
