#!/bin/sh
# Fetch just the files tools/build_lite.py reads out of the caesium repo.
# Sparse and blobless: the site's history and img/games/** are large, and the
# bundle only needs these ten files. The action runs this too, so a local build
# and a CI build read exactly the same sources.
#
# caesium is private: locally this leans on whatever credentials git already has,
# in CI set GH_TOKEN to a token with read access to it.
#
# Patterns go in on stdin rather than argv because git bash rewrites leading-slash
# arguments into windows paths, which silently checks out nothing.
set -eu

repo="${1:-https://github.com/gays-studio/caesium.git}"
ref="${2:-main}"
dest="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/src"

# token goes in the clone URL, which lands in src/.git/config's remote, so the
# lazy blob fetches a blobless clone makes during checkout are authenticated too.
# git bash's path rewriting skips URLs, so unlike the old --config argument this
# needs no ARG_CONV_EXCL sparing.
if [ -n "${GH_TOKEN:-}" ]; then
  repo="https://x-access-token:${GH_TOKEN}@${repo#https://}"
elif [ -n "${CI:-}" ]; then
  # An actions secret that does not reach the job expands to an empty string
  # rather than failing the step, so without this the clone runs with no
  # credentials at all and dies on git's username prompt, which says nothing
  # about the real problem.
  cat >&2 <<'MSG'
fetch_src.sh: GH_TOKEN is empty, so secrets.GH_TOKEN never reached this job.
Check, in order:
  * the secret sits under Settings > Secrets and variables > Actions, on the
    "Repository secrets" tab. Not the Variables tab beside it, which the
    workflow would have to read as vars.GH_TOKEN, and not the Dependabot or
    Codespaces tabs, which are separate stores Actions cannot see.
  * it is not scoped to an environment. This job declares no environment, so
    environment secrets stay invisible to it.
  * the run started after the secret was saved. Secrets are read when the job
    starts, so an older run keeps failing until you re-run it.
  * the run is not from a fork. Fork-triggered runs are handed no secrets
    besides GITHUB_TOKEN.
Once the token arrives it still needs read access to gays-studio/caesium:
Contents: Read-only if it is a fine-grained PAT, the repo scope if classic.
MSG
  exit 1
fi

rm -rf "$dest"
git clone --depth 1 --branch "$ref" --filter=blob:none --sparse "$repo" "$dest"
git -C "$dest" sparse-checkout set --no-cone --stdin <<'PATTERNS'
/index.html
/credits.html
/comic.cur
/css/styles.css
/js/loader.js
/js/iframe.js
/fonts/main.ttf
/fonts/bold.ttf
/img/cube-459.png
/img/bg.jpg
PATTERNS

echo "sources at $(git -C "$dest" rev-parse --short HEAD):"
find "$dest" -type f -not -path '*/.git/*' | sed "s|^$dest/|  |" | sort
