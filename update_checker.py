import io
import re
import shutil
import tempfile
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from pathlib import Path, PurePosixPath

import bpy


REPOSITORY_URL = "https://github.com/dadou000/trees2.0"
MANIFEST_URL = "https://raw.githubusercontent.com/dadou000/trees2.0/main/blender_manifest.toml"
DOWNLOAD_URL = "https://github.com/dadou000/trees2.0/archive/refs/heads/main.zip"
CHECK_INTERVAL_SECONDS = 15 * 60
REQUEST_TIMEOUT_SECONDS = 10
MAX_DOWNLOAD_BYTES = 128 * 1024 * 1024
PACKAGE_ID = "trees2"
FALLBACK_INSTALLED_VERSION = (0, 4, 1)

_STATE_LOCK = threading.Lock()
_STATE = {
    "status": "IDLE",
    "checking": False,
    "updating": False,
    "latest_version": None,
    "message": "Update check has not run yet",
    "last_checked": 0.0,
    "update_ready_path": None,
    "update_temp_dir": None,
    "update_target_version": None,
}

_VERSION_RE = re.compile(
    r'^\s*version\s*=\s*"(\d+)\.(\d+)\.(\d+)"\s*$',
    re.MULTILINE,
)
_ID_RE = re.compile(r'^\s*id\s*=\s*"([^\"]+)"\s*$', re.MULTILINE)


def _parse_version(text):
    match = _VERSION_RE.search(text)
    if not match:
        raise ValueError("Could not find version in blender_manifest.toml")
    return tuple(int(part) for part in match.groups())


def _parse_package_id(text):
    match = _ID_RE.search(text)
    if not match:
        raise ValueError("Could not find id in blender_manifest.toml")
    return match.group(1).strip()


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


def _request_bytes(url, installed):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"Trees2-Blender/{_version_text(installed)}",
            "Accept": "application/octet-stream, text/plain;q=0.9, */*;q=0.8",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        length = response.headers.get("Content-Length")
        if length and int(length) > MAX_DOWNLOAD_BYTES:
            raise ValueError("GitHub update archive is unexpectedly large")
        payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise ValueError("GitHub update archive exceeded the safety limit")
    return payload


def _check_worker(installed):
    try:
        remote_manifest = _request_bytes(MANIFEST_URL, installed).decode("utf-8", errors="replace")
        latest = _parse_version(remote_manifest)
        if _parse_package_id(remote_manifest) != PACKAGE_ID:
            raise ValueError("Remote manifest package id does not match Trees 2.0")

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
    """Start a non-blocking GitHub version check."""
    if not _online_access_allowed():
        _set_state(
            status="OFFLINE",
            checking=False,
            message="Blender online access is disabled",
        )
        return False

    state = state_snapshot()
    if state["checking"] or state["updating"]:
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


def _archive_root_and_manifest(source_zip):
    manifests = [
        name for name in source_zip.namelist()
        if name.endswith("blender_manifest.toml") and not name.endswith("/blender_manifest.toml/")
    ]
    if not manifests:
        raise ValueError("Downloaded GitHub archive has no blender_manifest.toml")

    # GitHub source archives normally have one top-level folder such as
    # trees2.0-main/. Prefer the shallowest manifest if multiple exist.
    manifest_name = min(manifests, key=lambda value: len(PurePosixPath(value).parts))
    parts = PurePosixPath(manifest_name).parts
    prefix = "/".join(parts[:-1])
    if prefix:
        prefix += "/"
    manifest_text = source_zip.read(manifest_name).decode("utf-8", errors="replace")
    return prefix, manifest_text


def _safe_package_member(name, prefix):
    if prefix and not name.startswith(prefix):
        return None
    relative = name[len(prefix):] if prefix else name
    relative = relative.replace("\\", "/")
    path = PurePosixPath(relative)
    if not relative or relative.endswith("/"):
        return None
    if path.is_absolute() or ".." in path.parts:
        return None
    if any(part in {".git", ".github", "__pycache__"} for part in path.parts):
        return None
    if path.name == ".gitignore" or path.suffix in {".pyc", ".pyo"}:
        return None
    return str(path)


