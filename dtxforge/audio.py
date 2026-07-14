"""Audio utilities: ffmpeg convert (bundled binary), yt-dlp + Demucs via in-process
Python APIs so everything works inside a frozen .exe (no external `python`)."""
import os, glob, subprocess


def ffmpeg_exe():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def to_wav(src, dst, ar=44100, ac=2):
    ff = ffmpeg_exe()
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-ac", str(ac), "-ar", str(ar), dst], check=True)
    return dst


def to_ogg(src, dst, q=5):
    ff = ffmpeg_exe()
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
                    "-c:a", "libvorbis", "-q:a", str(q), dst], check=True)
    return dst


def download_audio_url(url, out_base, progress=None):
    """Download audio from ANY yt-dlp-supported URL (YouTube, SoundCloud, Bandcamp,
    Vimeo, X/Twitter, a direct .mp3/.wav/.m4a link, and 1000+ more sites), tiered:
      1) anonymous (works for most users / IPs / sites)
      2) auto browser cookies (Firefox/Chrome/Edge/Brave) - reuses the user's
         existing site session, snapshotting the DB to dodge file-locks
      3) raise a friendly error suggesting Upload file
    Requires a JS runtime (deno) + EJS solver for sites (e.g. YouTube) that need it."""
    import yt_dlp

    common = {
        "format": "bestaudio/best",
        "outtmpl": out_base + ".%(ext)s",
        "quiet": True, "no_warnings": True, "noprogress": True,
        # enable the JS challenge solver (needed for YouTube signatures)
        "extractor_args": {"youtube": {"jsc_runtime": ["deno"]}},
        "remote_components": ["ejs:github"],
    }

    def _try(opts, label):
        if progress:
            progress(f"YouTube: trying {label}...")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            hits = [h for h in glob.glob(out_base + ".*") if not h.endswith((".part", ".ytdl"))]
            return max(hits, key=os.path.getsize) if hits else None
        except Exception as e:
            if progress:
                progress(f"YouTube {label} failed: {str(e)[:120]}")
            return None

    # 1) anonymous
    got = _try(dict(common), "anonymous")
    if got:
        return got

    # 2) auto browser cookies (snapshot to avoid locked DBs)
    for browser in ("firefox", "chrome", "edge", "brave"):
        snap = _snapshot_cookiefile(browser)
        opts = dict(common)
        if snap:
            opts["cookiefile"] = snap
        else:
            opts["cookiesfrombrowser"] = (browser,)
        got = _try(opts, f"{browser} session cookies")
        if got:
            return got

    raise RuntimeError(
        "Couldn't download audio from that link. If it's a site that needs a login "
        "(e.g. YouTube), make sure you're signed in to it in your browser, or use the "
        "'Upload file' option to add the audio directly.")


def _snapshot_cookiefile(browser):
    """Copy a browser's YouTube/Google cookies to a temp Netscape cookies.txt so
    yt-dlp can read them even while the browser holds the DB open. Returns path or None."""
    import tempfile, sqlite3, shutil, glob as _glob
    home = os.path.expanduser("~")
    try:
        if browser == "firefox":
            base = os.path.join(os.environ.get("APPDATA", ""), "Mozilla", "Firefox", "Profiles")
            profs = _glob.glob(os.path.join(base, "*")) if os.path.isdir(base) else []
            db = None
            for p in sorted(profs, key=lambda x: -os.path.getmtime(x)):
                cand = os.path.join(p, "cookies.sqlite")
                if os.path.exists(cand):
                    db = cand; break
            if not db:
                return None
            tmpd = tempfile.mkdtemp(prefix="dtxff_")
            snap = os.path.join(tmpd, "cookies.sqlite")
            _shared_copy(db, snap)
            for ext in ("-wal", "-shm"):
                if os.path.exists(db + ext):
                    _shared_copy(db + ext, snap + ext)
            con = sqlite3.connect(snap)
            try: con.execute("PRAGMA wal_checkpoint(FULL)")
            except Exception: pass
            rows = con.execute("SELECT host,path,isSecure,expiry,name,value FROM moz_cookies "
                               "WHERE host LIKE '%youtube%' OR host LIKE '%google%'").fetchall()
            con.close()
            if not rows:
                return None
            out = os.path.join(tmpd, "cookies.txt")
            with open(out, "w", encoding="utf-8") as f:
                f.write("# Netscape HTTP Cookie File\n")
                for host, path, sec, exp, name, val in rows:
                    flag = "TRUE" if host.startswith(".") else "FALSE"
                    f.write(f"{host}\t{flag}\t{path}\t{'TRUE' if sec else 'FALSE'}\t{int(exp or 0)}\t{name}\t{val}\n")
            return out
        # chromium family: let yt-dlp handle decryption via cookiesfrombrowser (snapshot copy of Cookies)
        roots = {
            "chrome": os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data"),
            "edge":   os.path.join(home, "AppData", "Local", "Microsoft", "Edge", "User Data"),
            "brave":  os.path.join(home, "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data"),
        }
        root = roots.get(browser)
        if not root or not os.path.isdir(root):
            return None
        return None   # fall back to yt-dlp's own cookiesfrombrowser for chromium
    except Exception:
        return None


