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
# arguments into windows paths, which silently checks out nothing. ARG_CONV_EXCL
# spares the --config argument below from the same rewriting, and nothing else:
# excluding everything would send git a dest path it resolves against the drive
# root. Both variables are ignored off windows.
set -eu
export MSYS2_ARG_CONV_EXCL='http.'

repo="${1:-https://github.com/gays-studio/caesium.git}"
ref="${2:-main}"
dest="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)/src"

# --config, unlike -c, sticks in src/.git/config, so the lazy blob fetches a
# blobless clone makes during checkout are authenticated too
set --
if [ -n "${GH_TOKEN:-}" ]; then
  basic="$(printf 'x-access-token:%s' "$GH_TOKEN" | base64 | tr -d '\n')"
  set -- --config "http.https://github.com/.extraheader=Authorization: Basic $basic"
fi

rm -rf "$dest"
git clone "$@" --depth 1 --branch "$ref" --filter=blob:none --sparse "$repo" "$dest"
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
