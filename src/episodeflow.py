"""
EpisodeFlow - engine (Python)
https://github.com/  (see README.md)
Used by episodeflow_gui.py (the window) and can also run on its own in a console.
Renames episode files in a folder to "<Show> - S01E01.mkv", keeping the real
episode numbers. Shows a preview first and only renames after you confirm.

Usage:
    py episodeflow.py "D:\\Anime\\Frieren"          preview + rename a folder
    py episodeflow.py file1.mkv file2.mkv ...      only these files
    py episodeflow.py "D:\\Anime\\Frieren" --undo   undo the last rename there
"""
import json
import os
import re
import shutil
import sys
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field

# Change this if you want another format. Placeholders: {show} {season} {episode}
VERSION = "1.0.0"
REPO_URL = "https://github.com/kai39x/EpisodeFlow"   
USER_AGENT = f"EpisodeFlow/{VERSION}"

# ---------- Where settings, history and the AniList cache live ----------
def _app_dir() -> str:
    """Where the program itself is: next to EpisodeFlow.exe, or next to this file."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _data_dir() -> str:
    """The user's own data folder (AppData/Local/EpisodeFlow), so nothing shows up next to the program."""
    base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share")
    path = os.path.join(base, "EpisodeFlow")
    try:
        os.makedirs(path, exist_ok=True)
        return path
    except OSError:
        return _app_dir()


APP_DIR = _app_dir()
DATA_DIR = _data_dir()
DATA_FILES = ["settings.json", "history.json", "anilist_cache.json", "episodeflow_error.log", "window-data"]


def migrate_old_data(old_dir: str = APP_DIR, new_dir: str = DATA_DIR) -> list[str]:
    """Older versions kept their files next to the program: move them to the data folder."""
    moved = []
    if os.path.normcase(os.path.abspath(old_dir)) == os.path.normcase(os.path.abspath(new_dir)):
        return moved
    for name in DATA_FILES:
        old, new = os.path.join(old_dir, name), os.path.join(new_dir, name)
        if not os.path.exists(old):
            continue
        try:
            if not os.path.exists(new):
                shutil.move(old, new)
            elif name == "history.json":           # both exist: keep every entry from both
                with open(old, encoding="utf-8") as fh:
                    a = json.load(fh)
                with open(new, encoding="utf-8") as fh:
                    b = json.load(fh)
                seen, merged = set(), []
                for e in sorted(a + b, key=lambda e: e.get("time", "")):
                    key = (e.get("time"), e.get("folder"), json.dumps(e.get("items"), ensure_ascii=False))
                    if key not in seen:
                        seen.add(key)
                        merged.append(e)
                for i, e in enumerate(merged, 1):
                    e["id"] = i
                with open(new, "w", encoding="utf-8") as fh:
                    json.dump(merged, fh, ensure_ascii=False, indent=1)
                os.remove(old)
            elif name == "episodeflow_error.log":
                with open(old, encoding="utf-8", errors="ignore") as src_fh, open(new, "a", encoding="utf-8") as dst:
                    dst.write(src_fh.read())
                os.remove(old)
            elif os.path.isdir(old):               # window-data: the data folder's copy is newer
                shutil.rmtree(old, ignore_errors=True)
            else:                                  # settings / cache: the data folder's copy wins
                os.remove(old)
            moved.append(name)
        except Exception:
            pass
    return moved


MIGRATED = migrate_old_data()

# ---------- Settings ----------
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")
DEFAULT_TEMPLATE = "{show} - S{season}E{episode}"
# {show} = folder name, {season}/{episode} = 2 digits (S01E05), {s}/{e} = no padding (1x5)
PRESET_TEMPLATES = ["{show} - S{season}E{episode}", "S{season}E{episode}",
                    "{show} - {episode}", "{show} - {s}x{episode}"]
BAD_CHARS = '\\/:*?"<>|'


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    if validate_template(data.get("template", "")):
        data["template"] = DEFAULT_TEMPLATE
    return data


def save_settings(data: dict):
    with open(SETTINGS_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)


def validate_template(tpl: str) -> str:
    """'' if fine, otherwise an error key."""
    if not tpl or not tpl.strip():
        return "err_tpl_empty"
    if "{episode}" not in tpl and "{e}" not in tpl:
        return "err_tpl_episode"
    rest = re.sub(r"\{(?:show|season|episode|s|e)\}", "", tpl)
    if any(c in rest for c in BAD_CHARS) or "{" in rest or "}" in rest:
        return "err_tpl_chars"
    if len(tpl) > 120:
        return "err_tpl_long"
    return ""


def render_template(tpl: str, show: str, season: int, episode: int) -> str:
    out = (tpl.replace("{show}", re.sub(r'[\\/:*?"<>|]', " ", show))
              .replace("{season}", f"{season:02d}").replace("{s}", str(season))
              .replace("{episode}", f"{episode:02d}").replace("{e}", str(episode)))
    return re.sub(r"\s+", " ", out).strip(" .")


TEMPLATE = load_settings().get("template", DEFAULT_TEMPLATE)

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".mov", ".wmv", ".m4v", ".ts", ".flv"}
SUB_EXTS = {".srt", ".ass", ".ssa", ".sub", ".vtt"}
UNDO_FILE = ".episodeflow_undo.json"   # old versions kept the undo info here (still read)
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
HISTORY_MAX = 500


class EFError(RuntimeError):
    """An error the window can translate: key + values, English text for the console."""

    def __init__(self, key: str, text: str, **values):
        super().__init__(text)
        self.key, self.values = key, values

# ======================================================================
# 1) Cleaning
# ======================================================================
JUNK_TOKENS = [
    r"\d{3,4}p", r"4k", r"8k", r"uhd", r"hevc", r"avc", r"x26[45]", r"h\.?26[45]",
    r"aac", r"flac", r"opus", r"ac3", r"eac3", r"ddp?\d?\.?\d?", r"webrip", r"web-?dl",
    r"bluray", r"bdrip", r"cr", r"nf", r"amzn", r"multisub", r"multi-?subs?", r"dual-?audio",
    r"10bit", r"8bit", r"hdr", r"sdr", r"final(?: version)?", r"end", r"v\d",
    r"raw", r"uncensored", r"bd", r"fhd", r"hd", r"sd",
]
JUNK_RE = re.compile(r"\b(?:" + "|".join(JUNK_TOKENS) + r")\b", re.I)


