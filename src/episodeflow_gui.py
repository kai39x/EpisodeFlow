"""
EpisodeFlow - window
Starts a small local server (only reachable from this PC) and shows it in a window:
 - a real app window (pywebview) when available, e.g. in EpisodeFlow.exe: drag & drop works there
 - otherwise an Edge app window, so it still runs with nothing extra installed

    pyw episodeflow_gui.py "D:\\Anime"            a show folder, or a folder of show folders
    pyw episodeflow_gui.py                       opens empty, choose a folder inside
"""
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import time
import traceback
import struct
import tempfile
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import episodeflow as ef

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE = getattr(sys, "_MEIPASS", HERE)          # where PyInstaller unpacks the UI file
UI_FILE = os.path.join(BUNDLE, "episodeflow_ui.html")
LOG_FILE = os.path.join(ef.DATA_DIR, "episodeflow_error.log")
WEBVIEW = {"window": None}                         # set when running in the pywebview window
TOKEN = secrets.token_urlsafe(16)


# ======================================================================
# State
# ======================================================================
class Show:
    def __init__(self, sid: int, folder: str, only=None):
        self.id, self.folder, self.only = sid, folder, only
        self.name = os.path.basename(os.path.normpath(folder))
        self.plan: ef.ShowPlan | None = None
        self.status, self.error = "waiting", ""


class State:
    def __init__(self):
        self.lock = threading.RLock()
        self.root, self.shows, self.busy, self.message = "", [], False, ""
        self.last_beat, self.seen_beat = time.time(), False

    def open(self, paths: list[str]):
        paths = [p for p in paths if p]
        if not paths:
            return ef.EFError("err_choose", "Choose a folder first.")
        dirs = [p for p in paths if os.path.isdir(p)]
        files = [p for p in paths if os.path.isfile(p)]
        shows = []
        if files and not dirs:      # files picked in Explorer: just those files
            folder = os.path.dirname(os.path.abspath(files[0]))
            shows.append((folder, [os.path.basename(f) for f in files]))
        for d in dirs:
            shows += [(f, None) for f in ef.find_show_folders(d)]
        if not shows:
            missing = [p for p in paths if not os.path.exists(p)]
            if missing:
                return ef.EFError("err_no_folder", f"This folder doesn't exist: {missing[0]}", name=missing[0])
            return ef.EFError("err_no_episodes", "No episodes found here, or in the folders inside it.")
        with self.lock:
            self.root = paths[0] if len(paths) == 1 else f"{len(paths)} items"
            self.shows = [Show(i, f, only) for i, (f, only) in enumerate(shows)]
            self.busy = True
        threading.Thread(target=self._analyze_all, daemon=True).start()
        return None

    def _analyze_all(self):
        for show in list(self.shows):
            self.analyze(show)
        with self.lock:
            self.busy = False

    def analyze(self, show: Show):
        with self.lock:
            show.status, show.error = "analyzing", ""
        try:
            plan = ef.analyze(show.folder, show.only)
            status = ef.plan_status(plan)
            with self.lock:
                show.plan, show.status, show.name = plan, status, plan.show
        except Exception as e:
            log_error()
            with self.lock:
                show.status, show.error = "error", str(e)

    def get(self, sid) -> Show:
        for s in self.shows:
            if s.id == int(sid):
                return s
        raise KeyError("That show isn't open any more. Reload the folder.")


STATE = State()


# ======================================================================
# JSON views
# ======================================================================
def show_summary(s: Show) -> dict:
    count = len(ef.plan_pairs(s.plan)) if s.plan and s.status not in ("analyzing", "error") else 0
    return {"id": s.id, "name": s.name, "status": s.status, "renames": count, "error": s.error}


