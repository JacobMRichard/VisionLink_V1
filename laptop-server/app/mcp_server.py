"""
VisionLink MCP Server
Gives Claude live read + control access to the running VisionLink server.

Read tools  — query session files written by the server.
Control tools — POST to the server's /control endpoint to change settings live.

Start separately (server must already be running):
    cd laptop-server
    python -m app.mcp_server
"""
import json
import statistics
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

import app.config as config

mcp = FastMCP("VisionLink")

SESSIONS_DIR = Path(__file__).parent.parent / "sessions"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _session_folder() -> Optional[Path]:
    pointer = SESSIONS_DIR / "current.json"
    if pointer.exists():
        data = json.loads(pointer.read_text())
        folder = Path(data["folder"])
        if folder.exists():
            return folder
    if SESSIONS_DIR.exists():
        folders = [p for p in SESSIONS_DIR.iterdir() if p.is_dir()]
        if folders:
            return max(folders, key=lambda p: p.stat().st_mtime)
    return None


def _read_json(path: Path) -> Optional[dict]:
    if path.exists():
        return json.loads(path.read_text())
    return None


def _control_url() -> str:
    folder = _session_folder()
    port = config.FRAME_PORT
    if folder:
        snap = _read_json(folder / "config_snapshot.json")
        if snap:
            port = snap.get("frame_port", port)
    return f"http://localhost:{port}/control"


def _post_control(payload: dict) -> dict:
    url = _control_url()
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        return {"error": f"Could not reach server at {url}: {exc.reason}. Is it running?"}


def _resolve_classes(classes: Optional[list], group: Optional[str]) -> Optional[list]:
    """Expand a group name (e.g. 'animals') to its class list, or return classes as-is."""
    if group:
        resolved = config.CLASS_GROUPS.get(group.lower())
        if resolved is None:
            available = list(config.CLASS_GROUPS.keys())
            raise ValueError(f"Unknown group '{group}'. Available: {available}")
        return resolved
    return classes


# ── Read tools ────────────────────────────────────────────────────────────────

@mcp.tool()
def get_session() -> dict:
    """
    Get current session info: session ID, config, folder path, and whether
    the server appears to be actively running.
    """
    folder = _session_folder()
    if folder is None:
        return {"error": "No session found — has the server been started yet?"}

    cfg = _read_json(folder / "config_snapshot.json")
    timings_path = folder / "recent_timings.json"
    result: dict = {
        "session_folder": str(folder),
        "config": cfg,
        "server_running": False,
        "timings_file_age_s": None,
    }
    if timings_path.exists():
        age = round(time.time() - timings_path.stat().st_mtime, 1)
        result["timings_file_age_s"] = age
        result["server_running"] = age < 5.0
    return result


@mcp.tool()
def get_timings(n: int = 30) -> dict:
    """
    Get the last N frame pipeline timings.
    Each record: frame_id, fps, latency_ms, decode_ms, detect_ms, track_ms, total_ms, objects.
    """
    folder = _session_folder()
    if folder is None:
        return {"error": "No active session"}
    data = _read_json(folder / "recent_timings.json")
    if data is None:
        return {"error": "No timings yet"}
    timings = data.get("timings", [])
    return {
        "updated_at_ms":  data.get("updated_at"),
        "total_recorded": len(timings),
        "returned":       min(n, len(timings)),
        "timings":        timings[-n:],
    }


