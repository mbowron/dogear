#!/usr/bin/env bash
# Copy recipes from this computer to the Dogear server.
#
#   tools/sync-recipes.sh             preview, then ask before changing anything
#   tools/sync-recipes.sh --yes       no question (for scripts)
#   tools/sync-recipes.sh --delete    also remove server recipes that are not here
#
# Settings (environment variables or flags):
#   DOGEAR_HOST        --host     ssh target, e.g. root@10.0.0.54       (required)
#   DOGEAR_REMOTE_DIR  --remote   recipes folder on the server   (/storage/dogear/recipes)
#   DOGEAR_SOURCE      --source   local recipes folder           (my-recipes)
#
# Only top-level *.md files are synced; subfolders are left alone on both
# sides. Before changing anything, the script checks every recipe with
# `python -m dogear check` and saves a backup of the server's folder.
# Works with the macOS default bash (3.2) and a BusyBox server (CoreELEC).

set -euo pipefail
export LC_ALL=C

HOST="${DOGEAR_HOST:-}"
REMOTE_DIR="${DOGEAR_REMOTE_DIR:-/storage/dogear/recipes}"
SOURCE="${DOGEAR_SOURCE:-}"
OWNER="${DOGEAR_OWNER:-1000:1000}"
KEEP_BACKUPS="${DOGEAR_KEEP_BACKUPS:-10}"
SSH="${DOGEAR_SSH:-ssh}"
ASSUME_YES=0
DELETE=0
SKIP_CHECK=0

usage() { sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; }
die() { printf 'sync-recipes: %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --host) HOST="$2"; shift 2 ;;
    --remote) REMOTE_DIR="$2"; shift 2 ;;
    --source) SOURCE="$2"; shift 2 ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --delete) DELETE=1; shift ;;
    --skip-check) SKIP_CHECK=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1 (see --help)" ;;
  esac
done

