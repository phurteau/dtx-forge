"""Songsterr integration: search, metadata, drum notation JSON, tab-synced audio."""
import json, gzip, io, urllib.parse, urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DTXForge/1.0"
NOTE_CDN = "https://dqsljvtekg760.cloudfront.net"
AUDIO_HOST = "https://audio4-1.songsterr.com"


def _get(url, want_json=True):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
    if want_json:
        return json.loads(raw.decode("utf-8"))
    return raw


def search(pattern, size=20):
    """Search Songsterr; return list of {songId,title,artist,...}."""
    q = urllib.parse.urlencode({"pattern": pattern, "size": size, "from": 0})
    url = f"https://www.songsterr.com/api/songs?{q}"
    try:
        data = _get(url)
    except Exception:
        # fallback to the a/ra search endpoint
        url = f"https://www.songsterr.com/a/ra/songs.json?{urllib.parse.urlencode({'pattern': pattern})}"
        data = _get(url)
    out = []
    for s in data:
        out.append({
            "songId": s.get("songId") or s.get("id"),
            "title": s.get("title"),
            "artist": (s.get("artist") or {}).get("name") if isinstance(s.get("artist"), dict) else s.get("artist"),
        })
    return [o for o in out if o["songId"]]


def parse_song_id(url_or_id):
    """Accept a Songsterr URL or a raw numeric id -> int songId."""
    s = str(url_or_id).strip()
    if s.isdigit():
        return int(s)
    # .../artist-title-s692328  or ...-s692328?...
    import re
    m = re.search(r"-s(\d+)", s) or re.search(r"/(\d+)(?:\D|$)", s)
    if not m:
        raise ValueError(f"Could not find a Songsterr song id in: {url_or_id}")
    return int(m.group(1))


def meta(song_id, revision_id=None):
    """Fetch song metadata (tracks, revision, audio + notation hashes)."""
    url = f"https://www.songsterr.com/api/meta/{song_id}"
    if revision_id:
        url += f"/{revision_id}"
    return _get(url)


def _drum_track_index(m):
    tracks = m.get("tracks", [])
    for i, t in enumerate(tracks):
        if t.get("instrumentId") == 1024 or (t.get("instrument", "").lower() == "drums"):
            return i
    return 0  # default first


def fetch_drum_notation(m):
    """Return the drum track's notation JSON (measures[]). Robust to page ordering."""
    song_id = m["songId"]; rev = m["revisionId"]; img = m["image"]
    n_pages = max(len(m.get("tracks", [])), 1)
    di = _drum_track_index(m)
    base = f"{NOTE_CDN}/{song_id}/{rev}/{img}"
    # try the drum track index first, then scan all pages for instrument==Drums
    order = [di] + [i for i in range(n_pages) if i != di]
    last_err = None
    for i in order:
        try:
            trk = _get(f"{base}/{i}.json")
        except Exception as e:
            last_err = e; continue
        if trk.get("instrumentId") == 1024 or (trk.get("instrument", "").lower() == "drums"):
            return trk
    # fallback: return page at drum index even if instrument tag missing
    try:
        return _get(f"{base}/{di}.json")
    except Exception as e:
        raise RuntimeError(f"Could not fetch drum notation: {e or last_err}")


def synced_audio_url(m, quality="100"):
    """URL of the tab-synced full-mix audio (opus). Perfectly aligned to the tab."""
    song_id = m["songId"]; rev = m["revisionId"]
    ah = m.get("audioV4") or m.get("audioV2")
    if not ah:
        return None
    return f"{AUDIO_HOST}/{song_id}/{rev}/{ah}/{quality}/f/0.opus"


def download_synced_audio(m, out_path):
    url = synced_audio_url(m)
    if not url:
        raise RuntimeError("No tab-synced audio available for this song.")
    data = _get(url, want_json=False)
    with open(out_path, "wb") as f:
        f.write(data)
    return out_path
