#!/usr/bin/env python3
"""Validate SKILL.md files against the Agent Skills spec.

Spec: https://agentskills.io/specification (checked 2026-09-02)

Written by hand on purpose: the reference validator `skills-ref` is
source-install only, is marked demonstration-only upstream, and pulls in
strictyaml. The rules below are few and stable enough to check with stdlib,
so the project keeps a zero-dependency gate it can run in CI.

Usage:
    python3 harness/tools/validate_skills.py [skills_dir ...]

Exit code 0 when every skill passes, 1 otherwise.
"""

import re
import sys
from pathlib import Path

ALLOWED_KEYS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BODY_LINE_LIMIT = 500


def split_frontmatter(text):
    """Return (frontmatter_lines, body_line_count) or raise ValueError."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("file does not start with a '---' frontmatter delimiter")
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return lines[1:i], len(lines) - i - 1
    raise ValueError("frontmatter is not closed by a second '---'")


def parse_frontmatter(fm_lines):
    """Minimal YAML subset: top-level `key: value` plus one nesting level.

    Enough for the spec's closed field set. Anything else is reported as an
    error rather than silently accepted.
    """
    fields = {}
    key = None
    for raw in fm_lines:
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith((" ", "\t")):
            if key is None:
                raise ValueError(f"indented line with no parent key: {raw!r}")
            if not isinstance(fields[key], dict):
                fields[key] = {}
            sub = raw.strip()
            if sub.startswith("- "):
                fields[key] = "<list>"
                continue
            if ":" not in sub:
                raise ValueError(f"cannot parse nested line: {raw!r}")
            k, v = sub.split(":", 1)
            fields[key][k.strip()] = v.strip()
            continue
        if ":" not in raw:
            raise ValueError(f"cannot parse line: {raw!r}")
        key, value = raw.split(":", 1)
        key = key.strip()
        fields[key] = value.strip()
    return fields


def unquote(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def check_skill(skill_dir):
    errors, warnings = [], []
    md = skill_dir / "SKILL.md"
    if not md.is_file():
        return [f"{skill_dir}: no SKILL.md"], []

    try:
        fm_lines, body_lines = split_frontmatter(md.read_text(encoding="utf-8"))
        fields = parse_frontmatter(fm_lines)
    except ValueError as exc:
        return [f"{md}: {exc}"], []

    unknown = sorted(set(fields) - ALLOWED_KEYS)
    if unknown:
        errors.append(f"{md}: top-level keys outside the spec: {', '.join(unknown)}")

    name = unquote(fields.get("name", ""))
    if not name:
        errors.append(f"{md}: missing required field 'name'")
    else:
        if len(name) > 64:
            errors.append(f"{md}: name is {len(name)} chars, limit is 64")
        if not NAME_RE.match(name):
            errors.append(f"{md}: name {name!r} must be lowercase alphanumeric with single hyphens")
        if name != skill_dir.name:
            errors.append(f"{md}: name {name!r} does not match directory {skill_dir.name!r}")

    description = unquote(fields.get("description", ""))
    if not description:
        errors.append(f"{md}: missing required field 'description'")
    elif len(description) > 1024:
        errors.append(f"{md}: description is {len(description)} chars, limit is 1024")

    compatibility = unquote(fields.get("compatibility", ""))
    if compatibility and len(compatibility) > 500:
        errors.append(f"{md}: compatibility is {len(compatibility)} chars, limit is 500")

    metadata = fields.get("metadata")
    if metadata is not None:
        if not isinstance(metadata, dict):
            errors.append(f"{md}: metadata must be a map of string keys to string values")
        else:
            for k, v in metadata.items():
                if not unquote(v):
                    errors.append(f"{md}: metadata.{k} has no scalar string value")

    if body_lines > BODY_LINE_LIMIT:
        warnings.append(f"{md}: body is {body_lines} lines, spec recommends under {BODY_LINE_LIMIT}")

    return errors, warnings


def main(argv):
    roots = [Path(a) for a in argv[1:]] or [Path(".claude/skills")]
    skills = sorted(
        {p.parent for root in roots for p in root.rglob("SKILL.md")}
    )
    if not skills:
        print(f"no SKILL.md found under: {', '.join(str(r) for r in roots)}")
        return 1

    all_errors, all_warnings = [], []
    for skill in skills:
        errors, warnings = check_skill(skill)
        all_errors += errors
        all_warnings += warnings
        status = "FAIL" if errors else ("warn" if warnings else "ok")
        print(f"[{status:>4}] {skill}")

    for w in all_warnings:
        print(f"  warning: {w}")
    for e in all_errors:
        print(f"  error:   {e}")

    print(f"\n{len(skills)} skills checked, {len(all_errors)} errors, {len(all_warnings)} warnings")
    return 1 if all_errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