def row_view(plan: ef.ShowPlan, i: int, r: ef.Result) -> dict:
    target = ef.target_name(plan, r)
    if r.skipped or r.episode is None:
        mark = "skip"
    elif r.conflict:
        mark = "conflict"
    elif target == r.original:
        mark = "same"
    elif r.confidence != "high":
        mark = "review"
    else:
        mark = "ok"
    notes = [list(n) for n in r.note_keys]
    if r.conflict:
        notes.append(["same_number", {}])
    if r.skipped:
        notes = [["skipped", {}]]
    elif r.episode is None:
        notes = [["no_number", {}]]
    if mark in ("ok", "same"):   # on fine rows only show what you did yourself
        notes = [n for n in notes if n[0] in ("edited", "shifted", "kept_both")]
    subs = [s for s, _ in ef.matching_subs(plan.folder, r.original, plan.all_files)] if target else []
    return {"row": i, "original": r.original, "target": target, "mark": mark, "notes": notes,
            "info": r.info_keys, "season": r.season, "episode": r.episode, "raw": r.raw_episode,
            "part": r.part, "special": r.special, "subs": subs, "suffix": r.suffix}


def show_detail(s: Show) -> dict:
    base = show_summary(s)
    plan = s.plan
    if not plan:
        return base
    ef.mark_conflicts(plan.results)
    rows = [row_view(plan, i, r) for i, r in enumerate(plan.ordered)]
    lookup = plan.lookup
    anilist = None
    if lookup and lookup._done:
        anilist = {"status": lookup.status_key, "matched": bool(lookup.labels), "cover": lookup.cover(),
                   "chain": [{"season": e["season"], "part": e["part"], "episodes": e["episodes"],
                              "aired": e.get("aired"), "title": e["title"]} for e in (lookup.labels or [])]}
    specials = sorted(r.episode for r in plan.results if r.special and r.episode and not r.skipped)
    base.update({
        "status": ef.plan_status(plan),
        "folder": plan.folder, "anilist": anilist, "rows": rows,
        "seasons": ef.missing_episodes(plan), "specials": specials,
        "counts": {k: sum(1 for r in rows if r["mark"] == k) for k in ("ok", "review", "conflict", "skip", "same")},
        "renames": len(ef.plan_pairs(plan)), "can_undo": ef.can_undo(plan.folder),
        "duplicates": ef.duplicate_groups(plan), "has_icon": has_folder_icon(plan.folder),
        "storage": ef.storage_summary(plan),
    })
    return base


def settings_view() -> dict:
    s = ef.load_settings()
    return {"template": ef.TEMPLATE, "presets": ef.PRESET_TEMPLATES, "default": ef.DEFAULT_TEMPLATE,
            "data_dir": ef.DATA_DIR, "mode": app_mode(), "shortcuts": s.get("shortcuts", ""),
            "version": ef.VERSION, "repo": ef.REPO_URL}


def storage_view() -> dict:
    shows = []
    with STATE.lock:
        for s in STATE.shows:
            if s.plan:
                shows.append({"id": s.id, "name": s.name, **ef.storage_summary(s.plan)})
    biggest = sorted(((f["name"], f["bytes"], sh["name"], sh["id"]) for sh in shows for f in sh["largest"]), key=lambda x: -x[1])[:10]
    return {"shows": sorted(shows, key=lambda x: -x["total"]), "total": sum(s["total"] for s in shows),
            "biggest": [{"name": n, "bytes": b, "show": sn, "id": i} for n, b, sn, i in biggest]}


def state_view() -> dict:
    with STATE.lock:
        return {"root": STATE.root, "busy": STATE.busy, "message": STATE.message, "mode": app_mode(),
                "shortcuts": ef.load_settings().get("shortcuts", ""),
                "shows": [show_summary(s) for s in STATE.shows]}


