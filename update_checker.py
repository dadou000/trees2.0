import re
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import bpy


REPOSITORY_URL = "https://github.com/dadou000/trees2.0"
MANIFEST_URL = "https://raw.githubusercontent.com/dadou000/trees2.0/main/blender_manifest.toml"
DOWNLOAD_URL = "https://github.com/dadou000/trees2.0/archive/refs/heads/main.zip"
CHECK_INTERVAL_SECONDS = 15 * 60
REQUEST_TIMEOUT_SECONDS = 6
FALLBACK_INSTALLED_VERSION = (0, 3, 4)

_STATE_LOCK = threading.Lock()
_STATE = {
    "status": "IDLE",
    "checking": False,
    "latest_version": None,
    "message": "Update check has not run yet",
    "last_checked": 0.0,
}

_VERSION_RE = re.compile(
    r'^\s*version\s*=\s*"(\d+)\.(\d+)\.(\d+)"\s*$',
    re.MULTILINE,
)


def _parse_version(text):
    match = _VERSION_RE.search(text)
    if not match:
        raise ValueError("Could not find version in remote blender_manifest.toml")
    return tuple(int(part) for part in match.groups())


def _version_text(version):
    if not version:
        return "unknown"
    return ".".join(str(int(part)) for part in version)


def installed_version():
    """Read the installed extension version from its local manifest."""
    try:
        manifest = Path(__file__).with_name("blender_manifest.toml").read_text(encoding="utf-8")
        return _parse_version(manifest)
    except Exception:
        return FALLBACK_INSTALLED_VERSION


def _set_state(**changes):
    with _STATE_LOCK:
        _STATE.update(changes)


def state_snapshot():
    with _STATE_LOCK:
        return dict(_STATE)


def _online_access_allowed():
    return bool(getattr(bpy.app, "online_access", True))


