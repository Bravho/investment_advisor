#!/bin/zsh
# Branch-based code-improvement mode for the nightly agent (PREPARED 2026-10-30, DISABLED by default).
# Safety: exits unless config/self_develop.json has code_mode_enabled=true AND approved_by/approved_at set.
# Works only in a separate git worktree on a new branch selfdev/YYYYMMDD; never merges, pushes or restarts services.
set -euo pipefail
ROOT=/Users/admin/Projects/investment_advisor
CFG=$ROOT/config/self_develop.json
PY=$ROOT/venv/bin/python
read -r ENABLED APPROVED WT PREFIX <<<"$($PY -c "import json;c=json.load(open('$CFG'));m=c.get('code_mode',{});print(str(c.get('code_mode_enabled') is True).lower(), 'yes' if c.get('approved_by') and c.get('approved_at') else 'no', m.get('worktree_dir',''), m.get('branch_prefix','selfdev/'))")"
if [[ "$ENABLED" != "true" || "$APPROVED" != "yes" ]]; then
  echo "code mode DISABLED (code_mode_enabled=$ENABLED, approved=$APPROVED) - nothing done"; exit 0
fi
BR="${PREFIX}$(date +%Y%m%d)"
cd "$ROOT"
if [[ -d "$WT" ]]; then echo "worktree $WT already exists - refusing (review/merge or move it first)"; exit 1; fi
git worktree add -b "$BR" "$WT" HEAD
echo "worktree $WT on branch $BR ready. The agent may now edit ONLY inside $WT (allowed_paths in $CFG)."
echo "After edits run checks from $CFG, then: git -C $WT -c user.name='Tho (via nightly agent)' -c user.email='bravegreatheart@gmail.com' commit -am '<summary>'"
echo "Never merge or push; Tho reviews with: git log main..$BR / git diff main...$BR"