def clean(name: str) -> str:
    """Strip extension, group tags, quality tags and hashes so only title + numbers remain."""
    s = os.path.splitext(name)[0]
    s = re.sub(r"\s*\(\d{1,2}\)\s*$", "", s)  # Windows duplicate marker "(1)"
    # Remove [..] and (..) blocks, but keep a lone number like [05] or (05)
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)",
               lambda m: m.group()[1:-1] if re.fullmatch(r"[\[(]\s*\d{1,3}\s*[\])]", m.group()) else " ", s)
    s = re.sub(r"[._]", " ", s)
    s = JUNK_RE.sub(" ", s)
    s = re.sub(r"\b[0-9a-f]{8}\b", " ", s, flags=re.I)  # loose CRC hashes
    return re.sub(r"\s+", " ", s).strip()


# ======================================================================
# 2) Detection of a single file
# ======================================================================
ROMAN = {"ii": 2, "iii": 3, "iv": 4, "v": 5}
PATTERNS_SE = [
    re.compile(r"\bS(\d{1,2})\s*-?\s*E[Pp]?\s*(\d{1,4})\b", re.I),  # S01E05, S4 E21
    re.compile(r"\b(\d{1,2})x(\d{1,3})\b", re.I),                    # 4x22
]
SEASON_PATTERNS = [
    re.compile(r"\bSeason\s*(\d{1,2})\b", re.I),
    re.compile(r"(?<=[A-Za-z])(\d{1,2})S(?=P\d|\b)"),                 # RZKHIS2S, RZKHIS2SP2
    re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)\s+Season\b", re.I),
    re.compile(r"\bS(\d{1,2})\b", re.I),
    re.compile(r"\b(II|III|IV)\b(?=\s*(?:-|Episode|Ep\b|$))", re.I),
]
EPISODE_PATTERNS = [
    re.compile(r"\b(?:Episode|Ep|E)\s*(\d{1,4})\b", re.I),  # Episode 09, Ep 08, E22
    re.compile(r"(?:^|\s)-\s*(\d{1,4})(?!\d)"),             # " - 05", " - 04-"
]
PART_PATTERNS = [
    re.compile(r"\b(?:Part|Cour)\s*(\d)\b", re.I),
    re.compile(r"(?<=\dS)P(\d)\b"),                                    # ...2SP2
]
SPECIAL_RE = re.compile(r"\b(OVA|OAD|Specials?|SP)(?:\s*-?\s*(\d{1,3}))?(?!\w)", re.I)
HALF_RE = re.compile(r"(?:\bE|\bEp\.?\s?|\bEpisode\s|\s-\s)(\d{1,3})\.5(?!\d)", re.I)   # "Ep 12.5", " - 12.5"
STANDALONE = re.compile(r"(?<![\w-])(\d{1,4})(?![\w-])")


# Every note has a key + values, so the window can translate it. English text is for the console.
NOTES = {
    "half_special": "Episode {n}.5 is treated as a special (Season 0)",
    "lone_number": "Episode number guessed from the only number in the name",
    "no_number": "No episode number found, so it won't be renamed",
    "season_neighbours": "Season {s} guessed from the files around it",
    "season_folder": "Season {s} taken from the folder name",
    "season_assumed": "No season in the name, so Season 1 was assumed",
    "special_numbered": "Special with no number, numbered {n} by name order",
    "season_title": "Season {s}: the name matches '{t}' on AniList",
    "part_anilist": "Part {p} starts after episode {n} on AniList, so +{n} was added",
    "part_no_base": "Part {p}, with no earlier part here to count from. If its numbers restart at 1, shift it",
    "part_folder": "Part {p} restarts at 1, so +{n} was added (counted from the files here). "
                   "If Part {q} isn't complete here, change the shift",
    "edited": "Edited by you",
    "shifted": "Shifted +{n} by you",
    "kept_both": "Kept next to another copy of this episode",
}


def add_note(r, key: str, info: bool = False, **values):
    """Attach a note (or an info line) to a file, in English plus a translatable key."""
    text = NOTES[key].format(**values)
    if info:
        r.info = (r.info + ". " if r.info else "") + text
        r.info_keys.append([key, values])
    else:
        r.notes.append(text)
        r.note_keys.append([key, values])


def reset_notes(r):
    r.notes, r.note_keys, r.info, r.info_keys = [], [], "", []


@dataclass
class Result:
    original: str
    season: int | None = None
    episode: int | None = None
    season_explicit: bool = False
    confidence: str = "high"          # high / medium / none
    notes: list = field(default_factory=list)
    conflict: bool = False
    skipped: bool = False
    part: int | None = None           # Part / Cour number if the name has one
    raw_episode: int | None = None    # number exactly as found in the name
    info: str = ""                    # extra line shown in the preview (e.g. AniList)
    special: bool = False             # OVA / SP / x.5 episode -> Season 0
    suffix: str = ""                  # " (1080p)" when you keep two copies of one episode
    note_keys: list = field(default_factory=list)
    info_keys: list = field(default_factory=list)


def find_season(text: str):
    for p in SEASON_PATTERNS:
        m = p.search(text)
        if m:
            g = m.group(1)
            return ROMAN.get(g.lower()) or int(g)
    return None


def detect(name: str) -> Result:
    r = detect_core(name)
    r.raw_episode = r.episode
    # A copy you chose to keep earlier: "Show - S03E09 (1080p).mkv" keeps its " (1080p)"
    m = re.search(r"\d( \((?:4K|1440p|1080p|720p|480p|\d{1,2})\))$", os.path.splitext(name)[0])
    if m:
        r.suffix = m.group(1)
    s = clean(name)
    for p in PART_PATTERNS:
        m = p.search(s)
        if m:
            r.part = int(m.group(1))
            break
    if r.part is None:
        m = re.search(r"\bPart\s*(II|III|IV)\b", s)
        if m:
            r.part = ROMAN_ALL[m.group(1).lower()]
        elif re.search(r"\bkouhen\b", s, re.I):   # Japanese for "second half"
            r.part = 2
        elif re.search(r"\bzenpen\b", s, re.I):   # "first half"
            r.part = 1
    return r


