#!/usr/bin/env bash
# Builds io.github.uunniiblog.lvnm and exports it as a single .flatpak bundle
# that can be copied to other machines. Nothing is installed locally for the app.
#
# Usage: ./build-flatpak-bundle.sh [output-file]
#   Default output: <repo_root>/dist/lvnm.flatpak
#   BRANCH=<name> overrides the branch (default: master)
set -euo pipefail

app_id="io.github.uunniiblog.lvnm"
branch="${BRANCH:-master}"

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="$repo_root/flatpak/$app_id.yml"
build_dir="$repo_root/flatpak-build"
ostree_repo="$repo_root/flatpak-repo"
output="${1:-$repo_root/flatpak/dist/lvnm.flatpak}"

if ! command -v flatpak >/dev/null; then
    echo "Flatpak is required. Install it with your distribution's package manager." >&2
    exit 1
fi

if ! flatpak remotes --user --columns=name | grep -qx 'flathub'; then
    flatpak remote-add --user flathub https://dl.flathub.org/repo/flathub.flatpakrepo
fi

ensure_ref() {
    local ref=$1
    if ! flatpak info "$ref" >/dev/null 2>&1; then
        flatpak install --user --noninteractive -y flathub "$ref"
    fi
}

if command -v flatpak-builder >/dev/null; then
    builder=(flatpak-builder)
else
    echo "flatpak-builder is not installed; using org.flatpak.Builder from Flathub."
    ensure_ref org.flatpak.Builder
    builder=(flatpak run org.flatpak.Builder)
fi

# Only what is needed to *build*. Runtime extensions (GL32, codecs, gamescope
# layer, ...) are not required to produce a bundle.
ensure_ref org.kde.Platform//6.11
ensure_ref org.kde.Sdk//6.11
ensure_ref io.qt.PySide.BaseApp//6.11

mkdir -p "$(dirname "$output")"

# Build and commit into a local OSTree repo (no --install).
"${builder[@]}" \
    --user \
    --force-clean \
    --default-branch="$branch" \
    --repo="$ostree_repo" \
    --install-deps-from=flathub \
    "$build_dir" \
    "$manifest"

# Export the single-file bundle. --runtime-repo lets the target machine
# automatically fetch the required runtimes from Flathub when installing.
rm -f "$output"
flatpak build-bundle \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo \
    "$ostree_repo" \
    "$output" \
    "$app_id" \
    "$branch"

echo
echo "Bundle created: $output"
echo
echo "On the target machine (needs internet access for runtimes on first install):"
echo "  flatpak install --user $(basename "$output")"
echo "  flatpak run $app_id"