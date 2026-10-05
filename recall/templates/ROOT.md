# ROOT — knowledge hub

The root node. Claude reads this at session start; everything else is pulled on demand.
Routing table: `INDEX.json`. History and sync status: `STATUS.md` (read on demand).

Every line here is paid for in every session. Keep only what changes how Claude behaves;
history, sync logs and one-off findings go in `STATUS.md` or a project card.

<!-- /recall init fills every section below. Replace the placeholders; delete what you don't use. -->

---

## Who

<!-- Name, what you do, what you are building and why. Two or three short paragraphs.
     Include how you work with Claude if it matters (e.g. "directs agents, reviews every diff"). -->

---

## Standing preferences

<!-- Rules you have repeated to Claude more than once. One bullet each, imperative, with
     the reason when it is not obvious. These are the highest-value lines in the hub. -->

- 

---

## Environment

<!-- OS, shell, where projects live, runtime versions, and what is NOT installed
     (so Claude stops reaching for it). -->

---

## Projects

| Project | Path | What it is |
|---|---|---|
|  |  |  |

Each has a card in `projects/<id>.md`. Load **only** the one matching the current directory.

## Cross-cutting decisions

<!-- Decisions that span projects live in `decisions/<topic>.md`. List each with one line
     on when to read it. Never loaded at session start. -->