def detect_core(name: str) -> Result:
    r = Result(name)
    s = clean(name)

    # Specials first: "12.5" recap episodes, OVA, OAD, SP, Special -> Season 0
    raw = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", os.path.splitext(name)[0])
    m = HALF_RE.search(raw)
    if m:
        r.season, r.season_explicit, r.special = 0, True, True
        add_note(r, "half_special", n=int(m.group(1)))
        r.confidence = "medium"
        return r
    m = SPECIAL_RE.search(s)
    if m:
        r.season, r.season_explicit, r.special = 0, True, True
        if m.group(2):
            r.episode = int(m.group(2))
        else:
            e = EPISODE_PATTERNS[0].search(s) or EPISODE_PATTERNS[1].search(s)
            r.episode = int(e.group(1)) if e else None
        if r.episode is None:
            r.confidence = "medium"
        return r

    for p in PATTERNS_SE:
        m = p.search(s)
        if m:
            r.season, r.episode, r.season_explicit = int(m.group(1)), int(m.group(2)), True
            r.special = r.season == 0
            return r
    season = find_season(s)
    if season is not None:
        r.season, r.season_explicit = season, True
    for p in EPISODE_PATTERNS:
        m = p.search(s)
        if m:
            r.episode = int(m.group(1))
            return r
    # a lone number; 4 digits are fine for long runners (Conan 1150) but not years (2024)
    nums = [n for n in STANDALONE.findall(s) if not (len(n) == 4 and 1900 <= int(n) <= 2099)]
    if nums:
        r.episode, r.confidence = int(nums[-1]), "medium"
        add_note(r, "lone_number")
    else:
        r.confidence = "none"
        add_note(r, "no_number")
    return r


# ======================================================================
# 2b) AniList lookup (episode counts per season / part)
# ======================================================================
ANILIST_URL = "https://graphql.anilist.co"
CACHE_FILE = os.path.join(DATA_DIR, "anilist_cache.json")
CACHE_DAYS = 7          # finished shows
CACHE_DAYS_AIRING = 1   # shows still airing change every week
CACHE_VERSION = 4
GOOD_FORMATS = {"TV", "ONA"}   # movies, OVAs, specials and shorts are ignored

