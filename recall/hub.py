#!/usr/bin/env python3
"""
Knowledge hub helper for Claude Code. Deterministic: stdlib only, no LLM, no network.

Claude Code keeps every session as a JSONL transcript under ~/.claude/projects/<dir>/.
Almost all of it is tool payloads, file dumps, diffs and command output. This keeps only
the real conversational signal - what you typed, plus (optionally) Claude's prose
replies - and redacts credentials, so Claude can distill it into small per-project cards.

Usage:
  python hub.py --init             # create the hub from the templates (never overwrites)
  python hub.py --discover         # list transcript dirs with their real paths and sizes
  python hub.py                    # filter every project in INDEX.json (your turns only)
  python hub.py --with-replies     # also keep Claude's prose replies
  python hub.py --project <id>     # filter one project
  python hub.py --selftest         # check the redaction rules

Env: KNOWLEDGE_HUB (default ~/.claude/knowledge), CLAUDE_CONFIG_DIR (default ~/.claude).
Output: <hub>/sessions/filtered/<project-id>.md, one section per session, chronological.
"""
import json, os, re, sys, glob, shutil, datetime

CLAUDE_DIR = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")
HUB = os.environ.get("KNOWLEDGE_HUB") or os.path.join(CLAUDE_DIR, "knowledge")
PROJECTS_ROOT = os.path.join(CLAUDE_DIR, "projects")
OUT = os.path.join(HUB, "sessions", "filtered")
TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

# Injected scaffolding that is not the user speaking.
STRIP_BLOCKS = [
    re.compile(r"<system-reminder>.*?</system-reminder>", re.S),
    re.compile(r"<local-command-stdout>.*?</local-command-stdout>", re.S),
    re.compile(r"<command-message>.*?</command-message>", re.S),
    re.compile(r"<command-args>.*?</command-args>", re.S),
    re.compile(r"<persisted-output>.*?</persisted-output>", re.S),
    re.compile(r"<task-notification>.*?</task-notification>", re.S),
    re.compile(r"<ci-monitor-event>.*?</ci-monitor-event>", re.S),
]

# Secret redaction. Transcripts DO contain pasted live credentials. The hub is a derived
# artifact that may be searched, copied or shared, so secrets must not survive the filter.
# The raw transcript still holds them - redaction here does not rotate anything.
REDACT = [
    # postgres://user:password@host  /  mysql://  /  mongodb+srv://  /  redis://
    (re.compile(r"\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp)://[^\s:]+:)"
                r"[^\s@]+(@)", re.I), r"\1[REDACTED]\2"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
     "[REDACTED-PRIVATE-KEY]"),
    # bare provider key formats
    (re.compile(r"\bnpg_[A-Za-z0-9]{8,}"), "[REDACTED-NEON-KEY]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"), "[REDACTED-API-KEY]"),
    (re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}"), "[REDACTED-STRIPE-KEY]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}"), "[REDACTED-GOOGLE-KEY]"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"), "[REDACTED-GH-TOKEN]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "[REDACTED-GH-TOKEN]"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "[REDACTED-SLACK-TOKEN]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED-AWS-KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
     "[REDACTED-JWT]"),
    # KEY=value style env lines for anything secret-shaped
    (re.compile(r"\b([A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|APIKEY|API_KEY|PRIVATE_KEY)"
                r"[A-Z0-9_]*\s*[=:]\s*)\S+"), r"\1[REDACTED]"),
]
# Whole-message discards: pastes, hook noise, caveats.
DISCARD_IF = (
    "Caveat: The messages below were generated",
    "[Request interrupted",
    "API Error",
    "<bash-stdout>",
)

def clean(text):
    for pat in STRIP_BLOCKS:
        text = pat.sub("", text)
    # Keep the slash-command name, drop its wrapper.
    text = re.sub(r"<command-name>(.*?)</command-name>", r"/\1", text, flags=re.S)
    for pat, repl in REDACT:
        text = pat.sub(repl, text)
    return text.strip()