# ======================================================================
# Actions
# ======================================================================
def act(path: str, data: dict):
    STATE.message = ""
    if path == "/api/open":
        err = STATE.open([data.get("path", "").strip().strip('"')])
        if err:
            raise err
        return state_view()
    if path == "/api/browse":
        return {"path": browse_folder()}
    if path == "/api/reload":
        if not STATE.root or not STATE.shows:
            raise ef.EFError("err_choose", "Choose a folder first.")
        paths = [STATE.root] if os.path.exists(STATE.root) else [s.folder for s in STATE.shows]
        err = STATE.open(paths)
        if err:
            raise err
        return state_view()
    if path == "/api/apply_ready":
        done, total = [], 0
        for s in list(STATE.shows):
            if s.plan and ef.plan_status(s.plan) == "ready":
                try:
                    total += ef.apply_plan(s.plan)
                    done.append(s.name)
                except Exception as e:
                    s.error = str(e)
                STATE.analyze(s)
        return {**state_view(), "renamed": total, "renamed_shows": done}
    if path == "/api/undo_entry":
        n = ef.undo_entry(int(data["entry"]))
        for s in list(STATE.shows):
            if ef._same_folder(s.folder, data.get("folder", "")):
                STATE.analyze(s)
        return {"restored": n, "history": ef.load_history()[::-1], **state_view()}
    if path == "/api/icons_done":
        folders = [s.folder for s in STATE.shows if int(s.id) in {int(x) for x in data.get("ids", [])}]
        refresh_explorer(folders)
        log_note(f"icons for all: {len(folders)} folders refreshed")
        return state_view()
    if path == "/api/shortcuts":
        want = "yes" if data.get("on") else "no"
        if want == "yes":
            portable_shortcuts("create")
        elif data.get("remove"):
            portable_shortcuts("remove")
        s = ef.load_settings()
        s["shortcuts"] = want
        ef.save_settings(s)
        return settings_view()
    if path == "/api/remove_app":
        remove_from_pc()
        return {"ok": True}
    if path == "/api/open_url":
        url = str(data.get("url", ""))
        if url.startswith(("https://anilist.co", "https://github.com/")) or (ef.REPO_URL and url == ef.REPO_URL):
            webbrowser.open(url)
        return {}
    if path == "/api/open_data":
        if os.name == "nt":
            os.startfile(ef.DATA_DIR)
        return {"data_dir": ef.DATA_DIR}
    if path == "/api/settings":
        ef.set_template(str(data.get("template", "")))
        for s in list(STATE.shows):          # new names -> new statuses
            if s.plan:
                s.status = ef.plan_status(s.plan)
        return {**settings_view(), **state_view()}

    s = STATE.get(data["id"])
    plan = s.plan
    if path == "/api/edit":
        r = plan.ordered[int(data["row"])]
        if data.get("skip"):
            ef.edit_result(r, None, None, skip=True)
        else:
            ef.edit_result(r, int(data["season"]), int(data["episode"]))
    elif path == "/api/shift":
        ef.shift_part(plan.ordered[int(data["row"])], int(data["offset"]), plan.results)
    elif path == "/api/apply":
        n = ef.apply_plan(plan)
        STATE.analyze(s)
        return {"renamed": n, "show": show_detail(s)}
    elif path == "/api/undo":
        n = ef.undo(s.folder)
        STATE.analyze(s)
        return {"restored": n, "show": show_detail(s)}
    elif path == "/api/reanalyze":
        STATE.analyze(s)
    elif path == "/api/keep_both":
        ef.keep_both(plan, [int(x) for x in data["rows"]])
    elif path == "/api/recycle":
        n = ef.recycle_files(plan, [int(x) for x in data["rows"]])
        STATE.analyze(s)
        return {"recycled": n, "show": show_detail(s)}
    elif path == "/api/icon":
        import base64
        pngs = {int(k): base64.b64decode(v) for k, v in (data.get("pngs") or {}).items()}
        if not pngs or not all(p[:8] == b"\x89PNG\r\n\x1a\n" for p in pngs.values()):
            raise ef.EFError("err_icon_failed", "Couldn't make the icon from the AniList picture.")
        try:
            # in "all folders" mode Explorer is refreshed once at the end instead of after every icon
            set_folder_icon(plan.folder, pngs, refresh=not data.get("batch"))
        except Exception as e:
            log_note(f"icon failed: {plan.folder}: {e!r}")
            raise
    elif path == "/api/icon_remove":
        remove_folder_icon(plan.folder)
    s.status = ef.plan_status(plan) if s.plan else s.status
    return {"show": show_detail(s)}