_MEDIA_FIELDS = """
  id format episodes synonyms
  title { romaji english }
  startDate { year month }
  nextAiringEpisode { episode }
  coverImage { extraLarge large }
  relations { edges { relationType node { id type format startDate { year month } } } }
"""
_SEARCH_Q = "query($s:String){Page(perPage:8){media(search:$s,type:ANIME,sort:SEARCH_MATCH){" + _MEDIA_FIELDS + "}}}"
_ID_Q = "query($id:Int){Media(id:$id,type:ANIME){" + _MEDIA_FIELDS + "}}"

ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6}
ROMAN_ALL = {"ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6}


# AniList allows 90 requests a minute (30 while their API is "degraded"). We stay under 25 and
# space requests out, so opening a folder with many shows never gets the user blocked.
_RATE_WINDOW, _RATE_MAX, _RATE_GAP = 60.0, 25, 0.7
_recent: list[float] = []
_rate_lock = __import__("threading").Lock()


def _wait_for_slot():
    with _rate_lock:
        now = time.monotonic()
        while _recent and now - _recent[0] > _RATE_WINDOW:
            _recent.pop(0)
        wait = 0.0
        if len(_recent) >= _RATE_MAX:
            wait = _RATE_WINDOW - (now - _recent[0]) + 0.1
        elif _recent:
            wait = max(0.0, _RATE_GAP - (now - _recent[-1]))
        _recent.append(now + wait)
    if wait > 0:
        time.sleep(wait)


def _anilist_post(query: str, variables: dict) -> dict:
    body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = urllib.request.Request(ANILIST_URL, data=body, headers={
        "Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT})
    for attempt in range(3):
        _wait_for_slot()
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 2:          # told to slow down: wait as long as AniList asks
                time.sleep(min(70, int(e.headers.get("Retry-After", "30") or 30) + 1))
                continue
            raise


def _date_key(node: dict):
    d = node.get("startDate") or {}
    return (d.get("year") or 9999, d.get("month") or 0)


def _next_in_chain(media: dict, relation: str):
    cands = [e["node"] for e in media["relations"]["edges"]
             if e["relationType"] == relation and e["node"]["type"] == "ANIME"
             and e["node"]["format"] in GOOD_FORMATS]
    if not cands:
        return None
    cands.sort(key=_date_key)
    return cands[-1] if relation == "PREQUEL" else cands[0]


def fetch_chain(search: str, post=_anilist_post) -> list[dict] | None:
    """Find the anime, walk back to its first TV season, then forward through every sequel."""
    found = post(_SEARCH_Q, {"s": search})["Page"]["media"]
    found = [m for m in found if m["format"] in GOOD_FORMATS]
    if not found:
        return None

    # Does the folder name spell out one exact entry? ("BLEACH Sennen Kessen-hen - Kashin-tan")
    text = " " + _norm(search) + " "
    anchor, best = None, 0
    for m in found:
        for t in (m["title"].get("romaji"), m["title"].get("english")):
            n = _norm(t)
            if n and f" {n} " in text and len(n) > best:
                anchor, best = m, len(n)

    if anchor is not None and _next_in_chain(anchor, "PREQUEL"):
        # The folder is about a later season/arc on its own: count from there, not from season 1
        media = anchor
    else:
        media, seen = anchor or found[0], set()
        while (prev := _next_in_chain(media, "PREQUEL")) and prev["id"] not in seen and len(seen) < 20:
            seen.add(media["id"])
            media = post(_ID_Q, {"id": prev["id"]})["Media"]
    chain, seen = [media], {media["id"]}
    while (nxt := _next_in_chain(chain[-1], "SEQUEL")) and nxt["id"] not in seen and len(chain) < 20:
        seen.add(nxt["id"])
        chain.append(post(_ID_Q, {"id": nxt["id"]})["Media"])
    return chain


def _title_numbers(titles: list[str]):
    """Read season / part numbers written in an AniList title."""
    season = part = None
    for t in titles:
        if not t:
            continue
        if season is None:
            m = (re.search(r"\b(\d+)(?:st|nd|rd|th)\s+Season\b", t, re.I)
                 or re.search(r"\bSeason\s*(\d+)\b", t, re.I))
            if m:
                season = int(m.group(1))
            else:
                m = re.search(r"\b(first|second|third|fourth|fifth|sixth)\s+Season\b", t, re.I)
                if m:
                    season = ORDINAL_WORDS[m.group(1).lower()]
                else:
                    m = re.search(r"\b(II|III|IV|V|VI)\b(?!\s*Part)", t)
                    if m:
                        season = ROMAN_ALL[m.group(1).lower()]
        if part is None:
            m = (re.search(r"\b(?:Part|Cour)\s*(\d+)\b", t, re.I)
                 or re.search(r"\b(\d+)(?:st|nd|rd|th)\s+(?:Part|Cour)\b", t, re.I))
            if m:
                part = int(m.group(1))
            else:
                m = re.search(r"\bPart\s*(II|III|IV)\b", t)
                if m:
                    part = ROMAN_ALL[m.group(1).lower()]
                elif re.search(r"\bkouhen\b", t, re.I):
                    part = 2
                elif re.search(r"\bzenpen\b", t, re.I):
                    part = 1
    return season, part


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (s or "").lower())).strip()


_PART_WORDS = re.compile(r"\b(?:part|cour)\s*(?:\d+|ii|iii|iv)\b|\b\d+(?:st|nd|rd|th)\s+(?:part|cour)\b|\bzenpen\b|\bkouhen\b")


def _title_keys(m: dict, root: dict) -> list[str]:
    """What makes this entry's title different from season 1 ('final season', 'shimetsu kaiyuu')."""
    keys = []
    for field_ in ("english", "romaji"):
        t, r = _norm(m["title"].get(field_)), _norm(root["title"].get(field_))
        if t and r and t.startswith(r) and t != r:
            k = _PART_WORDS.sub(" ", t[len(r):])
            k = re.sub(r"\s+", " ", k).strip()
            if len(k) >= 4 and re.search(r"[a-z]", k):
                keys.append(k)
    return keys


def label_chain(chain: list[dict]) -> list[dict]:
    """Turn the AniList chain into seasons/parts: [{title, episodes, season, part, keys}, ...]."""
    out, prev_season, prev_part = [], 0, 0
    for m in chain:
        titles = [m["title"].get("english"), m["title"].get("romaji")]
        season, part = _title_numbers(titles)
        if season is None:
            season = prev_season if (part and part >= 2 and prev_season) else prev_season + 1
        if part is None:
            part = prev_part + 1 if season == prev_season else 1
        nae = m.get("nextAiringEpisode") or {}
        out.append({"title": m["title"].get("english") or m["title"].get("romaji"),
                    "episodes": m.get("episodes"), "season": season, "part": part,
                    "aired": (nae["episode"] - 1) if nae.get("episode") else None,
                    "cover": ((m.get("coverImage") or {}).get("extraLarge") or (m.get("coverImage") or {}).get("large")),
                    "keys": _title_keys(m, chain[0])})
        prev_season, prev_part = season, part
    return out


def _load_cache() -> dict:
    try:
        with open(CACHE_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(cache, fh, ensure_ascii=False, indent=1)
    except Exception:
        pass


def title_candidates(show: str, files: list[str]) -> list[str]:
    """Folder name first, then the most common title found inside the file names."""
    cands = [show]
    counts = {}
    for f in files:
        s = clean(f)
        s = re.split(r"\s-\s|\bS\d{1,2}\b|\bS\d{1,2}E|\bSeason\b|\b\d+(?:st|nd|rd|th)\s+Season\b|"
                     r"\b(?:Episode|Ep|E)\s*\d|\bPart\b|\bCour\b|\b\d{1,4}\b", s, maxsplit=1, flags=re.I)[0]
        s = s.strip(" -!")
        if len(s) >= 3:
            counts[s] = counts.get(s, 0) + 1
    for t, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:2]:
        if t.lower() != show.lower():
            cands.append(t)
    return cands


class AniListLookup:
    """Lazy: goes online the first time something asks (cached for later runs)."""

    def __init__(self, show: str, files: list[str], post=None, use_cache=True):
        self.show, self.files, self.post, self.use_cache = show, files, post, use_cache
        self.labels, self.status, self._done = None, "", False
        self.status_key = ""   # saved / matched / offline / nomatch

    def _load(self):
        self._done = True
        cache = _load_cache() if self.use_cache else {}
        for term in title_candidates(self.show, self.files):
            key = term.lower()
            hit = cache.get(key)
            airing = hit and any(e["episodes"] is None for e in hit.get("labels", []))
            max_age = (CACHE_DAYS_AIRING if airing else CACHE_DAYS) * 86400
            if hit and hit.get("v") == CACHE_VERSION and time.time() - hit["time"] < max_age:
                self.labels, self.status = hit["labels"], f"AniList (saved): {hit['labels'][0]['title']}"
                self.status_key = "saved"
                return
            try:
                chain = fetch_chain(term, self.post or _anilist_post)
            except Exception:
                self.status = "AniList: couldn't connect, counting from the folder instead"
                self.status_key = "offline"
                return
            if chain:
                self.labels = label_chain(chain)
                self.status = f"AniList: {self.labels[0]['title']}  (searched: '{term}')"
                self.status_key = "matched"
                if self.use_cache:
                    cache[key] = {"time": time.time(), "labels": self.labels, "v": CACHE_VERSION}
                    _save_cache(cache)
                return
        self.status = f"AniList: no match for '{self.show}', counting from the folder instead"
        self.status_key = "nomatch"

    def offset(self, season: int, part: int):
        """Episodes before `part` inside `season`, or None if AniList can't tell."""
        if not self._done:
            self._load()
        if not self.labels:
            return None
        earlier = [e for e in self.labels if e["season"] == season and e["part"] < part]
        if len(earlier) != part - 1 or any(e["episodes"] is None for e in earlier):
            return None
        return sum(e["episodes"] for e in earlier)

    def season_parts(self, season: int):
        """Episode count of each part of a season, e.g. [13, 12]. None if unknown."""
        if not self._done:
            self._load()
        if not self.labels:
            return None
        sizes = []
        for e in sorted((e for e in self.labels if e["season"] == season), key=lambda e: e["part"]):
            n = e["episodes"] if e["episodes"] is not None else e.get("aired")
            if n is None:
                return None
            sizes.append(n)
        return sizes or None

    def season_airing(self, season: int) -> bool:
        if not self._done:
            self._load()
        return bool(self.labels) and any(e["season"] == season and e["episodes"] is None for e in self.labels)

    def cover(self) -> str | None:
        if not self._done:
            self._load()
        return self.labels[0].get("cover") if self.labels else None

    def season_for_name(self, name: str):
        """Match a file name to an AniList entry by its distinctive title words."""
        if not self._done:
            self._load()
        if not self.labels:
            return None
        raw = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", os.path.splitext(name)[0])  # keep words like 'Final'
        text = " " + _norm(raw) + " "
        best = None
        for e in self.labels:
            for k in e.get("keys", []):
                if f" {k} " in text and (best is None or len(k) > best[0]):
                    best = (len(k), e["season"], e["title"])
        return best[1:] if best else None

    def summary(self) -> str:
        if not self.labels:
            return self.status
        chain = " | ".join(f"S{e['season']}" + (f" P{e['part']}" if e["part"] > 1 else "")
                           + f" ({e['episodes'] if e['episodes'] is not None else '?'})" for e in self.labels)
        return f"{self.status}\n         {chain}"


# ======================================================================
# 3) Folder-level logic
# ======================================================================
def show_from_folder(folder: str) -> str:
    """Folder name -> show name ("Grand Blue Season 3" -> "Grand Blue")."""
    s = os.path.basename(os.path.normpath(folder))
    s = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", s)
    s = re.sub(r"[._]", " ", s)
    s = re.sub(r"\b(?:Season\s*\d+|S\d{1,2}|\d+(?:st|nd|rd|th)\s+Season|Part\s*\d+)\b", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip(" -")
    return s or "Show"


def resolve_batch(files: list[str], folder_season: int | None = None, lookup=None) -> list[Result]:
    results = [detect(f) for f in files]
    if lookup:
        for r in results:
            if not r.season_explicit and r.part and r.part >= 2 and r.episode is not None:
                hit = lookup.season_for_name(r.original)
                if hit:
                    r.season, r.season_explicit = hit[0], True
                    add_note(r, "season_title", info=True, s=hit[0], t=hit[1])
    known = [r for r in results if r.season_explicit and r.episode is not None and not r.special]
    known_seasons = sorted({k.season for k in known})
    unmarked_eps = sorted(x.episode for x in results if not x.season_explicit and x.episode)

    for r in results:
        if r.season_explicit or r.episode is None or r.special:
            continue
        best = None
        # a) the episode sits inside / right next to a known season's episodes
        for season in known_seasons:
            eps = [k.episode for k in known if k.season == season]
            if r.episode in eps:
                continue
            if min(eps) <= r.episode <= max(eps) or min(abs(r.episode - e) for e in eps) <= 3:
                best = season
                break
        # b) the episode continues a run of unmarked files that touches a known season
        if best is None:
            for season in known_seasons:
                eps = {k.episode for k in known if k.season == season}
                run = set(eps)
                for e in unmarked_eps:
                    if any(abs(e - x) <= 1 for x in run):
                        run.add(e)
                if r.episode in run and r.episode not in eps:
                    best = season
                    break
        if best is not None:
            r.season = best
            add_note(r, "season_neighbours", s=best)
            if r.part and r.part >= 2:
                r.confidence = "medium"  # 'Part 2' with no season is ambiguous
        elif folder_season:
            r.season = folder_season
            add_note(r, "season_folder", s=folder_season)
        else:
            r.season = 1
            add_note(r, "season_assumed")
            if known:
                r.confidence = "medium"

    # Specials without a number: give them the next free numbers, in name order
    numbered = {r.episode for r in results if r.special and r.episode is not None}
    nxt = max(numbered, default=0) + 1
    for r in sorted((r for r in results if r.special and r.episode is None), key=lambda r: r.original.lower()):
        r.episode = r.raw_episode = nxt
        add_note(r, "special_numbered", n=nxt)
        nxt += 1

    apply_part_offsets(results, lookup)
    mark_conflicts(results)
    return results


def apply_part_offsets(results: list[Result], lookup=None):
    """
    Part 2 / Cour 2 files often restart at episode 1. If the earlier part of the
    same season is in the folder, continue from its last episode
    (part 1 ends at 12 -> part 2 "01" becomes 13).
    """
    for season in sorted({r.season for r in results if r.episode is not None and not r.special}):
        parts = sorted({r.part for r in results if r.season == season and r.part and r.part >= 2 and r.episode})
        for part in parts:
            group = [r for r in results if r.season == season and r.part == part and r.episode]
            earlier = [r.episode for r in results
                       if r.season == season and r.episode and r not in group and (r.part is None or r.part < part)]
            first = min(r.episode for r in group)
            known = lookup.offset(season, part) if lookup else None
            if known is not None:
                if first > known:
                    continue  # numbered continuously already
                for r in group:
                    r.episode = r.raw_episode + known
                    add_note(r, "part_anilist", info=True, p=part, n=known)
                continue
            if not earlier:
                for r in group:
                    r.confidence = "medium"
                    add_note(r, "part_no_base", p=part)
                continue
            if first > max(earlier):
                continue  # already numbered continuously (13, 14...), nothing to do
            offset = max(earlier)
            for r in group:
                r.episode = r.raw_episode + offset
                r.confidence = "medium"
                add_note(r, "part_folder", p=part, n=offset, q=part - 1)


def mark_conflicts(results: list[Result]) -> int:
    for r in results:
        r.conflict = False
    seen = {}
    for r in results:
        if r.episode is None or r.skipped:
            continue
        # same final name = conflict (also catches formats without a season: S1E01 and S2E01 -> "Show - 01")
        key = (render_template(TEMPLATE, "x", r.season, r.episode).lower(), r.suffix)
        if key in seen:
            r.conflict = seen[key].conflict = True
        seen[key] = r
    return sum(r.conflict for r in results)


def new_base(r: Result, show: str) -> str:
    return render_template(TEMPLATE, show, r.season, r.episode)


def set_template(tpl: str):
    """Save a new file name format (raises EFError if it can't work)."""
    global TEMPLATE
    err = validate_template(tpl)
    if err:
        raise EFError(err, "This file name format can't be used.")
    TEMPLATE = tpl
    data = load_settings()
    data["template"] = tpl
    save_settings(data)


# ======================================================================
# 4) Renaming (with subtitles, two-phase, undo)
# ======================================================================
def matching_subs(folder: str, video_name: str, all_files: list[str]):
    """Subs that share the video's base name: 'x.srt', 'x.ar.srt', 'x.en.ass'..."""
    base = os.path.splitext(video_name)[0]
    out = []
    for f in all_files:
        if os.path.splitext(f)[1].lower() in SUB_EXTS and f.startswith(base + "."):
            out.append((f, f[len(base):]))  # suffix like ".ar.srt"
    return out


def safe_rename(folder: str, pairs: list[tuple[str, str]]):
    """Rename old->new in two phases so swaps (A->B, B->A) never collide."""
    temps = []
    for i, (old, new) in enumerate(pairs):
        tmp = f"__epf_tmp_{i}__{os.path.splitext(old)[1]}"
        os.rename(os.path.join(folder, old), os.path.join(folder, tmp))
        temps.append((tmp, new))
    for tmp, new in temps:
        os.rename(os.path.join(folder, tmp), os.path.join(folder, new))


# ---------- History (every rename and every file sent to the Recycle Bin) ----------
def _same_folder(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def load_history() -> list[dict]:
    try:
        with open(HISTORY_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return []


def _save_history(entries: list[dict]):
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(entries[-HISTORY_MAX:], fh, ensure_ascii=False, indent=1)
    os.replace(tmp, HISTORY_FILE)


def log_history(kind: str, folder: str, show: str, items: list) -> dict:
    """kind: 'rename' (items = [[old, new], ...]) or 'recycle' (items = [file, ...])."""
    entries = load_history()
    entry = {"id": max((e["id"] for e in entries), default=0) + 1, "time": time.strftime("%Y-%m-%d %H:%M"),
             "kind": kind, "folder": os.path.abspath(folder), "show": show, "items": items, "undone": False}
    entries.append(entry)
    _save_history(entries)
    return entry


def _latest_rename(folder: str) -> dict | None:
    for e in reversed(load_history()):
        if e["kind"] == "rename" and not e["undone"] and _same_folder(e["folder"], folder):
            return e
    return None


def _reverse(folder: str, pairs: list):
    gone = [new for _, new in pairs if not os.path.exists(os.path.join(folder, new))]
    if gone:
        raise EFError("err_undo_moved", f"Can't undo: this file was moved or renamed since: {gone[0]}", name=gone[0])
    news = {new for _, new in pairs}
    taken = [old for old, _ in pairs if old not in news and os.path.exists(os.path.join(folder, old))]
    if taken:
        raise EFError("err_undo_taken", f"Can't undo: a file already has the old name: {taken[0]}", name=taken[0])
    safe_rename(folder, [(new, old) for old, new in pairs])


def undo_entry(entry_id: int) -> int:
    """Undo one rename from the history. Returns how many files got their old names back."""
    entries = load_history()
    e = next((x for x in entries if x["id"] == entry_id), None)
    if not e or e["kind"] != "rename" or e["undone"]:
        raise EFError("err_undo_none", "There's nothing to undo for this entry.")
    if not os.path.isdir(e["folder"]):
        raise EFError("err_undo_folder", f"This folder doesn't exist any more: {e['folder']}", name=e["folder"])
    _reverse(e["folder"], e["items"])
    e["undone"] = True
    _save_history(entries)
    return len(e["items"])


def can_undo(folder: str) -> bool:
    return _latest_rename(folder) is not None or os.path.exists(os.path.join(folder, UNDO_FILE))


def undo(folder: str) -> int:
    """Put the last rename in this folder back. Returns how many files were restored."""
    e = _latest_rename(folder)
    if e:
        return undo_entry(e["id"])
    path = os.path.join(folder, UNDO_FILE)   # left by an older version
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as fh:
        pairs = json.load(fh)
    _reverse(folder, pairs)
    os.remove(path)
    return len(pairs)


# ---------- Duplicates (two files for the same episode) ----------
QUALITY = [(r"\b(?:2160p|4k|uhd)\b", 2160, "4K"), (r"\b1440p\b", 1440, "1440p"),
           (r"\b(?:1080p|fhd)\b", 1080, "1080p"), (r"\b(?:720p|hd)\b", 720, "720p"),
           (r"\b(?:480p|sd)\b", 480, "480p")]


def quality(name: str) -> tuple[int, str]:
    s = re.sub(r"[._\-\[\]()]", " ", os.path.splitext(name)[0].lower())
    for pattern, value, label in QUALITY:
        if re.search(pattern, s):
            return value, label
    return 0, ""


def duplicate_groups(plan: "ShowPlan") -> list[dict]:
    """Files that would get the same name, with which copy looks best (resolution, then size)."""
    mark_conflicts(plan.results)
    groups = {}
    for i, r in enumerate(plan.ordered):
        if r.conflict:
            groups.setdefault((r.season, r.episode, r.suffix), []).append(i)
    out = []
    for (season, episode, _), rows in sorted(groups.items(), key=lambda kv: (kv[0][0] or 0, kv[0][1] or 0)):
        if len(rows) < 2:
            continue   # clashes only because of the name format, not two copies of one episode
        files = []
        for i in rows:
            r = plan.ordered[i]
            try:
                size = os.path.getsize(os.path.join(plan.folder, r.original))
            except OSError:
                size = 0
            q, label = quality(r.original)
            files.append({"row": i, "original": r.original, "quality": q, "res": label, "size": size, "best": False})
        max(files, key=lambda f: (f["quality"], f["size"]))["best"] = True
        out.append({"season": season, "episode": episode, "files": files})
    return out


def keep_both(plan: "ShowPlan", rows: list[int]):
    """Keep every copy: the best keeps the plain name, the others get ' (1080p)' or ' (2)'."""
    group = [g for g in duplicate_groups(plan) if {f["row"] for f in g["files"]} & set(rows)]
    for g in group:
        used = set()
        for f in sorted(g["files"], key=lambda f: not f["best"]):
            r = plan.ordered[f["row"]]
            if f["best"]:
                r.suffix = ""
                continue
            label = f" ({f['res']})" if f["res"] and f" ({f['res']})" not in used else ""
            n = 2
            while not label or label in used:
                label, n = f" ({n})", n + 1
            used.add(label)
            r.suffix = label
            add_note(r, "kept_both")
    mark_conflicts(plan.results)


def send_to_recycle_bin(paths: list[str]):
    """Delete to the Recycle Bin so it can be restored. (Outside Windows: a temp 'trash' folder.)"""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class SHFILEOPSTRUCTW(ctypes.Structure):
            _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                        ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", wintypes.BOOL),
                        ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]
        buf = ctypes.create_unicode_buffer("\0".join(os.path.abspath(p) for p in paths) + "\0\0")
        op = SHFILEOPSTRUCTW(None, 3, ctypes.cast(buf, wintypes.LPCWSTR), None, 0x40 | 0x10 | 0x4 | 0x400, False, None, None)
        result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
        left = [p for p in paths if os.path.exists(p)]
        if result != 0 or op.fAnyOperationsAborted or left:
            raise EFError("err_recycle", f"Couldn't move to the Recycle Bin: {os.path.basename((left or paths)[0])}",
                          name=os.path.basename((left or paths)[0]))
    else:
        import tempfile
        trash = os.path.join(tempfile.gettempdir(), "episodeflow_trash")
        os.makedirs(trash, exist_ok=True)
        for p in paths:
            shutil.move(p, os.path.join(trash, f"{time.time():.6f}_{os.path.basename(p)}"))


def recycle_files(plan: "ShowPlan", rows: list[int]) -> int:
    """Send these episodes (and their subtitles) to the Recycle Bin."""
    names = []
    for i in rows:
        r = plan.ordered[i]
        names.append(r.original)
        names += [s for s, _ in matching_subs(plan.folder, r.original, plan.all_files)]
    send_to_recycle_bin([os.path.join(plan.folder, n) for n in names])
    log_history("recycle", plan.folder, plan.show, names)
    return len(names)


# ======================================================================
# 5) Plan API (what the window uses)
# ======================================================================
@dataclass
class ShowPlan:
    folder: str
    show: str
    folder_season: int | None
    all_files: list
    results: list
    lookup: "AniListLookup | None"
    ordered: list            # display order, stays the same while you edit
    sizes: dict = field(default_factory=dict)   # file name -> bytes


def _sort_key(r: Result):
    return (r.episode is None, r.special, r.season or 0, r.episode or 0)


def analyze(folder: str, only: list[str] | None = None, post=None, use_cache=True, online=True) -> ShowPlan:
    all_files = sorted(os.listdir(folder))
    videos = [f for f in all_files if os.path.splitext(f)[1].lower() in VIDEO_EXTS]
    if only:
        videos = [f for f in videos if f in only]
    show = show_from_folder(folder)
    folder_season = find_season(clean(os.path.basename(os.path.normpath(folder))) + " ")
    lookup = AniListLookup(show, videos, post=post, use_cache=use_cache) if (online and videos) else None
    results = resolve_batch(videos, folder_season, lookup)
    plan = ShowPlan(folder, show, folder_season, all_files, results, lookup, sorted(results, key=_sort_key))
    for f in all_files:
        try:
            plan.sizes[f] = os.path.getsize(os.path.join(folder, f))
        except OSError:
            pass
    missing_episodes(plan)   # warms up AniList so the totals are ready
    return plan


def target_name(plan: ShowPlan, r: Result) -> str | None:
    if r.skipped or r.episode is None:
        return None
    return new_base(r, plan.show) + r.suffix + os.path.splitext(r.original)[1]


def plan_pairs(plan: ShowPlan) -> list[tuple[str, str]]:
    pairs = []
    for r in plan.ordered:
        target = target_name(plan, r)
        if target and target != r.original:
            pairs.append((r.original, target))
            for sub, suffix in matching_subs(plan.folder, r.original, plan.all_files):
                pairs.append((sub, new_base(r, plan.show) + r.suffix + suffix))
    return pairs


def plan_status(plan: ShowPlan) -> str:
    """empty / conflict / review / ready / done"""
    if not plan.results:
        return "empty"
    if mark_conflicts(plan.results):
        return "conflict"
    pairs = plan_pairs(plan)
    if not pairs:
        return "done"
    if any(r.confidence != "high" and not r.skipped and target_name(plan, r) != r.original for r in plan.results):
        return "review"
    return "ready"


def apply_plan(plan: ShowPlan) -> int:
    """Rename everything in the plan. Returns the number of files renamed."""
    if mark_conflicts(plan.results):
        raise EFError("err_conflicts", "Some files share the same episode number. Fix them first.")
    pairs = plan_pairs(plan)
    if not pairs:
        return 0
    sources = {o for o, _ in pairs}
    clashes = [n for _, n in pairs if os.path.exists(os.path.join(plan.folder, n)) and n not in sources]
    if clashes:
        raise EFError("err_exists", f"A file with this name already exists: {clashes[0]}", name=clashes[0])
    safe_rename(plan.folder, pairs)
    log_history("rename", plan.folder, plan.show, [list(p) for p in pairs])
    legacy = os.path.join(plan.folder, UNDO_FILE)
    if os.path.exists(legacy):
        os.remove(legacy)   # the history replaces the old per-folder undo file
    return len(pairs)


def edit_result(r: Result, season: int | None, episode: int | None, skip: bool = False):
    if skip:
        r.skipped = True
        return
    r.skipped = False
    if season is not None:
        r.season = season
        r.special = season == 0
    if episode is not None:
        r.episode = episode
    r.season_explicit, r.confidence, r.suffix = True, "high", ""
    reset_notes(r)
    add_note(r, "edited")


def missing_episodes(plan: ShowPlan) -> list[dict]:
    """
    Per season in the folder: which episodes aren't here.
    Uses AniList's episode count when it fits, otherwise counts up to the highest episode found.
    """
    out = []
    seasons = sorted({r.season for r in plan.results
                      if r.episode is not None and not r.skipped and not r.special and r.season})
    for s in seasons:
        have = sorted({r.episode for r in plan.results
                       if r.season == s and r.episode is not None and not r.skipped and not r.special})
        parts = plan.lookup.season_parts(s) if plan.lookup else None
        total = sum(parts) if parts else None
        if total and max(have) <= total:
            source = "anilist"
        else:
            total, parts, source = max(have), None, "folder"
        missing = [e for e in range(1, total + 1) if e not in set(have)]
        airing = bool(plan.lookup and source == "anilist" and plan.lookup.season_airing(s))
        out.append({"season": s, "have": have, "total": total, "parts": parts,
                    "missing": missing, "source": source, "airing": airing})
    return out


def ranges(nums: list[int]) -> str:
    """[1,2,3,5,7,8] -> 'E01-03, E05, E07-08'"""
    out, i = [], 0
    while i < len(nums):
        j = i
        while j + 1 < len(nums) and nums[j + 1] == nums[j] + 1:
            j += 1
        out.append(f"E{nums[i]:02d}" + (f"-{nums[j]:02d}" if j > i else ""))
        i = j + 1
    return ", ".join(out)


def storage_summary(plan: ShowPlan) -> dict:
    """How much space the show takes: total, per season, and its biggest files."""
    seasons, total, subs = {}, 0, 0
    for r in plan.results:
        size = plan.sizes.get(r.original, 0)
        total += size
        key = r.season if r.season is not None else -1
        seasons[key] = seasons.get(key, 0) + size
        for sub, _ in matching_subs(plan.folder, r.original, plan.all_files):
            subs += plan.sizes.get(sub, 0)
    other = sum(v for k, v in plan.sizes.items()
                if os.path.splitext(k)[1].lower() not in VIDEO_EXTS | SUB_EXTS)
    largest = sorted(((r.original, plan.sizes.get(r.original, 0)) for r in plan.results), key=lambda x: -x[1])[:5]
    return {"videos": total, "subs": subs, "other": other, "total": total + subs + other,
            "seasons": [{"season": k, "bytes": v} for k, v in sorted(seasons.items())],
            "largest": [{"name": n, "bytes": b} for n, b in largest]}


def find_show_folders(path: str) -> list[str]:
    """A folder with episodes in it is one show; otherwise each sub-folder with episodes is a show."""
    def has_videos(p):
        try:
            return any(os.path.splitext(f)[1].lower() in VIDEO_EXTS for f in os.listdir(p))
        except OSError:
            return False
    if has_videos(path):
        return [path]
    subs = []
    for d in sorted(os.listdir(path), key=str.lower):
        full = os.path.join(path, d)
        if os.path.isdir(full) and not d.startswith(".") and has_videos(full):
            subs.append(full)
    return subs


# ======================================================================
# 6) Console mode (the window is episodeflow_gui.py)
# ======================================================================
def print_preview(plan: ShowPlan):
    print("=" * 70)
    for i, r in enumerate(plan.ordered, 1):
        target = target_name(plan, r)
        if target is None:
            why = "skipped by you" if r.skipped else "; ".join(r.notes)
            print(f"{i:>2} X  {r.original}\n        -> (not renamed)   [{why}]")
            continue
        mark = "!!" if r.conflict else ("? " if r.confidence != "high" else "  ")
        notes = list(r.notes) + (["same episode number as another file"] if r.conflict else [])
        print(f"{i:>2} {mark} {r.original}\n        -> {target}"
              + (f"   [{'; '.join(notes)}]" if mark.strip() else ""))
        if r.info:
            print(f"           i {r.info}")
        for sub, suffix in matching_subs(plan.folder, r.original, plan.all_files):
            print(f"           + subtitle -> {new_base(r, plan.show) + suffix}")
    print("=" * 70)
    for m in missing_episodes(plan):
        if m["missing"]:
            print(f"Missing S{m['season']:02d} ({len(m['have'])} of {m['total']}, {m['source']}): {ranges(m['missing'])}")
    print("Legend:  ? = please double-check   !! = conflict   X = not renamed")


def shift_part(target: Result, offset: int, results: list[Result]):
    """'7 +13': number = number in the name + 13, for that file's whole Part (or just the file)."""
    if target.raw_episode is None:
        return 0
    if target.part and target.part >= 2:
        group = [r for r in results if r.season == target.season and r.part == target.part and r.raw_episode]
    else:
        group = [target]
    for r in group:
        r.episode = r.raw_episode + offset
        r.skipped, r.confidence = False, "high"
        reset_notes(r)
        add_note(r, "shifted", n=offset)
    return len(group)


def run_console(folder: str, only: list[str] | None = None):
    plan = analyze(folder, only)
    if not plan.results:
        print("No video files found.")
        return
    print(f"\nShow: {plan.show}" + (f"   (folder season: S{plan.folder_season})" if plan.folder_season else ""))
    if plan.lookup and plan.lookup._done:
        print("         " + plan.lookup.summary())
    while True:
        conflicts = mark_conflicts(plan.results)
        print_preview(plan)
        if conflicts:
            print(f"\n{conflicts} file(s) share the same number. Fix one of them by typing its line number.")
        ans = input("\ny = rename | n = cancel | 5 = edit line 5 | 5 +13 = shift line 5's part by 13: ").strip().lower()
        m = re.fullmatch(r"(\d+)\s*\+\s*(\d+)", ans)
        if m and 1 <= int(m.group(1)) <= len(plan.ordered):
            n = shift_part(plan.ordered[int(m.group(1)) - 1], int(m.group(2)), plan.results)
            print(f"\nShifted {n} file(s).")
            continue
        if ans.isdigit() and 1 <= int(ans) <= len(plan.ordered):
            r = plan.ordered[int(ans) - 1]
            a = input(f"\n{r.original}\nNew season and episode (e.g. 2 14), 'skip', or Enter to cancel: ").strip().lower()
            nums = re.findall(r"\d+", a)
            if a == "skip":
                edit_result(r, None, None, skip=True)
            elif len(nums) == 2:
                edit_result(r, int(nums[0]), int(nums[1]))
            elif len(nums) == 1:
                edit_result(r, None, int(nums[0]))
            continue
        if ans == "y":
            try:
                print(f"Done, {apply_plan(plan)} file(s) renamed. To undo: run again with --undo")
                return
            except EFError as e:
                print(e)
                continue
        print("Cancelled, nothing changed.")
        return


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    args = [a for a in sys.argv[1:] if a != "--undo"]
    if not args:
        args = [os.getcwd()]
    if os.path.isdir(args[0]):
        folder, only = args[0], None
    else:
        folder, only = os.path.dirname(os.path.abspath(args[0])), [os.path.basename(a) for a in args]
    if "--undo" in sys.argv:
        n = undo(folder)
        print(f"Undone: {n} files restored." if n else "Nothing to undo in this folder.")
        return
    for f in ([folder] if only else find_show_folders(folder)):
        run_console(f, only)


if __name__ == "__main__":
    main()
