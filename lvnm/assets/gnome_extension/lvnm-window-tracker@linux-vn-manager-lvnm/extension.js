import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';

import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const SERVICE_NAME = 'io.github.uunniiblog.lvnm.GnomeWindowTracker';
const OBJECT_PATH = '/io/github/uunniiblog/lvnm/GnomeWindowTracker';

const INTERFACE_XML = `
<node>
  <interface name="io.github.uunniiblog.lvnm.GnomeWindowTracker">
    <method name="Ping">
      <arg name="protocol_version" type="u" direction="out"/>
    </method>
    <method name="GetSnapshot">
      <arg name="snapshot" type="s" direction="out"/>
    </method>
  </interface>
</node>`;

const PROTOCOL_VERSION = 1;
const MINIMUM_WINDOW_SIZE = 100;

function isTrackableWindow(window) {
    if (!window || window.is_override_redirect())
        return false;

    const type = window.get_window_type();
    if (type !== Meta.WindowType.NORMAL &&
        type !== Meta.WindowType.DIALOG &&
        type !== Meta.WindowType.MODAL_DIALOG &&
        type !== Meta.WindowType.UTILITY)
        return false;

    const rect = window.get_frame_rect();
    return rect.width >= MINIMUM_WINDOW_SIZE &&
        rect.height >= MINIMUM_WINDOW_SIZE;
}

class WindowTrackerService {
    Ping() {
        return PROTOCOL_VERSION;
    }

    GetSnapshot() {
        const focusWindow = global.display.get_focus_window();
        const appTracker = Shell.WindowTracker.get_default();
        const windows = {};

        for (const window of global.display.list_all_windows()) {
            try {
                if (!isTrackableWindow(window))
                    continue;

                const id = String(window.get_id());
                const app = appTracker.get_window_app(window);
                const rect = window.get_frame_rect();

                windows[id] = {
                    id,
                    pid: Number(window.get_pid() || 0),
                    title: window.get_title() || 'Unknown',
                    wm_class: window.get_wm_class() || '',
                    app_id: app?.get_id() ||
                        window.get_gtk_application_id() ||
                        window.get_sandboxed_app_id() || '',
                    client_type: Number(window.get_client_type()),
                    width: rect.width,
                    height: rect.height,
                    has_focus: window === focusWindow,
                };
            } catch (error) {
                console.warn(`LVNM Window Tracker: failed to inspect a window: ${error}`);
            }
        }

        return JSON.stringify({
            version: PROTOCOL_VERSION,
            active_window_id: focusWindow ? String(focusWindow.get_id()) : null,
            windows,
        });
    }
}

export default class LvnmWindowTrackerExtension extends Extension {
    enable() {
        this._enabled = true;
        this._ownerId = Gio.bus_own_name(
            Gio.BusType.SESSION,
            SERVICE_NAME,
            Gio.BusNameOwnerFlags.NONE,
            connection => {
                if (!this._enabled)
                    return;

                this._dbusObject = Gio.DBusExportedObject.wrapJSObject(
                    INTERFACE_XML,
                    new WindowTrackerService()
                );
                this._dbusObject.export(connection, OBJECT_PATH);
            },
            null,
            (_connection, name) => {
                if (this._enabled)
                    console.error(`LVNM Window Tracker could not own D-Bus name ${name}`);
            }
        );
    }

    disable() {
        this._enabled = false;

        if (this._dbusObject) {
            this._dbusObject.unexport();
            this._dbusObject = null;
        }

        if (this._ownerId) {
            Gio.bus_unown_name(this._ownerId);
            this._ownerId = 0;
        }
    }
}
