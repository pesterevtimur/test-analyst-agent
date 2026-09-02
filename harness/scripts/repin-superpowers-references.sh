#!/usr/bin/env bash
# Re-pin the Superpowers reference copies under harness/meta-skills/superpowers-references/.
#
# Why: the installed plugin is mutable (`claude plugin update` overwrites it).
# We keep immutable copies of the skills our own skills are derived from, so we
# can diff against upstream and cite an exact version in a skill's provenance.
#
# Usage (from repo root):
#   bash harness/scripts/repin-superpowers-references.sh
#
# After running: update MANIFEST.md and audit every local skill whose
# metadata.upstream still names the old version.

set -euo pipefail

SKILLS=(brainstorming verification-before-completion writing-skills)
CACHE="$HOME/.claude/plugins/cache/claude-plugins-official/superpowers"
DST="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/meta-skills/superpowers-references"

if [ ! -d "$CACHE" ]; then
    echo "ERROR: superpowers plugin not installed at $CACHE" >&2
    echo "Install it: claude plugin install superpowers@claude-plugins-official" >&2
    exit 1
fi

VERSION="$(ls -1 "$CACHE" | sort -V | tail -1)"
SRC="$CACHE/$VERSION/skills"
SHA="$(git ls-remote https://github.com/obra/superpowers.git "refs/tags/v$VERSION^{}" | cut -c1-8)"
TODAY="$(date +%F)"

echo "Pinning superpowers v$VERSION (${SHA:-sha unknown}) into $DST"

for s in "${SKILLS[@]}"; do
    if [ ! -d "$SRC/$s" ]; then
        echo "ERROR: $s not found in $SRC - upstream layout changed?" >&2
        exit 1
    fi
    rm -rf "${DST:?}/$s"
    cp -R "$SRC/$s" "$DST/$s"

    header="$DST/$s/.header.tmp"
    cat > "$header" <<HDR
<!-- PINNED REFERENCE - DO NOT EDIT.
     Source: obra/superpowers @ ${SHA:-unknown} (v$VERSION)
     File:   skills/$s/SKILL.md
     Pinned: $TODAY by harness/scripts/repin-superpowers-references.sh
     If you need to adapt this skill, COPY it to .claude/skills/ and modify there.
     See ../MANIFEST.md for provenance details.
-->

HDR
    cat "$header" "$DST/$s/SKILL.md" > "$DST/$s/SKILL.md.new"
    mv "$DST/$s/SKILL.md.new" "$DST/$s/SKILL.md"
    rm -f "$header"
    echo "  pinned $s ($(find "$DST/$s" -type f | wc -l) files)"
done

echo
echo "Done. Now update $DST/MANIFEST.md with version $VERSION / sha ${SHA:-unknown} / date $TODAY,"
echo "and audit every skill whose metadata.upstream names an older version."