def _check_worker(installed):
    try:
        request = urllib.request.Request(
            MANIFEST_URL,
            headers={
                "User-Agent": f"Trees2-Blender/{_version_text(installed)}",
                "Accept": "text/plain",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            remote_manifest = response.read().decode("utf-8", errors="replace")

        latest = _parse_version(remote_manifest)
        if latest > installed:
            status = "UPDATE_AVAILABLE"
            message = f"Trees 2.0 v{_version_text(latest)} is available"
        elif latest == installed:
            status = "UP_TO_DATE"
            message = f"Trees 2.0 v{_version_text(installed)} is up to date"
        else:
            status = "LOCAL_AHEAD"
            message = (
                f"Installed v{_version_text(installed)} is newer than "
                f"GitHub v{_version_text(latest)}"
            )

        _set_state(
            status=status,
            checking=False,
            latest_version=latest,
            message=message,
            last_checked=time.time(),
        )
    except urllib.error.HTTPError as exc:
        _set_state(
            status="ERROR",
            checking=False,
            message=f"GitHub update check failed: HTTP {exc.code}",
            last_checked=time.time(),
        )
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        _set_state(
            status="ERROR",
            checking=False,
            message=f"GitHub update check failed: {reason}",
            last_checked=time.time(),
        )
    except Exception as exc:
        _set_state(
            status="ERROR",
            checking=False,
            message=f"Update check failed: {exc}",
            last_checked=time.time(),
        )


def request_check(force=False):
    """Start a non-blocking GitHub version check.

    Returns True when a new worker was started, False when the request was
    skipped because Blender is offline, a check is already running, or the
    cached result is still fresh.
    """
    if not _online_access_allowed():
        _set_state(
            status="OFFLINE",
            checking=False,
            message="Blender online access is disabled",
        )
        return False

    state = state_snapshot()
    if state["checking"]:
        return False
    if (
        not force
        and state["last_checked"]
        and time.time() - state["last_checked"] < CHECK_INTERVAL_SECONDS
    ):
        return False

    installed = installed_version()
    _set_state(
        status="CHECKING",
        checking=True,
        message="Checking GitHub for updates...",
    )
    worker = threading.Thread(
        target=_check_worker,
        args=(installed,),
        name="Trees2UpdateCheck",
        daemon=True,
    )
    worker.start()
    return True


def _startup_check_timer():
    request_check(force=False)
    return None


class TREES2_OT_CheckForUpdates(bpy.types.Operator):
    bl_idname = "trees2.check_for_updates"
    bl_label = "Check for Updates"
    bl_description = "Check the Trees 2.0 GitHub repository for a newer version"

    def execute(self, context):
        if not _online_access_allowed():
            self.report(
                {"WARNING"},
                "Blender online access is disabled; enable Allow Online Access in Preferences",
            )
            _set_state(
                status="OFFLINE",
                checking=False,
                message="Blender online access is disabled",
            )
            return {"CANCELLED"}

        started = request_check(force=True)
        if started:
            self.report({"INFO"}, "Checking GitHub for Trees 2.0 updates")
        return {"FINISHED"}


class TREES2_OT_OpenUpdatePage(bpy.types.Operator):
    bl_idname = "trees2.open_update_page"
    bl_label = "Open GitHub"
    bl_description = "Open the Trees 2.0 GitHub repository in your web browser"

    def execute(self, context):
        webbrowser.open(REPOSITORY_URL)
        return {"FINISHED"}


class TREES2_OT_DownloadLatest(bpy.types.Operator):
    bl_idname = "trees2.download_latest"
    bl_label = "Download Latest"
    bl_description = "Open the GitHub download for the latest main-branch source ZIP"

    def execute(self, context):
        webbrowser.open(DOWNLOAD_URL)
        return {"FINISHED"}


class TREES2_PT_UpdateStatus(bpy.types.Panel):
    bl_label = "Updates"
    bl_idname = "TREES2_PT_update_status"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Trees 2.0"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        installed = installed_version()
        state = state_snapshot()

        row = layout.row()
        row.label(text=f"Installed: v{_version_text(installed)}")

        if not _online_access_allowed():
            box = layout.box()
            box.alert = True
            box.label(text="Online access disabled", icon="ERROR")
            box.label(text="Enable Allow Online Access in Preferences")
        elif state["checking"] or state["status"] == "CHECKING":
            layout.label(text="Checking GitHub...", icon="TIME")
        elif state["status"] == "UPDATE_AVAILABLE":
            latest = _version_text(state["latest_version"])
            box = layout.box()
            box.alert = True
            box.label(text=f"Update available: v{latest}", icon="IMPORT")
            row = box.row(align=True)
            row.operator("trees2.download_latest", icon="URL")
            row.operator("trees2.open_update_page", icon="URL")
        elif state["status"] == "UP_TO_DATE":
            latest = _version_text(state["latest_version"])
            layout.label(text=f"Up to date: v{latest}", icon="CHECKMARK")
        elif state["status"] == "LOCAL_AHEAD":
            layout.label(text="Development build newer than GitHub", icon="INFO")
        elif state["status"] == "ERROR":
            box = layout.box()
            box.alert = True
            box.label(text="Update check failed", icon="ERROR")
            box.label(text=state["message"][:90])
        else:
            layout.label(text="GitHub has not been checked yet", icon="INFO")

        row = layout.row(align=True)
        row.operator("trees2.check_for_updates", icon="FILE_REFRESH")
        row.operator("trees2.open_update_page", text="GitHub", icon="URL")


CLASSES = (
    TREES2_OT_CheckForUpdates,
    TREES2_OT_OpenUpdatePage,
    TREES2_OT_DownloadLatest,
    TREES2_PT_UpdateStatus,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    # Delay the automatic request until Blender has completed add-on startup.
    if not bpy.app.background and not bpy.app.timers.is_registered(_startup_check_timer):
        bpy.app.timers.register(_startup_check_timer, first_interval=2.5, persistent=False)


def unregister():
    if bpy.app.timers.is_registered(_startup_check_timer):
        bpy.app.timers.unregister(_startup_check_timer)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