REPO="$(cd "$(dirname "$0")/.." && pwd)"
[ -n "$SOURCE" ] || SOURCE="$REPO/my-recipes"
[ -n "$HOST" ] || die "set DOGEAR_HOST (for example: export DOGEAR_HOST=root@10.0.0.54) or pass --host"
[ -d "$SOURCE" ] || die "recipes folder not found: $SOURCE"
case "$REMOTE_DIR" in /*) ;; *) die "--remote must be an absolute path" ;; esac

WORK="$(mktemp -d)"
CTL="$WORK/ssh-ctl"
cleanup() {
  "$SSH" -o ControlPath="$CTL" -O exit "$HOST" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

# One ssh connection for the whole run, so a password is asked for at most once.
remote() { "$SSH" -o ControlMaster=auto -o ControlPath="$CTL" -o ControlPersist=60 "$HOST" "$@"; }

if command -v sha1sum >/dev/null 2>&1; then filehash() { sha1sum "$@"; }; else filehash() { shasum -a 1 "$@"; }; fi

# --- 1. Local recipes -------------------------------------------------------

cd "$SOURCE"
: > "$WORK/local"
bad=0
for f in *.md; do
  [ -e "$f" ] || continue
  if ! printf '%s' "$f" | grep -Eq '^[a-z0-9][a-z0-9-]*\.md$'; then
    printf 'skipping %s: file names must be lowercase letters, digits and hyphens\n' "$f" >&2
    bad=1
    continue
  fi
  filehash "$f" >> "$WORK/local"
done
[ -s "$WORK/local" ] || die "no recipes in $SOURCE"
sort -k2 "$WORK/local" -o "$WORK/local"

if [ "$SKIP_CHECK" -eq 0 ]; then
  if ( cd "$REPO" && python3 -c 'import yaml' ) >/dev/null 2>&1; then
    if ! ( cd "$REPO" && python3 -m dogear check "$SOURCE" ) > "$WORK/check" 2>&1; then
      grep -v '^ok ' "$WORK/check" >&2 || true
      die "fix the recipes above first (or pass --skip-check)"
    fi
  else
    printf 'note: python3 with PyYAML not found, so recipes were not checked\n' >&2
  fi
fi

# --- 2. Server recipes ------------------------------------------------------

printf 'Connecting to %s...\n' "$HOST"
remote "mkdir -p '$REMOTE_DIR' && cd '$REMOTE_DIR' && for f in *.md; do [ -e \"\$f\" ] && sha1sum \"\$f\"; done; true" \
  > "$WORK/remote" || die "could not reach $HOST"
sort -k2 "$WORK/remote" -o "$WORK/remote"

awk '{print $2}' "$WORK/local" > "$WORK/local.names"
awk '{print $2}' "$WORK/remote" > "$WORK/remote.names"
comm -23 "$WORK/local.names" "$WORK/remote.names" > "$WORK/new"
comm -13 "$WORK/local.names" "$WORK/remote.names" > "$WORK/gone"
join -1 2 -2 2 "$WORK/local" "$WORK/remote" | awk '$2 != $3 {print $1}' > "$WORK/changed"
cat "$WORK/new" "$WORK/changed" > "$WORK/upload"

count() { wc -l < "$1" | tr -d ' '; }
n_new=$(count "$WORK/new"); n_changed=$(count "$WORK/changed"); n_gone=$(count "$WORK/gone")
n_same=$(( $(count "$WORK/local") - n_new - n_changed ))

show() { # title file
  [ -s "$2" ] || return 0
  printf '\n%s\n' "$1"
  sed 's/^/  /' "$2"
}
show "New:" "$WORK/new"
show "Changed:" "$WORK/changed"
if [ "$DELETE" -eq 1 ]; then
  show "Remove from the server:" "$WORK/gone"
else
  show "Only on the server (kept; add --delete to remove):" "$WORK/gone"
fi
printf '\n%s new, %s changed, %s unchanged' "$n_new" "$n_changed" "$n_same"
[ "$DELETE" -eq 1 ] && printf ', %s to remove' "$n_gone"
printf '.\n'

if [ "$n_new" -eq 0 ] && [ "$n_changed" -eq 0 ] && { [ "$DELETE" -eq 0 ] || [ "$n_gone" -eq 0 ]; }; then
  printf 'The server is up to date.\n'
  exit 0
fi

if [ "$ASSUME_YES" -eq 0 ]; then
  printf 'Apply these changes to %s? [y/N] ' "$HOST"
  read -r answer < /dev/tty || answer=""
  case "$answer" in y|Y|yes|YES) ;; *) printf 'Nothing changed.\n'; exit 0 ;; esac
fi

# --- 3. Back up, upload, remove ----------------------------------------------

stamp="$(date +%Y%m%d-%H%M%S)"
backups="$(dirname "$REMOTE_DIR")/backups"
remote "mkdir -p '$backups' && cd '$REMOTE_DIR' && tar -czf '$backups/recipes-$stamp.tar.gz' \$(ls *.md 2>/dev/null) 2>/dev/null; \
  ls -1t '$backups'/recipes-*.tar.gz 2>/dev/null | tail -n +$((KEEP_BACKUPS + 1)) | xargs rm -f; true" \
  || die "backup on the server failed; nothing was changed"

if [ -s "$WORK/upload" ]; then
  # tar keeps it to one connection and works without rsync on the server.
  tar -cf - $(cat "$WORK/upload") | remote "cd '$REMOTE_DIR' && tar -xf - && chown $OWNER $(tr '\n' ' ' < "$WORK/upload")" \
    || die "upload failed; the previous recipes are in $backups/recipes-$stamp.tar.gz"
fi

if [ "$DELETE" -eq 1 ] && [ -s "$WORK/gone" ]; then
  remote "cd '$REMOTE_DIR' && rm -f $(tr '\n' ' ' < "$WORK/gone")" || die "removing files failed"
fi

printf 'Done. Backup of the previous recipes: %s:%s/recipes-%s.tar.gz\n' "$HOST" "$backups" "$stamp"
printf 'Reload Dogear to see the changes.\n'
[ "$bad" -eq 0 ] || exit 2
