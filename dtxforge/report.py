"""Structured progress reporter: tracks pipeline STAGES (for the UI visualizer)
plus a running text log. Backwards compatible: calling the reporter like a
function logs a message, so old `progress("text")` calls still work."""

STAGES = [
    ("notation",    "Notation"),
    ("audio",       "Audio"),
    ("separate",    "Drum separation"),
    ("align",       "Auto-sync"),
    ("humanize",    "Foot technique"),
    ("playability", "Playability"),
    ("package",     "Package"),
]


class Reporter:
    def __init__(self, sink=None):
        self.sink = sink                     # optional callable(text) for streaming
        self.messages = []
        self.data = {}                       # live key/values for the UI (e.g. detected bpm)
        self.stages = [{"id": i, "label": l, "state": "pending"} for i, l in STAGES]

    # ---- live data (surfaced to the UI as soon as it's known) ----
    def set_data(self, key, value):
        self.data[key] = value

    # ---- text log ----
    def log(self, text):
        self.messages.append(text)
        if self.sink:
            try: self.sink(text)
            except Exception: pass

    def __call__(self, text):                # progress("...") still works
        self.log(text)

    # ---- stage control ----
    def _find(self, sid):
        return next((s for s in self.stages if s["id"] == sid), None)

    def stage(self, sid, msg=None):
        """Activate a stage: any currently-active stage becomes done."""
        for s in self.stages:
            if s["state"] == "active":
                s["state"] = "done"
        cur = self._find(sid)
        if cur and cur["state"] != "done":
            cur["state"] = "active"
        if msg:
            self.log(msg)

    def skip(self, sid):
        s = self._find(sid)
        if s and s["state"] in ("pending",):
            s["state"] = "skipped"

    def error(self, sid=None):
        s = self._find(sid) if sid else next((x for x in self.stages if x["state"] == "active"), None)
        if s:
            s["state"] = "error"

    def finish(self):
        for s in self.stages:
            if s["state"] == "active":
                s["state"] = "done"
            elif s["state"] == "pending":
                s["state"] = "skipped"

    def snapshot(self):
        return [dict(s) for s in self.stages]