def browse_folder() -> str:
    """Folder picker: the app window's own dialog, or Windows' via PowerShell."""
    win = WEBVIEW["window"]
    if win is not None:
        try:
            import webview
            kind = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
            picked = win.create_file_dialog(kind)
            return picked[0] if picked else ""
        except Exception:
            log_error()
    if os.name != "nt":
        return ""
    script = (
        "[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
        "Add-Type -AssemblyName System.Windows.Forms;"
        "$f=New-Object System.Windows.Forms.Form -Property @{TopMost=$true};"
        "$d=New-Object System.Windows.Forms.FolderBrowserDialog;"
        "$d.Description='Choose an anime folder, or a folder that has anime folders inside';"
        "if($d.ShowDialog($f) -eq 'OK'){$d.SelectedPath}"
    )
    out = subprocess.run(["powershell", "-NoProfile", "-STA", "-Command", script],
                         capture_output=True, text=True, encoding="utf-8",
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return out.stdout.strip()


# ======================================================================
# Portable app: shortcuts and removing the program
# ======================================================================
def app_mode() -> str:
    """'portable' (EpisodeFlow.exe) or 'dev' (running the .py files)."""
    return "portable" if getattr(sys, "frozen", False) else "dev"


_SHORTCUT_PS = r"""
$ws = New-Object -ComObject WScript.Shell
foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('SendTo'))) {
  $p = Join-Path $d 'EpisodeFlow.lnk'
  if ($env:EPF_MODE -eq 'remove') { if (Test-Path $p) { Remove-Item $p -Force }; continue }
  if ($env:EPF_MODE -eq 'fix' -and -not (Test-Path $p)) { continue }
  $s = $ws.CreateShortcut($p)
  if ($s.TargetPath -ne $env:EPF_EXE) {
    $s.TargetPath = $env:EPF_EXE; $s.WorkingDirectory = (Split-Path $env:EPF_EXE); $s.IconLocation = "$($env:EPF_EXE),0"; $s.Save()
  }
}
"""


def portable_shortcuts(mode: str):
    """mode: 'create' (Desktop + Send To), 'fix' (point existing ones at this exe), 'remove'."""
    if os.name != "nt" or app_mode() != "portable":
        return
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _SHORTCUT_PS],
                   env={**os.environ, "EPF_MODE": mode, "EPF_EXE": sys.executable},
                   capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def remove_from_pc():
    """Remove the shortcuts, the data folder and the exe itself once the window has closed.
    Anime files are never touched."""
    mode = app_mode()
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    if mode == "portable":
        portable_shortcuts("remove")
        cmd = (f'ping -n 6 127.0.0.1 >nul & del /f /q "{sys.executable}" & '
               f'rmdir /s /q "{ef.DATA_DIR}"')
        subprocess.Popen(["cmd", "/c", cmd], creationflags=flags, close_fds=True)
    else:
        raise ef.EFError("err_remove_dev", "Running from the source files: just delete the folder.")
    log_note(f"remove requested ({mode})")
    threading.Thread(target=_close_soon, daemon=True).start()


def _close_soon():
    time.sleep(0.8)
    win = WEBVIEW["window"]
    try:
        if win is not None:
            win.destroy()
    except Exception:
        pass
    if SERVER:
        SERVER.shutdown()


# ======================================================================
# Folder icon (AniList cover -> EpisodeFlow.ico + desktop.ini)
# The window shrinks the picture to 256/48/32/16 px PNGs; here we only write files.
# ======================================================================
ICON_PREFIX = "EpisodeFlow"   # icon files: EpisodeFlow-<time>.ico (a new name each time beats Explorer's icon cache)
_COVER_CACHE: dict[str, tuple[bytes, str]] = {}


def download_cover(url: str) -> tuple[bytes, str]:
    if url in _COVER_CACHE:
        return _COVER_CACHE[url]
    last = None
    for ua in ("EpisodeFlow/0.1", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua if ua != "EpisodeFlow/0.1" else ef.USER_AGENT})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data, ctype = resp.read(), resp.headers.get("Content-Type", "image/jpeg")
            _COVER_CACHE[url] = (data, ctype)
            return data, ctype
        except Exception as e:
            last = e
    log_note(f"cover download failed for {url}: {last!r}")
    raise ef.EFError("err_icon_download", "Couldn't download the picture from AniList.")