@mcp.tool()
def get_stats() -> dict:
    """
    Aggregate pipeline stats: avg/min/max/p95 for decode_ms, detect_ms,
    track_ms, total_ms, latency_ms, fps. Use this to spot bottlenecks.
    """
    folder = _session_folder()
    if folder is None:
        return {"error": "No active session"}
    data = _read_json(folder / "recent_timings.json")
    if not data or not data.get("timings"):
        return {"error": "No timing records yet"}

    timings = data["timings"]
    keys = ["decode_ms", "detect_ms", "track_ms", "total_ms", "latency_ms", "fps"]
    result: dict = {"samples": len(timings), "stages": {}}
    for key in keys:
        vals = [t[key] for t in timings if key in t]
        if not vals:
            continue
        s = sorted(vals)
        p95_idx = max(0, int(len(s) * 0.95) - 1)
        result["stages"][key] = {
            "avg": round(statistics.mean(vals), 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
            "p95": round(s[p95_idx], 1),
        }
    return result


@mcp.tool()
def get_exceptions() -> dict:
    """Get all recorded pipeline exceptions from this session. Empty = clean run."""
    folder = _session_folder()
    if folder is None:
        return {"error": "No active session"}
    path = folder / "exceptions.txt"
    if not path.exists() or path.stat().st_size == 0:
        return {"status": "clean", "exceptions": "None recorded."}
    return {"status": "has_exceptions", "exceptions": path.read_text(encoding="utf-8")}


@mcp.tool()
def get_live_config() -> dict:
    """
    Get the current live runtime config: class filter, confidence threshold,
    max objects, notification settings. These are the values the running
    pipeline is actually using right now.
    """
    return _post_control({})   # POST with empty body returns current config


# ── Control tools ─────────────────────────────────────────────────────────────

@mcp.tool()
def set_class_filter(classes: Optional[list] = None, group: Optional[str] = None) -> dict:
    """
    Filter what YOLO classes get tracked and shown on the phone overlay.

    Pass a group name OR a specific class list (not both).

    Groups: people, animals, pets, vehicles, electronics, furniture, food, sports, kitchen
    Examples:
      set_class_filter(group="people")          → only person
      set_class_filter(group="animals")         → all animal classes
      set_class_filter(classes=["person","dog"]) → person + dog only
      set_class_filter()                        → remove filter (track everything)

    Takes effect immediately on the next processed frame.
    """
    try:
        resolved = _resolve_classes(classes, group)
    except ValueError as exc:
        return {"error": str(exc)}
    return _post_control({"class_filter": resolved})


@mcp.tool()
def set_confidence(threshold: float) -> dict:
    """
    Set the minimum YOLO detection confidence (0.05–0.99).
    Lower = more detections (noisier). Higher = fewer but more certain.
    Default: 0.4. Takes effect immediately.
    """
    return _post_control({"confidence": threshold})


@mcp.tool()
def set_max_objects(n: int) -> dict:
    """
    Set the maximum number of objects tracked simultaneously (1–50).
    E.g. set_max_objects(2) to track only the top 2 highest-priority objects.
    Takes effect immediately.
    """
    return _post_control({"max_objects": n})


@mcp.tool()
def set_notifications(
    enabled: bool,
    cooldown_s: Optional[float] = None,
    min_count: Optional[int] = None,
) -> dict:
    """
    Enable or disable Discord notifications and tune their behaviour.

    enabled     — True/False
    cooldown_s  — seconds between alerts for the same class (default 30)
    min_count   — minimum simultaneous confirmed detections to trigger (default 1)

    Example: set_notifications(True, cooldown_s=60, min_count=2)
    → alert when 2+ of the same class are confirmed, at most once per minute.
    """
    payload: dict = {"notifications": {"enabled": enabled}}
    if cooldown_s is not None:
        payload["notifications"]["cooldown_s"] = cooldown_s
    if min_count is not None:
        payload["notifications"]["min_count"] = min_count
    return _post_control(payload)


@mcp.tool()
def reset_all_filters() -> dict:
    """
    Reset class filter to all classes, confidence to default (0.4),
    max objects to default (10). Notifications unchanged.
    """
    return _post_control({
        "class_filter": None,
        "confidence":   config.CONFIDENCE_THRESHOLD,
        "max_objects":  config.MAX_TRACKED_OBJECTS,
    })


@mcp.tool()
def list_class_groups() -> dict:
    """List all available class group presets and their member classes."""
    return {
        "groups": {
            name: sorted(classes)
            for name, classes in config.CLASS_GROUPS.items()
        }
    }


# ── Resources ─────────────────────────────────────────────────────────────────

@mcp.resource("visionlink://status")
def status_resource() -> str:
    """
    Read-only snapshot of the current VisionLink session.
    Returns session ID, live runtime config (class filter, confidence,
    max objects, notifications), and aggregate pipeline stats (fps, latency,
    detect_ms). Use this to understand what the server is currently doing
    before issuing control commands.
    """
    folder = _session_folder()
    if folder is None:
        return json.dumps({"error": "No active session"})

    cfg = _read_json(folder / "config_snapshot.json")
    live = _post_control({})   # empty POST returns current config

    stats: dict = {}
    data = _read_json(folder / "recent_timings.json")
    if data and data.get("timings"):
        timings = data["timings"]
        for key in ["fps", "latency_ms", "detect_ms"]:
            vals = [t[key] for t in timings if key in t]
            if vals:
                stats[key] = {"avg": round(sum(vals) / len(vals), 1), "samples": len(vals)}

    return json.dumps({
        "session_id":   cfg.get("session_id") if cfg else None,
        "live_config":  live,
        "pipeline_stats": stats,
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