def extract(path, with_replies):
    """Yield (ts, role, text) for real conversational turns in one transcript."""
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("isMeta") or d.get("isSidechain"):
                continue
            m = d.get("message") or {}
            role = m.get("role")
            if role not in ("user", "assistant"):
                continue
            if role == "assistant" and not with_replies:
                continue
            c = m.get("content")
            if isinstance(c, str):
                text = c
            elif isinstance(c, list):
                # text blocks only - tool_use / tool_result are the bulk we are dropping
                text = "\n".join(b.get("text", "") for b in c
                                 if isinstance(b, dict) and b.get("type") == "text")
            else:
                continue
            text = clean(text)
            if len(text) < 2 or any(s in text for s in DISCARD_IF):
                continue
            yield d.get("timestamp", ""), role, text

def run(project_id, transcript_dir, with_replies):
    # Top-level *.jsonl only: <session>/subagents/*.jsonl hold no user turns.
    files = sorted(glob.glob(os.path.join(PROJECTS_ROOT, transcript_dir, "*.jsonl")))
    if not files:
        return None
    raw_bytes = sum(os.path.getsize(f) for f in files)
    out_lines, n_turns, n_sessions = [], 0, 0
    out_lines.append(f"# {project_id} - filtered transcript signal\n")
    out_lines.append(f"Source: {len(files)} sessions, {raw_bytes/1e6:.1f} MB raw. "
                     f"Filtered {datetime.date.today()}.\n")
    for f in files:
        turns = list(extract(f, with_replies))
        if not turns:
            continue
        n_sessions += 1
        sid = os.path.basename(f).replace(".jsonl", "")
        first_ts = turns[0][0][:10] if turns[0][0] else "unknown-date"
        out_lines.append(f"\n\n## session {sid[:8]} - {first_ts}\n")
        for ts, role, text in turns:
            tag = "USER" if role == "user" else "CLAUDE"
            out_lines.append(f"\n### {tag} {ts[:16]}\n{text}\n")
            n_turns += 1
    body = "".join(out_lines)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"{project_id}.md"), "w", encoding="utf-8") as fh:
        fh.write(body)
    return {"project": project_id, "files": len(files), "sessions_kept": n_sessions,
            "turns": n_turns, "raw_mb": raw_bytes/1e6,
            "filtered_kb": len(body.encode("utf-8"))/1024,
            "ratio": (len(body.encode("utf-8")) / raw_bytes * 100) if raw_bytes else 0}

