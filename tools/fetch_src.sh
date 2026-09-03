#!/bin/sh
# Fetch just the files tools/build_lite.py reads out of the caesium repo.
# Sparse and blobless: the site's history and img/games/** are large, and the
# bundle only needs these ten files. The action runs this too, so a local build
# and a CI build read exactly the same sources.
#
# Patterns go in on stdin rather than argv: git bash rewrites leading-slash
# arguments into windows paths, which silently checks out nothing.
set -eu

repo="${1:-https://github.com/gays-studio/caesium.git}"
ref="${2:-main}"
dest="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/src"

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
