# claude-knowledge-hub

Cross-session memory for [Claude Code](https://claude.com/claude-code). One skill, `/recall`.

Claude Code forgets everything between sessions, but it keeps every session on disk as a
JSONL transcript under `~/.claude/projects/`. Those pile up fast, and almost all of it is
tool output, file dumps and diffs. This skill filters them down to what you actually said,
then has Claude distill that into **small per-project cards** that load only when you are
working in that project.

On the author's machine: **327 MB of transcripts across 24 sessions → 470 KB of real
signal (0.15%)** → about a dozen cards. Session-start cost is roughly 2k tokens.

## How it works

```
~/.claude/knowledge/
├── ROOT.md              who you are, standing preferences, environment, project list   ← every session
├── INDEX.json           routing table: project path → card
├── projects/<id>.md     one card per project                                          ← only when cwd matches
├── decisions/<topic>.md cross-project decisions (optional)                            ← on demand
└── sessions/filtered/   filtered transcripts                                          ← searched, never loaded
```

| Tier | What | Loaded |
|---|---|---|
| 0 | A short binding in `~/.claude/CLAUDE.md` | always |
| 1 | `ROOT.md` | session start |
| 2 | The one card for the current directory | when cwd matches |
| 3 | Filtered and raw transcripts | only via `/recall <topic>` |

The filter (`hub.py`) is plain Python: stdlib only, no network, no LLM. Distillation is
done by Claude in your own session when you run `/recall init` or `/recall sync`.

## Install

You need Claude Code and Python 3.8+.

```bash
git clone https://github.com/SSS-R/claude-knowledge-hub.git
cp -r claude-knowledge-hub/recall ~/.claude/skills/
```

On Windows PowerShell, the second line is:

```powershell
Copy-Item -Recurse claude-knowledge-hub\recall $HOME\.claude\skills\
```

Then, in Claude Code:

```
/recall init
```

Claude creates the hub, lists your transcript folders, asks which projects to track, and
writes the first card as a pilot for you to check before doing the rest. At the end it
offers to add a 6-line binding to `~/.claude/CLAUDE.md` so `ROOT.md` loads in every
session. It asks before editing that file.

## Commands

| Command | Does |
|---|---|
| `/recall` | Load ROOT plus the card for this directory and give a short orientation |
| `/recall init` | Build the hub for the first time |
| `/recall sync` | Re-filter transcripts and update only the cards whose projects changed |
| `/recall status` | What is tracked and when each card was last distilled |
| `/recall add <path>` | Start tracking another project |
| `/recall <anything>` | Search across every project: *"what did I decide about auth"*, *"where did I use Redis"* |

Nothing updates automatically. Run `/recall sync` when you have done a few sessions' work.

## Privacy

- Everything stays in `~/.claude/knowledge/` on your machine. Nothing is uploaded anywhere
  by this skill.
- Claude reads the filtered transcripts while distilling, so that text goes to the model
  the same way any file Claude reads does.
- `hub.py` redacts credentials it recognises (database URLs, API keys, GitHub/Slack/AWS/
  Stripe tokens, JWTs, private keys, `*_SECRET=` lines). It flags them; it does not rotate
  them. The raw transcripts still contain whatever you pasted. Run `python hub.py --selftest`
  to check the redaction rules.
- Your hub is personal. Don't commit `~/.claude/knowledge/` to a public repo.

## Script reference

```
python hub.py --init            create the hub from templates (never overwrites)
python hub.py --discover        list transcript folders with real paths, sizes, last use
python hub.py                   filter every tracked project, report what's new
python hub.py --project <id>    filter one project
python hub.py --with-replies    also keep Claude's prose replies (bigger output)
python hub.py --selftest        check the redaction rules
```

Env vars: `KNOWLEDGE_HUB` (default `~/.claude/knowledge`) and `CLAUDE_CONFIG_DIR`
(default `~/.claude`).

## Known gap

Transcripts are filed by the folder a session **started in**, not by what you built. If
you built project B in a session opened in project A's folder, B's history sits in A's
transcripts. `/recall add` checks for this.

## License

MIT