def _prepare_update_package(installed):
    payload = _request_bytes(DOWNLOAD_URL, installed)
    with zipfile.ZipFile(io.BytesIO(payload), "r") as source_zip:
        prefix, manifest_text = _archive_root_and_manifest(source_zip)
        package_id = _parse_package_id(manifest_text)
        latest = _parse_version(manifest_text)
        if package_id != PACKAGE_ID:
            raise ValueError(f"Downloaded package id is {package_id!r}, expected {PACKAGE_ID!r}")
        if latest <= installed:
            return None, None, latest

        temp_dir = Path(tempfile.mkdtemp(prefix="trees2_update_"))
        package_path = temp_dir / f"trees2-{_version_text(latest)}.zip"
        wrote_manifest = False
        wrote_init = False
        with zipfile.ZipFile(package_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as output_zip:
            for info in source_zip.infolist():
                relative = _safe_package_member(info.filename, prefix)
                if relative is None:
                    continue
                data = source_zip.read(info.filename)
                output_zip.writestr(relative, data)
                wrote_manifest = wrote_manifest or relative == "blender_manifest.toml"
                wrote_init = wrote_init or relative == "__init__.py"

        if not wrote_manifest or not wrote_init:
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise ValueError("Prepared extension ZIP is missing manifest or __init__.py at its root")
        return package_path, temp_dir, latest


def _update_download_worker(installed):
    try:
        package_path, temp_dir, latest = _prepare_update_package(installed)
        if package_path is None:
            _set_state(
                status="UP_TO_DATE" if latest == installed else "LOCAL_AHEAD",
                updating=False,
                latest_version=latest,
                message=(
                    f"Trees 2.0 v{_version_text(installed)} is up to date"
                    if latest == installed
                    else f"Installed v{_version_text(installed)} is newer than GitHub v{_version_text(latest)}"
                ),
                last_checked=time.time(),
            )
            return

        _set_state(
            status="INSTALL_READY",
            update_ready_path=str(package_path),
            update_temp_dir=str(temp_dir),
            update_target_version=latest,
            latest_version=latest,
            message=f"Installing Trees 2.0 v{_version_text(latest)}...",
        )
    except urllib.error.HTTPError as exc:
        _set_state(status="ERROR", updating=False, message=f"Update download failed: HTTP {exc.code}")
    except urllib.error.URLError as exc:
        _set_state(status="ERROR", updating=False, message=f"Update download failed: {getattr(exc, 'reason', exc)}")
    except Exception as exc:
        _set_state(status="ERROR", updating=False, message=f"Update failed: {exc}")


def request_update():
    if not _online_access_allowed():
        _set_state(status="OFFLINE", updating=False, message="Blender online access is disabled")
        return False
    state = state_snapshot()
    if state["checking"] or state["updating"]:
        return False

    installed = installed_version()
    _set_state(
        status="DOWNLOADING",
        checking=False,
        updating=True,
        update_ready_path=None,
        update_temp_dir=None,
        update_target_version=None,
        message="Downloading the latest Trees 2.0 update...",
    )
    worker = threading.Thread(
        target=_update_download_worker,
        args=(installed,),
        name="Trees2SelfUpdate",
        daemon=True,
    )
    worker.start()
    return True


def _path_is_within(child, parent):
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _manifest_is_trees2(directory):
    manifest_path = directory / "blender_manifest.toml"
    if not manifest_path.is_file():
        return False
    try:
        text = manifest_path.read_text(encoding="utf-8")
        return _parse_package_id(text) == PACKAGE_ID
    except Exception:
        return False


def _remove_path(path):
    try:
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
        return True
    except Exception:
        return False


def _clear_python_caches(directory):
    if not directory.exists():
        return
    for cache in list(directory.rglob("__pycache__")):
        shutil.rmtree(cache, ignore_errors=True)
    for pattern in ("*.pyc", "*.pyo"):
        for item in list(directory.rglob(pattern)):
            try:
                item.unlink()
            except Exception:
                pass


def _current_repo_module():
    current_dir = Path(__file__).resolve().parent
    try:
        repos = bpy.context.preferences.extensions.repos
    except Exception:
        return "user_default"

    for repo in repos:
        if getattr(repo, "source", "USER") != "USER":
            continue
        directory = Path(getattr(repo, "directory", "") or "")
        if directory and _path_is_within(current_dir, directory):
            return getattr(repo, "module", "") or "user_default"
    return "user_default"


def _cleanup_old_installations():
    """Remove duplicate Trees 2.0 installs only from Blender-managed locations.

    The currently running package is preserved. The install operator then
    overwrites that package atomically. This deliberately never scans arbitrary
    user folders, repositories or project directories.
    """
    current_dir = Path(__file__).resolve().parent
    removed = 0

    # Extension repositories configured in Blender preferences.
    try:
        repos = list(bpy.context.preferences.extensions.repos)
    except Exception:
        repos = []
    for repo in repos:
        if getattr(repo, "source", "USER") != "USER":
            continue
        repo_dir = Path(getattr(repo, "directory", "") or "")
        if not repo_dir.is_dir():
            continue
        for candidate in list(repo_dir.iterdir()):
            if not candidate.is_dir() or candidate.resolve() == current_dir:
                continue
            if _manifest_is_trees2(candidate) and _remove_path(candidate):
                removed += 1

    # Legacy add-on folders are also a common cause of two Trees 2.0 versions
    # being loaded at once after moving to Blender's extension system.
    try:
        addon_roots = bpy.utils.script_paths(subdir="addons")
    except Exception:
        addon_roots = []
    for root_text in addon_roots:
        root = Path(root_text)
        if not root.is_dir():
            continue
        for candidate in list(root.iterdir()):
            if not candidate.is_dir() or candidate.resolve() == current_dir:
                continue
            looks_named = candidate.name.lower().replace(".", "").replace("_", "").replace("-", "") in {
                "trees2", "trees20", "trees20main", "trees2main"
            }
            if (_manifest_is_trees2(candidate) or (looks_named and (candidate / "__init__.py").is_file())):
                if _remove_path(candidate):
                    removed += 1

    _clear_python_caches(current_dir)
    return removed


def _cleanup_update_temp(state):
    temp_dir = state.get("update_temp_dir")
    if temp_dir:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _install_ready_update():
    state = state_snapshot()
    if state["status"] != "INSTALL_READY" or not state.get("update_ready_path"):
        return

    package_path = Path(state["update_ready_path"])
    target_version = state.get("update_target_version")
    try:
        if not package_path.is_file():
            raise FileNotFoundError("Prepared update package disappeared")

        removed = _cleanup_old_installations()
        repo_module = _current_repo_module()
        _set_state(status="INSTALLING", message=f"Installing v{_version_text(target_version)}...")

        result = bpy.ops.extensions.package_install_files(
            filepath=str(package_path),
            repo=repo_module,
            enable_on_install=True,
            overwrite=True,
        )
        if "FINISHED" not in result:
            raise RuntimeError(f"Blender extension installer returned {sorted(result)}")

        _cleanup_update_temp(state)
        _set_state(
            status="UPDATED",
            updating=False,
            checking=False,
            update_ready_path=None,
            update_temp_dir=None,
            latest_version=target_version,
            message=(
                f"Updated to v{_version_text(target_version)}"
                + (f"; removed {removed} older duplicate install(s)" if removed else "")
            ),
            last_checked=time.time(),
        )
    except Exception as exc:
        _cleanup_update_temp(state)
        _set_state(
            status="ERROR",
            updating=False,
            update_ready_path=None,
            update_temp_dir=None,
            message=f"Automatic install failed: {exc}",
        )


def _startup_check_timer():
    request_check(force=False)
    return None


def _update_poll_timer():
    # All bpy operators stay on Blender's main thread. The worker only handles
    # HTTP and ZIP preparation, then this timer performs the actual install.
    _install_ready_update()
    return 0.25 if state_snapshot().get("updating") else 1.0


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
            _set_state(status="OFFLINE", checking=False, message="Blender online access is disabled")
            return {"CANCELLED"}

        if request_check(force=True):
            self.report({"INFO"}, "Checking GitHub for Trees 2.0 updates")
        return {"FINISHED"}


class TREES2_OT_UpdateNow(bpy.types.Operator):
    bl_idname = "trees2.update_now"
    bl_label = "Update Now"
    bl_description = "Download, install and clean older Trees 2.0 versions in one click"

    def execute(self, context):
        if not _online_access_allowed():
            self.report(
                {"WARNING"},
                "Blender online access is disabled; enable Allow Online Access in Preferences",
            )
            return {"CANCELLED"}
        if request_update():
            self.report({"INFO"}, "Trees 2.0 update started")
        return {"FINISHED"}


class TREES2_OT_OpenUpdatePage(bpy.types.Operator):
    bl_idname = "trees2.open_update_page"
    bl_label = "Open GitHub"
    bl_description = "Open the Trees 2.0 GitHub repository in your web browser"

    def execute(self, context):
        webbrowser.open(REPOSITORY_URL)
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

        layout.label(text=f"Installed: v{_version_text(installed)}")

        if not _online_access_allowed():
            box = layout.box()
            box.alert = True
            box.label(text="Online access disabled", icon="ERROR")
            box.label(text="Enable Allow Online Access in Preferences")
        elif state["updating"] or state["status"] in {"DOWNLOADING", "INSTALL_READY", "INSTALLING"}:
            box = layout.box()
            box.label(text=state["message"][:96], icon="TIME")
            box.label(text="Do not close Blender while the extension is being replaced.")
        elif state["checking"] or state["status"] == "CHECKING":
            layout.label(text="Checking GitHub...", icon="TIME")
        elif state["status"] == "UPDATE_AVAILABLE":
            latest = _version_text(state["latest_version"])
            box = layout.box()
            box.alert = True
            box.label(text=f"Update available: v{latest}", icon="IMPORT")
            update_row = box.row()
            update_row.scale_y = 1.35
            update_row.operator("trees2.update_now", text="Update Now", icon="IMPORT")
            box.label(text="Downloads, replaces and cleans old installs automatically.", icon="INFO")
        elif state["status"] == "UPDATED":
            box = layout.box()
            box.label(text=state["message"][:96], icon="CHECKMARK")
            box.label(text="Update installed. Restart Blender if any old UI remains.", icon="INFO")
        elif state["status"] == "UP_TO_DATE":
            latest = _version_text(state["latest_version"])
            layout.label(text=f"Up to date: v{latest}", icon="CHECKMARK")
        elif state["status"] == "LOCAL_AHEAD":
            layout.label(text="Development build newer than GitHub", icon="INFO")
        elif state["status"] == "ERROR":
            box = layout.box()
            box.alert = True
            box.label(text="Update failed", icon="ERROR")
            box.label(text=state["message"][:96])
        else:
            layout.label(text="GitHub has not been checked yet", icon="INFO")

        row = layout.row(align=True)
        row.enabled = not state.get("updating", False)
        row.operator("trees2.check_for_updates", text="Check", icon="FILE_REFRESH")
        row.operator("trees2.open_update_page", text="GitHub", icon="URL")


CLASSES = (
    TREES2_OT_CheckForUpdates,
    TREES2_OT_UpdateNow,
    TREES2_OT_OpenUpdatePage,
    TREES2_PT_UpdateStatus,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    if not bpy.app.background and not bpy.app.timers.is_registered(_startup_check_timer):
        bpy.app.timers.register(_startup_check_timer, first_interval=2.5, persistent=False)
    if not bpy.app.background and not bpy.app.timers.is_registered(_update_poll_timer):
        bpy.app.timers.register(_update_poll_timer, first_interval=1.0, persistent=True)


def unregister():
    for timer in (_startup_check_timer, _update_poll_timer):
        if bpy.app.timers.is_registered(timer):
            bpy.app.timers.unregister(timer)
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
