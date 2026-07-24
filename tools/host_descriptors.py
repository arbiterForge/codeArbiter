#!/usr/bin/env python3
"""Strict loader for the canonical governance-host registry.

core/hosts.json is the only host list.  This module validates it and exposes
deeply immutable descriptors to every generator and later host consumer.
"""
from dataclasses import dataclass
import json
import os
import re
import string
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class SurfaceRule:
    source_prefix: str
    output_pattern: str
    exclude: frozenset[str]
    add_skill_frontmatter: bool = False


@dataclass(frozen=True)
class PermissionPolicy:
    surfaces: Mapping[str, str]


@dataclass(frozen=True)
class HostDescriptor:
    name: str
    plugin_dir: str
    hooks_dir: str
    command_form: str
    tokens: Mapping[str, str]
    capabilities: Mapping[str, bool]
    surface_rules: tuple[SurfaceRule, ...]
    managed_subtrees: tuple[str, ...]
    catalog: str | None
    tool_classes: Mapping[str, str]
    permission_policy: PermissionPolicy | None
    package: Mapping[str, object] | None


class DescriptorError(ValueError):
    """core/hosts.json violates the strict host-descriptor schema."""


_ROOT_KEYS = frozenset({"hosts"})
_HOST_KEYS = frozenset({
    "name", "plugin_dir", "hooks_dir", "command_form", "tokens",
    "capabilities", "surface", "tool_classes", "permission_policy", "package",
})
_HOST_REQUIRED_KEYS = _HOST_KEYS - {"permission_policy"}
_SURFACE_KEYS = frozenset({"rules", "managed_subtrees", "catalog"})
_PERMISSION_POLICY_KEYS = frozenset({"surfaces"})
_RULE_KEYS = frozenset({
    "source_prefix", "output_pattern", "exclude", "add_skill_frontmatter",
})
_TOKENS = frozenset({"PLUGIN_ROOT", "PROJECT_DIR"})
_TOOL_CLASSES = frozenset({"EXEC", "WRITE", "EDIT", "READ", "OTHER"})
_PERMISSION_ACTIONS = frozenset({
    "read", "inspection", "source-write", "source-edit", "config-write",
    "config-edit", "planning-write", "shell-mutation", "dependency-change",
    "network-side-effect", "external-side-effect", "background-launch", "push",
    "release",
})
_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_PERMISSION_SURFACE_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,127}$")
_CONDITION_START = "{{IF:"
_FORMATTER = string.Formatter()


def _mapping(value, where):
    if not isinstance(value, dict):
        raise DescriptorError(f"{where}: expected an object")
    return value


