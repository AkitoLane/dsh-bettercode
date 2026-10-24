# dsh-bettercode

A skill for coding agents. It makes the model work through a fixed procedure
before and after writing code: pick data structures before writing the loop,
keep functions small and flat, measure before optimizing, run a checklist
before saying "done".

Language agnostic. Covers new code, refactors and code review.

[中文说明](README.zh-CN.md)

## Why this exists

Models write code that runs. What they skip is the boring part: they stack a
patch on a hack instead of fixing it, hide an O(n^2) inside a loop that
"works", and ship the first draft without walking the edge cases.

This skill replaces that judgement call with rules you can check. "Function
under 40 lines" is verifiable. "Write clean code" is not.

## How it runs

The agent picks one of three routes first:

| Route | What it runs |
|---|---|
| Write new code | Phase 1 to 5 |
| Refactor legacy code | Refactor rules, then Phase 2 to 5 |
| Review code | Phase 5 checklist plus `references/code-smells.md`, no edits |

| Phase | What happens |
|---|---|
| 1. Before typing | Contract, data size N, hot path or not, latency or throughput, then a complexity budget |
| 2. Design | Data structure first, layering, pure core with IO pushed to the edges |
| 3. Write | Hard rules: early return, one job per function, rule of three, no dead code, no magic values, no boolean traps, explicit errors |
| 4. Performance | The "always do" list (hoist invariants, index before the loop, batch IO) versus micro-optimization, which needs a profile first |
| 5. Before delivery | 10 item checklist, iterate until it passes |

Refactor mode adds: lock behaviour with characterization tests, keep legacy
quirks and label them, prove equivalence with differential fuzzing, and freeze
broken public signatures behind a thin adapter instead of changing them.

Two handbooks load on demand, so they stay out of context until a phase needs
them:

| File | Loaded when |
|---|---|
| `references/performance-patterns.md` | Designing for performance, optimizing, debugging slowness. Data structure table, hot path ritual, IO and memory and concurrency patterns, 12 anti-pattern to fix pairs, measurement method, per language notes |
| `references/code-smells.md` | Reviewing, refactoring, or when a red line fires. 20 smells as symptom, cause, prescription, plus refactoring safety rules |

## Install

Clone once, then copy the directory into wherever your host looks for skills.

```bash
git clone https://github.com/AkitoLane/dsh-bettercode.git
```

### DeepSeek Harness (DSH)

User level, auto-discovered, no restart needed:

```bash
mkdir -p ~/.dsh/skills
cp -r dsh-bettercode ~/.dsh/skills/
```

Or project scoped:

```bash
mkdir -p <project>/.dsh/skills
cp -r dsh-bettercode <project>/.dsh/skills/
```

### Claude Code

```bash
mkdir -p ~/.claude/skills
cp -r dsh-bettercode ~/.claude/skills/
```

Restart the session, then confirm it shows up in your skills or plugins list.

### Cursor, Codex CLI, Gemini CLI, opencode

These hosts read a plain instructions file instead of a skill directory. Keep
the folder in or near the project and point that file at it.

| Host | File it reads |
|---|---|
| Cursor | `AGENTS.md` or `.cursor/rules/dsh-bettercode.mdc` |
| Codex CLI | `AGENTS.md` (repo root or `~/.codex/`) |
| Gemini CLI | `GEMINI.md` |
| opencode | `AGENTS.md` |

Add one line to that file:

```markdown
For any coding task, follow ./dsh-bettercode/SKILL.md and load the files
under ./dsh-bettercode/references/ when it says to.
```

Pasting `SKILL.md` inline also works, but then the two references are out of
reach, and phases 3 and 4 lose their lookup tables.

### Check that it loaded

Ask for something that should trip the gates:

```
Use dsh-bettercode to review this file
```

A loaded skill runs the phase 5 checklist and cites smell names from
`code-smells.md`. Generic advice means it did not load.

## Usage

Automatic: the description covers writing, refactoring, reviewing and
optimizing, so a compatible host loads it unasked.

Manual: `Use dsh-bettercode to rewrite this module.`

## Evidence

Same model, with and without the skill, three tasks. Full numbers and the
harness that produced them are in [EVALUATION.md](EVALUATION.md) and
`evaluation/`.

- Refactoring a 147 line god function with 20 planted smells: both groups
  passed a 400 case differential test, so behaviour was provably identical.
  The skill group removed about 19.5 of 20 smells against 17, kept the
  orchestrator at 47 lines against 80, and fixed the boolean trap the baseline
  left alone.
- Reviewing the same file with 26 planted issues: recall 26/26 against 24/26,
  and 9 performance findings against 7.
- Writing a sliding window rate limiter from scratch: both groups picked the
  deque design and both scored 100/100 on the AST rubric. On a well specified
  greenfield task the baseline is already good.

So no, it does not turn bad output into good output. It makes the ceiling
predictable, so coverage does not depend on the model having a good day.

## Repo layout

```
SKILL.md                            the skill body
references/performance-patterns.md  performance handbook
references/code-smells.md           smell catalogue and refactoring rules
EVALUATION.md                       A/B writeup with the numbers
evaluation/                         scoring tools, task specs, six run artifacts
```

## License

MIT
