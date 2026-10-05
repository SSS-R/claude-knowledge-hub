---
name: recall
description: "Cross-session memory for Claude Code. /recall (load context), /recall init (build the hub), /recall sync (mine new sessions), /recall status, /recall add <path>, /recall <topic> (search across all projects). Use when the user asks what they decided, built or said in earlier sessions or other projects."
argument-hint: "[init | sync | status | add <path> | <topic>]"
---

# recall — knowledge hub

The hub lives at `~/.claude/knowledge/` (override with the `KNOWLEDGE_HUB` env var).
Routing table: `INDEX.json`. Root node: `ROOT.md`. Project cards: `projects/<id>.md`.
History and sync log: `STATUS.md`. Optional: `decisions/<topic>.md` for cross-project
decisions, `profile/` for long-form detail that does not fit in ROOT.

ROOT loads in every session, so every line in it is paid for every time. It holds only what
changes how Claude behaves. History, sync logs and one-off findings go in `STATUS.md`.

`hub.py` and `templates/` sit next to this file — use the base directory shown when this
skill loaded. Run it with `python3` (`python` on Windows). It is stdlib-only and offline.

Handle `$ARGUMENTS`:

## empty — load context

Read `ROOT.md`. If the current directory matches a `projects[].path` in `INDEX.json`, also
read that project's card. Then give a 3–5 line orientation: what this project is, where it
stands, and any hard rule that applies here. Do **not** read `sessions/` — it is searched,
not loaded. If the hub does not exist, say so and offer `/recall init`.

## `init` — build the hub (first run)

1. `python hub.py --init` — creates the hub from the templates. Never overwrites.
2. `python hub.py --discover` — lists every transcript folder under `~/.claude/projects/`
   with its real path, session count, size and last use. Show the user the list and
   **ask which projects to track**. Suggest the ones with the most sessions and recent use;
   skip throwaway and scratch folders. Five or six is a good start.
3. Add each chosen project to `INDEX.json` (`id`, `name`, `path`, `card`, `repo`,
   `transcripts` = the folder name from `--discover`, `status`, `distilled_on: null`).
4. `python hub.py` — filters the transcripts. It prints an estimated token count. **State
   that estimate and get a yes before distilling** if it is over ~150k tokens.
5. **Pilot one card first.** Read `sessions/filtered/<id>.md` for the project with the most
   sessions, skim its repo (README, CLAUDE.md, `git log --oneline -20`), and write
   `projects/<id>.md` from `templates/project-card.md`. Show it, take corrections, then do
   the rest the same way.
6. Fill `ROOT.md`: *Who* and *Standing preferences* from what the user repeatedly says and
   corrects across the filtered transcripts (ask two or three questions to fill gaps —
   never invent), *Environment* from checking installed runtimes, and the *Projects* table.
7. Offer to add the session-start binding below to `~/.claude/CLAUDE.md`. Show it and ask
   before writing — it is the user's global config. Without it, the hub loads only when
   they type `/recall`.

```markdown
### knowledge-hub (cross-session memory)
- **Hub:** `~/.claude/knowledge/` · **Root node:** `ROOT.md` · **Routing:** `INDEX.json` · **Command:** `/recall`
- **At session start, read `~/.claude/knowledge/ROOT.md`.** If the working directory matches a
  `projects[].path` in `INDEX.json`, also read that project's card. Load no other card.
- Never read `sessions/` into context — search it with `/recall <topic>`.
- Nothing updates automatically; refresh with `/recall sync`. Treat a card as current only up to
  its `distilled_on` date, and trust the repo over the card when they disagree.
- Project cards may carry hard rules that override defaults. The card wins.
```

## `sync` — mine new sessions

1. `python hub.py` — re-filters every tracked project, prints a per-project delta and a
   `CARDS TO REFRESH` verdict.
2. If nothing changed, say so and stop. Do not re-distill unchanged projects.
3. For each project in the verdict, read only its `sessions/filtered/<id>.md` and update
   `projects/<id>.md` with what is genuinely new — decisions, reversals, constraints,
   current state. Keep what still holds; do not rewrite a card wholesale to paraphrase it.
4. Set `distilled_on` in the card and in `INDEX.json`, and add a dated entry to
   `STATUS.md` (create it if missing). Touch `ROOT.md` only if something that changes
   behaviour moved — a project's one-line summary, a new standing preference.
5. Report what changed in a few lines. If a card's claim now contradicts the repo, verify
   against the repo and say which won.

## `status` — report, change nothing

Projects tracked, when each was last distilled, session and turn counts, and when the last
sync ran. Read `INDEX.json`, `sessions/.last_run.json` and `STATUS.md` only.

## `add <path>` — track a new project

Resolve the path. Find its transcript folder in `python hub.py --discover` (match on the
path column). Append an entry to `INDEX.json`, run `python hub.py --project <id>`, and
write its card. A project with no transcript folder gets `"transcripts": null` and a card
built from the repo alone.

Check for the known gap: transcripts are keyed by the folder a session *started in*, not by
what was built. A project created from inside another project's folder has its history in
that other project's transcripts.

## anything else — search the whole hub

Treat it as a topic. Grep `ROOT.md`, `STATUS.md`, `profile/`, `projects/`, `decisions/`
and `sessions/filtered/` for it and answer from what you find, citing which card or project
each fact came from. This is the cross-project path — "what did I decide about licensing",
"where did I use Postgres", "which projects hit rate limits". If the answer needs an exact
exchange or date the cards do not hold, grep the raw transcripts under
`~/.claude/projects/<folder>/*.jsonl` (or use a session-search tool if one is available).

## What belongs in a card

Keep: decisions **with their reason and date**, reversals (marked explicitly), hard rules
in the user's own words, things the user corrected Claude on, gotchas already paid for,
current state. Drop: step-by-step narration, code, transient debugging, anything the repo
already records better. Aim for under ~150 lines per card.

## Rules for every path

- Cards are lossy by design. When precision matters, go to the transcript, not a guess.
- `hub.py` redacts credentials, but the raw transcripts still hold them. Never copy a
  secret into the hub. If filtered output shows a `[REDACTED-…]` marker, tell the user a
  live credential is sitting in that raw transcript so they can rotate it.
- Never load `sessions/filtered/*.md` except during `init`, `sync` or a search — and then
  only the file you need.
- Never invent facts about the user to fill a template section. Leave it empty or ask.