def _keys(value, allowed, where, required=None):
    unknown = set(value) - set(allowed)
    missing = set(allowed if required is None else required) - set(value)
    if unknown:
        raise DescriptorError(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
    if missing:
        raise DescriptorError(f"{where}: missing key(s): {', '.join(sorted(missing))}")


def _string(value, where, allow_empty=False):
    if not isinstance(value, str) or (not allow_empty and not value):
        raise DescriptorError(f"{where}: expected a non-empty string")
    return value


def _relative_path(value, where, allow_empty=False):
    value = _string(value, where, allow_empty=allow_empty)
    if "\\" in value or os.path.isabs(value):
        raise DescriptorError(f"{where}: path must be relative POSIX form")
    parts = value.split("/")
    if any(part in ("", ".", "..") for part in parts) and not (allow_empty and value == ""):
        raise DescriptorError(f"{where}: path is empty, malformed, or escapes its root")
    return value


def _command_form(value, where):
    value = _string(value, where)
    fields = []
    try:
        for _literal, field, spec, conversion in _FORMATTER.parse(value):
            if field is not None:
                fields.append(field)
                if field != "name" or spec or conversion:
                    raise DescriptorError(f"{where}: only plain {{name}} is allowed")
    except ValueError as error:
        raise DescriptorError(f"{where}: malformed command template: {error}") from error
    if fields != ["name"]:
        raise DescriptorError(f"{where}: command template needs exactly one {{name}}")
    return value


def _output_pattern(value, where):
    value = _string(value, where)
    fields = []
    try:
        for _literal, field, spec, conversion in _FORMATTER.parse(value):
            if field is not None:
                fields.append(field)
                if field not in {"relative", "stem", "name"} or spec or conversion:
                    raise DescriptorError(
                        f"{where}: only plain {{relative}}, {{stem}}, and {{name}} are allowed"
                    )
    except ValueError as error:
        raise DescriptorError(f"{where}: malformed output pattern: {error}") from error
    rendered = value.format(relative="path/file.md", stem="file", name="file")
    _relative_path(rendered, where)
    return value


def _string_mapping(value, where, values=None):
    value = _mapping(value, where)
    out = {}
    for key, item in value.items():
        key = _string(key, f"{where} key")
        item = _string(item, f"{where}.{key}")
        if values is not None and item not in values:
            raise DescriptorError(f"{where}.{key}: noncanonical value {item!r}")
        out[key] = item
    return MappingProxyType(out)


def _bool_mapping(value, where):
    value = _mapping(value, where)
    out = {}
    for key, item in value.items():
        key = _string(key, f"{where} key")
        if type(item) is not bool:
            raise DescriptorError(f"{where}.{key}: expected true or false")
        out[key] = item
    return MappingProxyType(out)


def _freeze(value, where):
    if isinstance(value, dict):
        return MappingProxyType({str(key): _freeze(item, f"{where}.{key}")
                                 for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item, where) for item in value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise DescriptorError(f"{where}: unsupported JSON value")


def _permission_policy(value, where):
    value = _mapping(value, where)
    _keys(value, _PERMISSION_POLICY_KEYS, where)
    surfaces = _mapping(value["surfaces"], f"{where}.surfaces")
    validated = {}
    for name, action in surfaces.items():
        if not isinstance(name, str) or not _PERMISSION_SURFACE_NAME.fullmatch(name):
            raise DescriptorError(
                f"{where}.surfaces: names must be bounded lowercase surface identifiers"
            )
        action = _string(action, f"{where}.surfaces.{name}")
        if action not in _PERMISSION_ACTIONS:
            raise DescriptorError(
                f"{where}.surfaces.{name}: noncanonical permission action {action!r}"
            )
        validated[name] = action
    return PermissionPolicy(surfaces=MappingProxyType(validated))


def _rule(value, where):
    value = _mapping(value, where)
    _keys(value, _RULE_KEYS, where,
          required={"source_prefix", "output_pattern", "exclude"})
    prefix = _string(value["source_prefix"], f"{where}.source_prefix")
    trailing_slash = prefix.endswith("/")
    _relative_path(prefix[:-1] if trailing_slash else prefix,
                   f"{where}.source_prefix")
    excluded = value["exclude"]
    if not isinstance(excluded, list) or not all(isinstance(item, str) for item in excluded):
        raise DescriptorError(f"{where}.exclude: expected a string array")
    excluded = frozenset(_relative_path(item, f"{where}.exclude") for item in excluded)
    add_frontmatter = value.get("add_skill_frontmatter", False)
    if type(add_frontmatter) is not bool:
        raise DescriptorError(f"{where}.add_skill_frontmatter: expected true or false")
    return SurfaceRule(
        source_prefix=prefix,
        output_pattern=_output_pattern(value["output_pattern"], f"{where}.output_pattern"),
        exclude=excluded,
        add_skill_frontmatter=add_frontmatter,
    )


def _host(value, index):
    where = f"hosts[{index}]"
    value = _mapping(value, where)
    _keys(value, _HOST_KEYS, where, required=_HOST_REQUIRED_KEYS)
    name = _string(value["name"], f"{where}.name")
    if not _NAME.fullmatch(name):
        raise DescriptorError(f"{where}.name: expected lowercase host slug")
    surface = _mapping(value["surface"], f"{where}.surface")
    _keys(surface, _SURFACE_KEYS, f"{where}.surface")
    rules = surface["rules"]
    if not isinstance(rules, list) or not rules:
        raise DescriptorError(f"{where}.surface.rules: expected a non-empty array")
    managed = surface["managed_subtrees"]
    if not isinstance(managed, list) or not managed:
        raise DescriptorError(f"{where}.surface.managed_subtrees: expected a non-empty array")
    managed = tuple(_relative_path(item, f"{where}.surface.managed_subtrees")
                    for item in managed)
    if len(set(managed)) != len(managed):
        raise DescriptorError(f"{where}.surface.managed_subtrees: duplicate path")
    catalog = surface["catalog"]
    if catalog is not None:
        catalog = _relative_path(catalog, f"{where}.surface.catalog")
    tokens = _string_mapping(value["tokens"], f"{where}.tokens")
    if frozenset(tokens) != _TOKENS:
        raise DescriptorError(f"{where}.tokens: keys must be PLUGIN_ROOT and PROJECT_DIR")
    package = value["package"]
    if package is not None:
        package = _freeze(_mapping(package, f"{where}.package"), f"{where}.package")
    permission_policy = value.get("permission_policy")
    if permission_policy is not None:
        permission_policy = _permission_policy(
            permission_policy, f"{where}.permission_policy"
        )
    return HostDescriptor(
        name=name,
        plugin_dir=_relative_path(value["plugin_dir"], f"{where}.plugin_dir"),
        hooks_dir=_relative_path(value["hooks_dir"], f"{where}.hooks_dir"),
        command_form=_command_form(value["command_form"], f"{where}.command_form"),
        tokens=tokens,
        capabilities=_bool_mapping(value["capabilities"], f"{where}.capabilities"),
        surface_rules=tuple(_rule(rule, f"{where}.surface.rules[{number}]")
                            for number, rule in enumerate(rules)),
        managed_subtrees=managed,
        catalog=catalog,
        tool_classes=_string_mapping(
            value["tool_classes"], f"{where}.tool_classes", _TOOL_CLASSES
        ),
        permission_policy=permission_policy,
        package=package,
    )


def _validate_condition_tags(repo, names):
    surface = os.path.join(repo, "core", "surface")
    if not os.path.isdir(surface):
        return
    for dirpath, dirnames, filenames in os.walk(surface):
        dirnames.sort()
        for filename in sorted(filenames):
            path = os.path.join(dirpath, filename)
            try:
                with open(path, encoding="utf-8") as stream:
                    text = stream.read()
            except (OSError, UnicodeError) as error:
                raise DescriptorError(f"{path}: cannot scan condition tags: {error}") from error
            start = text.find(_CONDITION_START)
            while start >= 0:
                tag_start = start + len(_CONDITION_START)
                end = text.find("}}", tag_start)
                if end < 0:
                    raise DescriptorError(
                        f"{path}: malformed host condition token at offset {start}"
                    )
                tag = text[tag_start:end]
                if not _NAME.fullmatch(tag):
                    raise DescriptorError(
                        f"{path}: malformed host condition tag {tag!r}"
                    )
                if tag not in names:
                    raise DescriptorError(f"{path}: unknown host condition tag {tag!r}")
                start = text.find(_CONDITION_START, end + 2)


def load_host_descriptors(repo: str) -> tuple[HostDescriptor, ...]:
    """Load and fully validate core/hosts.json below `repo`."""
    path = os.path.join(os.fspath(repo), "core", "hosts.json")
    try:
        with open(path, encoding="utf-8") as stream:
            document = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DescriptorError(f"{path}: cannot load host descriptors: {error}") from error
    document = _mapping(document, "root")
    _keys(document, _ROOT_KEYS, "root")
    values = document["hosts"]
    if not isinstance(values, list) or not values:
        raise DescriptorError("root.hosts: expected a non-empty array")
    hosts = tuple(_host(value, index) for index, value in enumerate(values))
    for attribute in ("name", "plugin_dir", "hooks_dir"):
        seen = set()
        for host in hosts:
            value = getattr(host, attribute)
            if value in seen:
                raise DescriptorError(f"hosts: duplicate {attribute} {value!r}")
            seen.add(value)
    names = {host.name for host in hosts}
    _validate_condition_tags(os.fspath(repo), names)
    return hosts


def host_descriptor(name: str, repo: str) -> HostDescriptor:
    """Return one named host descriptor or raise DescriptorError."""
    for host in load_host_descriptors(repo):
        if host.name == name:
            return host
    raise DescriptorError(f"unknown host {name!r}")