def make_ico(pngs: dict[int, bytes]) -> bytes:
    """Several PNG sizes packed into one Windows .ico (PNG icons work since Vista)."""
    sizes = sorted(pngs)
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset, entries, blobs = 6 + 16 * len(sizes), b"", b""
    for s in sizes:
        data = pngs[s]
        dim = 0 if s >= 256 else s
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    return header + entries + blobs


def _set_attrs(path: str, attrs: int):
    import ctypes
    if not ctypes.windll.kernel32.SetFileAttributesW(path, attrs):
        log_note(f"SetFileAttributesW failed ({ctypes.GetLastError()}) for {path}")


def _get_attrs(path: str) -> int:
    import ctypes
    a = ctypes.windll.kernel32.GetFileAttributesW(path) & 0xFFFFFFFF
    return 0x10 if a == 0xFFFFFFFF else a


def refresh_explorer(folders: list[str]):
    """Tell Explorer these folders changed. Never waits, so many icons in a row don't pile up."""
    if os.name != "nt" or not folders:
        return
    import ctypes
    sh = ctypes.windll.shell32
    NOWAIT = 0x3000                                              # SHCNF_FLUSHNOWAIT
    for f in folders:
        sh.SHChangeNotify(0x00002000, 0x0005 | NOWAIT, f, None)   # SHCNE_UPDATEITEM
    for parent in {os.path.dirname(f) for f in folders}:
        sh.SHChangeNotify(0x00001000, 0x0005 | NOWAIT, parent, None)  # SHCNE_UPDATEDIR
    sh.SHChangeNotify(0x08000000, NOWAIT, None, None)            # SHCNE_ASSOCCHANGED
    try:   # rebuild the icon cache in the background, once
        subprocess.Popen(["ie4uinit.exe", "-show"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception:
        pass


def _icon_files(folder: str) -> list[str]:
    try:
        return [f for f in os.listdir(folder) if f.startswith(ICON_PREFIX) and f.lower().endswith(".ico")]
    except OSError:
        return []


def has_folder_icon(folder: str) -> bool:
    return bool(_icon_files(folder))


def _ini_text(path: str) -> str:
    raw = open(path, "rb").read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", "ignore")
    return raw.decode("utf-8", "ignore")


def set_folder_icon(folder: str, pngs: dict[int, bytes], refresh: bool = True):
    ini = os.path.join(folder, "desktop.ini")
    if os.path.exists(ini):
        text = _ini_text(ini)
        if "IconResource" in text and ICON_PREFIX not in text:
            raise ef.EFError("err_icon_custom", "This folder already has its own icon, so it was left alone.")
    old = _icon_files(folder)
    name = f"{ICON_PREFIX}-{int(time.time())}.ico"
    ico = os.path.join(folder, name)
    if os.name == "nt" and os.path.exists(ini):
        _set_attrs(ini, 0x80)                        # normal, so it can be overwritten
    with open(ico, "wb") as fh:
        fh.write(make_ico(pngs))
    with open(ini, "w", encoding="utf-16") as fh:    # UTF-16 with BOM, as Explorer writes it
        fh.write(f"[.ShellClassInfo]\r\nIconResource={name},0\r\nIconFile={name}\r\nIconIndex=0\r\n")
    for f in old:                                    # remove earlier icons of ours
        p = os.path.join(folder, f)
        if f != name:
            if os.name == "nt":
                _set_attrs(p, 0x80)
            try:
                os.remove(p)
            except OSError:
                pass
    if os.name == "nt":
        _set_attrs(ico, 0x2 | 0x4)                   # hidden + system
        _set_attrs(ini, 0x2 | 0x4)
        _set_attrs(folder, _get_attrs(folder) | 0x1)  # read-only folder = Explorer reads desktop.ini
    if refresh:
        refresh_explorer([folder])
    log_note(f"icon set: {folder} {name} ico={os.path.getsize(ico)}B")


def remove_folder_icon(folder: str):
    ini = os.path.join(folder, "desktop.ini")
    files = _icon_files(folder)
    if not files:
        return
    for f in files:
        p = os.path.join(folder, f)
        if os.name == "nt":
            _set_attrs(p, 0x80)
        os.remove(p)
    if os.path.exists(ini) and ICON_PREFIX in _ini_text(ini):
        if os.name == "nt":
            _set_attrs(ini, 0x80)
        os.remove(ini)
    if os.name == "nt":
        _set_attrs(folder, _get_attrs(folder) & ~0x1)
    refresh_explorer([folder])
    log_note(f"icon removed: {folder}")


# ======================================================================
# HTTP
# ======================================================================
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _authorized(self) -> bool:
        return self.headers.get("X-Token") == TOKEN

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/":
            if parse_qs(url.query).get("t", [""])[0] != TOKEN:
                return self._send(403, b"Forbidden", "text/plain")
            with open(UI_FILE, "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if not self._authorized():
            return self._json({"error": "forbidden"}, 403)
        try:
            if url.path == "/api/state":
                return self._json(state_view())
            if url.path == "/api/history":
                return self._json({"history": ef.load_history()[::-1]})
            if url.path == "/api/settings":
                return self._json(settings_view())
            if url.path == "/api/storage":
                return self._json(storage_view())
            if url.path == "/api/cover":
                with STATE.lock:
                    s = STATE.get(parse_qs(url.query)["id"][0])
                cover = s.plan.lookup.cover() if s.plan and s.plan.lookup else None
                if not cover:
                    raise ef.EFError("err_icon_nocover", "AniList has no picture for this show.")
                data, ctype = download_cover(cover)
                return self._send(200, data, ctype)
            if url.path == "/api/show":
                with STATE.lock:
                    s = STATE.get(parse_qs(url.query)["id"][0])
                return self._json(show_detail(s))
        except ef.EFError as e:
            return self._json({"error": str(e), "error_key": e.key, "error_values": e.values}, 400)
        except Exception as e:
            log_error()
            return self._json({"error": str(e)}, 500)
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._authorized():
            return self._json({"error": "forbidden"}, 403)
        length = int(self.headers.get("Content-Length") or 0)
        data = json.loads(self.rfile.read(length) or b"{}")
        path = urlparse(self.path).path
        if path == "/api/clientlog":
            log_note("window: " + str(data.get("msg", ""))[:500])
            return self._json({})
        if path == "/api/beat":
            STATE.last_beat, STATE.seen_beat = time.time(), True
            return self._json({})
        if path == "/api/bye":
            self._json({})
            threading.Thread(target=lambda: (time.sleep(1.5), maybe_quit(force_check=True)), daemon=True).start()
            return
        try:
            self._json(act(path, data))
        except ef.EFError as e:
            self._json({"error": str(e), "error_key": e.key, "error_values": e.values})
        except Exception as e:
            log_error()
            self._json({"error": str(e)})


SERVER: ThreadingHTTPServer | None = None


def maybe_quit(force_check=False):
    """Close the server once the window is gone (no heartbeat)."""
    quiet = time.time() - STATE.last_beat
    if (STATE.seen_beat and quiet > 10) or (not STATE.seen_beat and quiet > 120) or (force_check and quiet > 1.4):
        threading.Thread(target=SERVER.shutdown, daemon=True).start()


def watchdog():
    while True:
        time.sleep(2)
        maybe_quit()


# ======================================================================
# Window
# ======================================================================
def find_browser() -> str | None:
    roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
    for root in filter(None, roots):
        for rel in (r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"):
            p = os.path.join(root, rel)
            if os.path.exists(p):
                return p
    return shutil.which("msedge") or shutil.which("chrome")


def window_size() -> tuple[int, int]:
    """1240x800, or smaller so the window fits on a small / scaled laptop screen."""
    try:
        import ctypes
        u = ctypes.windll.user32
        w, h = u.GetSystemMetrics(16), u.GetSystemMetrics(17)   # usable screen area
        return max(800, min(1240, w - 30)), max(540, min(800, h - 10))
    except Exception:
        return 1240, 800


def open_window(url: str):
    browser = find_browser()
    if browser:
        w, h = window_size()
        profile = os.path.join(os.environ.get("LOCALAPPDATA", HERE), "EpisodeFlow", "window")
        subprocess.Popen([browser, f"--app={url}", f"--window-size={w},{h}", "--window-position=10,0",
                          f"--user-data-dir={profile}",
                          "--no-first-run", "--no-default-browser-check", "--disable-features=Translate"])
    else:
        webbrowser.open(url)


def on_drop(event):
    """A folder or files were dropped on the app window."""
    try:
        files = (event.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files if f.get("pywebviewFullPath")]
        if not paths:
            return
        err = STATE.open(paths)
        STATE.message = {"key": err.key, "values": err.values, "text": str(err)} if err else ""
        win = WEBVIEW["window"]
        if win is not None:
            win.evaluate_js("window.epfDropped && window.epfDropped()")
    except Exception:
        log_error()


def _bind_drop(window):
    from webview.dom import DOMEventHandler
    ignore = lambda e: None
    window.dom.document.events.dragenter += DOMEventHandler(ignore, True, True)
    window.dom.document.events.dragstart += DOMEventHandler(ignore, True, True)
    window.dom.document.events.dragover += DOMEventHandler(ignore, True, True, debounce=500)
    window.dom.document.events.drop += DOMEventHandler(on_drop, True, True)


def run_app_window(url: str) -> bool:
    """Show the UI in a real app window. False if pywebview isn't available or can't start."""
    try:
        import webview
    except ImportError:
        return False
    w, h = window_size()
    try:
        window = webview.create_window(f"EpisodeFlow", url, width=w, height=h, min_size=(860, 560))
        WEBVIEW["window"] = window
        # not private, so the chosen language is remembered between runs
        webview.start(_bind_drop, window, private_mode=False,
                      storage_path=os.path.join(ef.DATA_DIR, "window-data"))
        return True
    except Exception:
        log_error()
        WEBVIEW["window"] = None
        return False


def log_error():
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("\n[%Y-%m-%d %H:%M:%S]\n") + traceback.format_exc())
    except Exception:
        pass


def log_note(msg: str):
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
    except Exception:
        pass


def fatal(msg: str):
    log_error()
    if os.name == "nt":
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "EpisodeFlow", 0x10)
    else:
        print(msg, file=sys.stderr)


def main(open_ui=True):
    global SERVER
    SERVER = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{SERVER.server_address[1]}/?t={TOKEN}"
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if app_mode() == "portable" and ef.load_settings().get("shortcuts") == "yes":
        threading.Thread(target=lambda: portable_shortcuts("fix"), daemon=True).start()
    if ef.MIGRATED:
        log_note(f"moved old data next to the program into {ef.DATA_DIR}: {', '.join(ef.MIGRATED)}")
    if args:
        err = STATE.open(args)
        if err:
            STATE.message = {"key": err.key, "values": err.values, "text": str(err)}
    if open_ui and "--edge" not in sys.argv:
        server = threading.Thread(target=SERVER.serve_forever, daemon=True)
        server.start()
        if run_app_window(url):       # returns when the window is closed
            SERVER.shutdown()
            return
        # the app window couldn't start: fall back to Edge
        threading.Thread(target=watchdog, daemon=True).start()
        open_window(url)
        server.join()
        return
    threading.Thread(target=watchdog, daemon=True).start()
    if open_ui:
        open_window(url)
    else:
        print(url, flush=True)
    SERVER.serve_forever()


if __name__ == "__main__":
    try:
        main(open_ui="--no-window" not in sys.argv)
    except Exception as e:
        fatal(f"EpisodeFlow couldn't start:\n{e}\n\nDetails were saved to:\n{LOG_FILE}")