def load_index():
    p = os.path.join(HUB, "INDEX.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)

def init():
    if os.path.exists(os.path.join(HUB, "INDEX.json")):
        print(f"Hub already exists at {HUB} - left untouched.")
        return
    os.makedirs(HUB, exist_ok=True)
    for f in ("ROOT.md", "INDEX.json"):
        shutil.copy(os.path.join(TEMPLATES, f), HUB)
    print(f"Hub created at {HUB}")

def session_cwd(path):
    """The working directory a session started in."""
    with open(path, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            if '"cwd"' in line:
                try:
                    return json.loads(line).get("cwd")
                except ValueError:
                    pass
    return None

def real_path(dir_name, files):
    """The path behind a transcript dir name. Claude Code names the dir by replacing every
    non-alphanumeric character of the path with '-', so prefer a session whose start path
    encodes back to the dir name - a session can start elsewhere and move in."""
    cwds = [c for c in (session_cwd(f) for f in files) if c]
    for c in cwds:
        if re.sub(r"[^A-Za-z0-9]", "-", c).lower() == dir_name.lower():
            return c
    return cwds[0] if cwds else "?"

def discover():
    idx = load_index() or {}
    tracked = {p.get("transcripts") for p in idx.get("projects", [])}
    rows = []
    for d in os.listdir(PROJECTS_ROOT) if os.path.isdir(PROJECTS_ROOT) else []:
        files = sorted(glob.glob(os.path.join(PROJECTS_ROOT, d, "*.jsonl")),
                       key=os.path.getmtime, reverse=True)
        if not files:
            continue
        rows.append((sum(os.path.getsize(f) for f in files) / 1e6, len(files),
                     datetime.date.fromtimestamp(os.path.getmtime(files[0])).isoformat(),
                     "yes" if d in tracked else "", d, real_path(d, files)))
    rows.sort(reverse=True)
    print(f"{'MB':>8}{'sess':>6}  {'last used':<12}{'tracked':<9}{'transcripts dir':<40}path")
    print("-" * 110)
    for mb, n, last, t, d, cwd in rows:
        print(f"{mb:>8.1f}{n:>6}  {last:<12}{t:<9}{d:<40}{cwd}")
    print(f"\n{len(rows)} transcript dirs under {PROJECTS_ROOT}")

def selftest():
    gh = "gh" + "p_" + "x" * 36          # built at runtime so this file trips no scanner
    for text, secret in [
        ("postgres://app:hunter2pass@db.example.com/main", "hunter2pass"),
        ("OPENAI_API_KEY=sk-abcdefghijklmnopqrstuvwx", "abcdefghijklmnop"),
        ("DB_PASSWORD: correct-horse", "correct-horse"),
        (f"token {gh} here", gh),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----", "MIIEow"),
    ]:
        assert secret not in clean(text), f"leaked: {text!r} -> {clean(text)!r}"
    assert clean("<system-reminder>noise</system-reminder> hello") == "hello"
    assert clean("<command-name>recall</command-name>") == "/recall"
    print("selftest ok")

def main():
    if "--selftest" in sys.argv:
        return selftest()
    if "--init" in sys.argv:
        return init()
    if "--discover" in sys.argv:
        return discover()

    with_replies = "--with-replies" in sys.argv
    only = sys.argv[sys.argv.index("--project") + 1] if "--project" in sys.argv else None
    idx = load_index()
    if idx is None:
        sys.exit(f"No INDEX.json in {HUB} - run with --init first.")
    rows = []
    for p in idx.get("projects", []):
        if only and p["id"] != only:
            continue
        # Projects built from the repo alone have no transcript dir - nothing to filter.
        if p.get("transcripts"):
            r = run(p["id"], p["transcripts"], with_replies)
            if r:
                rows.append(r)
    if not rows:
        sys.exit("No transcripts to filter - add projects to INDEX.json first.")

    # Compare against the previous run so /recall sync can report what is actually new.
    state_path = os.path.join(HUB, "sessions", ".last_run.json")
    prev = {}
    if os.path.exists(state_path):
        try:
            with open(state_path, encoding="utf-8") as fh:
                prev = json.load(fh).get("projects", {})
        except ValueError:
            prev = {}

    print(f"{'project':<24}{'sess':>5}{'turns':>7}{'raw MB':>9}{'kept KB':>10}{'ratio':>8}"
          f"  new since last sync")
    print("-" * 87)
    changed = []
    for r in rows:
        p = prev.get(r["project"])
        if p is None:
            delta = "(first run)"
            changed.append(r["project"])
        else:
            ds, dt = r["sessions_kept"] - p.get("sessions", 0), r["turns"] - p.get("turns", 0)
            if ds or dt:
                delta = f"+{ds} sessions, +{dt} turns"
                changed.append(r["project"])
            else:
                delta = "unchanged"
        print(f"{r['project']:<24}{r['sessions_kept']:>5}{r['turns']:>7}"
              f"{r['raw_mb']:>9.1f}{r['filtered_kb']:>10.0f}{r['ratio']:>7.2f}%  {delta}")
    print("-" * 87)

    # A --project run must not forget the other projects' baselines.
    prev.update({r["project"]: {"sessions": r["sessions_kept"], "turns": r["turns"],
                                "filtered_kb": round(r["filtered_kb"])} for r in rows})
    with open(state_path, "w", encoding="utf-8") as fh:
        json.dump({"synced": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                   "projects": prev}, fh, indent=2)

    tr, tk = sum(x["raw_mb"] for x in rows), sum(x["filtered_kb"] for x in rows)
    print(f"{'TOTAL':<24}{sum(x['sessions_kept'] for x in rows):>5}"
          f"{sum(x['turns'] for x in rows):>7}{tr:>9.1f}{tk:>10.0f}"
          f"{(tk*1024/(tr*1e6)*100) if tr else 0:>7.2f}%")
    print(f"\nestimated tokens to read all filtered output: ~{tk*1024/4/1000:,.0f}k")
    print(f"output: {OUT}")
    print("\nCARDS TO REFRESH: " + ", ".join(changed) if changed
          else "\nNothing new since the last sync - no card needs refreshing.")

if __name__ == "__main__":
    main()
