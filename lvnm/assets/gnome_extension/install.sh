#!/bin/sh
set -eu

extension_uuid="lvnm-window-tracker@linux-vn-manager-lvnm"
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
source_dir="$script_dir/$extension_uuid"
if [ -f /.flatpak-info ]; then
    # Flatpak rewrites XDG_DATA_HOME to the app-specific directory, which
    # GNOME Shell does not scan for extensions. `--filesystem=home` gives this
    # installer access to the real per-user extension directory.
    data_home="$HOME/.local/share"
else
    data_home=${XDG_DATA_HOME:-"$HOME/.local/share"}
fi
target_dir="$data_home/gnome-shell/extensions/$extension_uuid"

run_host() {
    if [ -f /.flatpak-info ]; then
        flatpak-spawn --host "$@"
    else
        "$@"
    fi
}

update_extension_list() {
    key=$1
    action=$2
    uuid=$3
    current=$(run_host gsettings get org.gnome.shell "$key")
    updated=$(
        printf '%s' "$current" | run_host python3 -c '
import ast
import sys

raw = sys.stdin.read().strip()
if raw.startswith("@as "):
    raw = raw[4:]
values = list(ast.literal_eval(raw))
uuid = sys.argv[1]
if sys.argv[2] == "add":
    if uuid not in values:
        values.append(uuid)
else:
    values = [value for value in values if value != uuid]
print(repr(values))
' "$uuid" "$action"
    )
    run_host gsettings set org.gnome.shell "$key" "$updated"
}

if [ ! -f "$source_dir/metadata.json" ] || [ ! -f "$source_dir/extension.js" ]; then
    echo "LVNM GNOME extension files were not found in $source_dir" >&2
    exit 1
fi

mkdir -p "$target_dir"
cp "$source_dir/metadata.json" "$source_dir/extension.js" "$target_dir/"

# Keep the UUID enabled across the next GNOME Shell login even when the
# currently running Wayland shell has not discovered this new extension yet.
update_extension_list enabled-extensions add "$extension_uuid"
update_extension_list disabled-extensions remove "$extension_uuid"

if run_host gnome-extensions info "$extension_uuid" >/dev/null 2>&1; then
    run_host gnome-extensions enable "$extension_uuid" || true
fi

echo "Installed $extension_uuid in $target_dir"
echo "Log out and log back in to load a newly installed or updated extension on GNOME Wayland."
