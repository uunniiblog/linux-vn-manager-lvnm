#!/bin/sh
set -eu

# Flatpak redirects XDG paths to ~/.var/app/<app-id>. linux-rt-upscaler is
# also commonly installed with pipx, so use the host XDG paths to share its
# config.yaml, gui-config.yaml, cache and state with that installation.
export XDG_CONFIG_HOME="${HOST_XDG_CONFIG_HOME:-${HOME}/.config}"
export XDG_DATA_HOME="${HOST_XDG_DATA_HOME:-${HOME}/.local/share}"
export XDG_CACHE_HOME="${HOST_XDG_CACHE_HOME:-${HOME}/.cache}"
export XDG_STATE_HOME="${HOST_XDG_STATE_HOME:-${HOME}/.local/state}"

case "${0##*/}" in
    upscale-gui)
        exec /app/libexec/linux-rt-upscaler/upscale-gui "$@"
        ;;
    *)
        exec /app/libexec/linux-rt-upscaler/upscale "$@"
        ;;
esac