def _shared_copy(src, dst):
    """Copy a file that another process may hold open (Windows share flags)."""
    try:
        with open(src, "rb") as s:
            data = s.read()
        with open(dst, "wb") as d:
            d.write(data)
        return
    except PermissionError:
        pass
    # Windows: open with full sharing via CreateFileW
    import ctypes
    from ctypes import wintypes
    GENERIC_READ = 0x80000000
    FILE_SHARE_ALL = 0x00000001 | 0x00000002 | 0x00000004  # read|write|delete
    OPEN_EXISTING = 3
    CreateFileW = ctypes.windll.kernel32.CreateFileW
    CreateFileW.restype = wintypes.HANDLE
    ReadFile = ctypes.windll.kernel32.ReadFile
    CloseHandle = ctypes.windll.kernel32.CloseHandle
    h = CreateFileW(src, GENERIC_READ, FILE_SHARE_ALL, None, OPEN_EXISTING, 0x80, None)
    if h == wintypes.HANDLE(-1).value:
        raise IOError("could not open " + src)
    try:
        with open(dst, "wb") as out:
            buf = ctypes.create_string_buffer(1 << 20)
            read = wintypes.DWORD(0)
            while True:
                ok = ReadFile(h, buf, len(buf), ctypes.byref(read), None)
                if not ok or read.value == 0:
                    break
                out.write(buf.raw[:read.value])
    finally:
        CloseHandle(h)


def demucs_remove_drums(wav_path, out_root, progress=None):
    """Separate drums using the Demucs Python API (in-process). Returns
    (no_drums_wav, drums_wav). Downloads the ~80 MB model on first use."""
    from demucs.api import Separator, save_audio
    if progress:
        progress("Separating drums with Demucs (first run downloads the model, ~80 MB)...")
    sep = Separator(model="htdemucs")
    origin, stems = sep.separate_audio_file(wav_path)
    drums = stems["drums"]
    no_drums = origin - drums          # everything except drums
    os.makedirs(out_root, exist_ok=True)
    nd = os.path.join(out_root, "no_drums.wav")
    dr = os.path.join(out_root, "drums.wav")
    save_audio(no_drums, nd, samplerate=sep.samplerate)
    save_audio(drums, dr, samplerate=sep.samplerate)
    if progress:
        progress("Drum separation complete.")
    return nd, dr


def build_bgm(full_wav, drums_wav, out_wav, k):
    """BGM = normalize(full_mix - k*drums). Keeps the song full-bodied while
    reducing drums. k~0.9 => drums nearly gone (arcade); k~0.6 => quiet drums.
    The result is normalized back up so the song plays at a healthy level."""
    import wave, numpy as np

    def rd(p):
        with wave.open(p, "r") as w:
            sr = w.getframerate(); ch = w.getnchannels()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
        return x.reshape(-1, ch) if ch > 1 else x.reshape(-1, 1), sr

    full, sr = rd(full_wav)
    drm, _ = rd(drums_wav)
    n = min(len(full), len(drm)); full, drm = full[:n], drm[:n]
    if full.shape[1] != drm.shape[1]:
        m = min(full.shape[1], drm.shape[1]); full, drm = full[:, :m], drm[:, :m]
    mix = full - k * drm
    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.97
    out = (mix * 32767).astype("<i2")
    with wave.open(out_wav, "w") as w:
        w.setnchannels(mix.shape[1]); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(out.tobytes())
    return out_wav


def trim_start(in_wav, out_wav, seconds):
    """Drop the first `seconds` from a WAV. Used by the audio-only path to slide the
    backing track so it starts at the first detected drum hit (chart t=0)."""
    import wave, numpy as np
    with wave.open(in_wav, "r") as w:
        sr = w.getframerate(); ch = w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    off = max(0, int(round(seconds * sr))) * ch
    x = x[off:] if off < len(x) else x[:0]
    with wave.open(out_wav, "w") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(x.tobytes())
    return out_wav
