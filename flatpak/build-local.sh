#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="$repo_root/flatpak/io.github.uunniiblog.lvnm.yml"

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

ensure_ref org.kde.Platform//6.11
ensure_ref org.kde.Sdk//6.11
ensure_ref io.qt.PySide.BaseApp//6.11
ensure_ref org.freedesktop.Platform.codecs-extra//25.08-extra
ensure_ref org.freedesktop.Platform.Compat.i386//25.08
ensure_ref org.freedesktop.Platform.GL32.default//25.08
ensure_ref org.freedesktop.Platform.GL32.default//25.08-extra
ensure_ref org.freedesktop.Platform.codecs_extra.i386//25.08-extra
ensure_ref org.freedesktop.Platform.VulkanLayer.gamescope//25.08

# Mesa GL32 is installed explicitly because a locally installed application and
# its runtime extensions come from different origins. Flatpak selects another
# active GL32 implementation automatically on systems that require one.

"${builder[@]}" \
    --user \
    --force-clean \
    --install \
    --install-deps-from=flathub \
    "$repo_root/flatpak-build" \
    "$manifest"

echo
echo "Built and installed io.github.uunniiblog.lvnm. Run it with:"
echo "  flatpak run io.github.uunniiblog.lvnm"
