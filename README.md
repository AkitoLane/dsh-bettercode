# dsh-bettercode

[中文](README.zh-CN.md) | English

A coding-discipline skill for AI agents: make the model write code like a
top-tier engineer — right complexity by design, clean and readable logic,
measured performance — and stop spaghetti code ("屎山") at the source.

Language-agnostic. Works for writing new code, refactoring legacy code, and
code review, in any language.

## Why this skill

Modern LLMs already write *working* code. What they often miss is the
discipline of a senior engineer:

- picking the data structure **before** writing the loop (hidden O(n²) in "working" code);
- distinguishing design-time performance (always do) from micro-optimization (measure first);
- refusing to stack one more patch on a "temporary hack";
- running a pre-delivery self-check instead of shipping the first draft.

`dsh-bettercode` turns that discipline into a gated workflow with **checkable
hard rules** (function ≤ 40 lines, nesting ≤ 3, third duplication must be
abstracted, zero dead code, zero magic values, …) plus two on-demand
reference handbooks.

## How it works

```
Router   pick your mode             write new → Phase 1-5 · refactor legacy → refactor
                                   disciplines + Phase 2-5 · review → checklist + smell catalog
Phase 1  Before typing (≤2 min)     contract · data scale N · hot path? · latency vs throughput
                                   → complexity budget (tiny script vs N>10⁵ hot path)
Phase 2  Design                    data structure choice table · layering · pure core / IO edge
Phase 3  Write                     hard rules: early return, SRP, DRY (rule of three),
                                   no dead code, no magic values, no boolean traps, CQS…
Phase 4  Performance               "always do" list (hoist invariants, batch/parallel IO,
                                   index before loop…) vs "measure first" micro-opts
                                   + structure-vs-constant-cost trade-off awareness
Phase 5  Pre-delivery self-check   10-item checklist, iterate until it passes
─────────────────────────────────
Refactor mode                      lock behavior (characterization tests) → preserve & label
                                   quirks → prove equivalence (differential fuzz) → explicit
                                   compat shims → report; verification depth ∝ change risk
Red lines                          7 spaghetti signals → stop and refactor, don't stack
```

Two references load **on demand** (they stay out of context until needed):

| File | Loaded when |
|---|---|
| `references/performance-patterns.md` | designing for performance / optimizing / debugging slowness — data-structure table, hot-path ritual, IO & memory & concurrency patterns, 12 anti-pattern → fix pairs, measurement method, per-language notes |
| `references/code-smells.md` | reviewing / refactoring / a red line fires — 20 smells as symptom → cause → prescription, plus refactoring safety rules |

## Install

### DeepSeek Harness (DSH)

Copy the `dsh-bettercode/` directory into your user skill root (auto-discovered,
no restart needed):

```
~/.dsh/skills/dsh-bettercode/
```

Or make it project-scoped:

```
<project>/.dsh/skills/dsh-bettercode/
```

### Other agents (Claude Code / Cursor / Codex CLI / Gemini CLI / opencode)

The skill is a plain `SKILL.md` + `references/` bundle. Drop it into the
skill/rules location of your tool, or paste `SKILL.md` into your system rules.

## Usage

- **Automatic**: the description matches writing / refactoring / reviewing /
  optimizing tasks, so compliant hosts load it on their own.
- **Manual**: "Use dsh-bettercode to implement/refactor …"

## Effectiveness (A/B)

Validated with same-model A/B runs (with skill vs without) on three tasks.
Full data in [EVALUATION.md](EVALUATION.md):

- **Refactor legacy spaghetti** (137-line god function, 20 planted smells,
  O(n²) lookups, bare `except:`, boolean trap): both groups passed a 400-case
  randomized differential test (behavior provably identical). The skill group
  eliminated ~19.5/20 smells vs ~17/20, kept the orchestrator at 47 lines
  (vs 80), fixed the boolean trap the baseline kept, and documented preserved
  quirks and the complexity argument in the module docstring.
- **Code review of the same file** (26 planted issues): skill group recall
  26/26 vs ~24/26 baseline, 9 vs 7 performance findings, and a consistent
  smell taxonomy instead of ad-hoc wording.
- **New performance-sensitive component** (sliding-window rate limiter):
  both groups chose the optimal deque design and scored 100/100 on the AST
  quality rubric — on well-specified greenfield tasks a strong baseline model
  already performs; the skill's edge there is explicit complexity arguments
  and refusal of unmeasured micro-opts.

Honest takeaway: the skill does not turn bad output into good output — modern
baseline models already write decent code. It makes the *ceiling behavior
deterministic*: full-coverage reviews, disciplined refactors, documented
trade-offs, every time.

## Design principles of this skill itself

- **Checkable rules over vague advice.** "≤ 40 lines" is verifiable;
  "write clean code" is not.
- **Minimal resident context.** SKILL.md is deliberately short; the handbooks
  load only when the phase calls for them.
- **Both failure modes.** Spaghetti *and* premature optimization are
  addressed — micro-opts require profile evidence, written into comments.
- **Gates, not slogans.** Every phase ends with a checklist that blocks
  delivery until it passes.

## License

MIT
