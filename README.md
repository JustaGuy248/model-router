# Model-Router Pipeline

Read a project plan (markdown or prose) and tag **each task with the cheapest
model tier capable of doing it** — `local` / `haiku` / `sonnet` / `opus` — to
maximize token efficiency.

**Output:** a task breakdown table (`task | model tier | reason | est. tokens`)
plus an estimated **cost / token savings vs. running everything on the top
model** (Opus).

```
$ python analyze_plan.py examples/plan_saas_mvp.md
...
Total tasks        : 12
Est. total tokens  : 38,571
Cost (routed)      : $0.5593
Cost (all opus  ) : $1.8056   <- baseline: everything on the top model
Savings            : $1.2462  (69.0% cheaper)
```

## Why this exists

A rule-based router is only worth it if the routing decision is cheaper than
the waste it prevents — which, for a free deterministic scorer, it always is.
The real payoff is the **rollup**: "you were about to run all 12 tasks on Opus;
you actually need Opus for 1 — here's your ~69% cost cut." That headline number
is the point; the per-task table is how you audit it.

## Install & run

Zero runtime dependencies — standard library only. Python 3.9+.

```bash
# from the model-router/ folder
python analyze_plan.py <plan.md>            # text table + savings rollup
python analyze_plan.py <plan.md> --json     # machine-readable JSON
python analyze_plan.py <plan.md> --tiebreaker mock   # resolve ambiguous tasks
cat plan.md | python analyze_plan.py -      # read from stdin

# tests (offline, no API key)
pip install pytest
python -m pytest -q
```

The input can be a markdown to-do list (numbered or bulleted, nested, with or
without `[ ]` checkboxes) **or** free-text prose — imperative sentences are
extracted as tasks. Headings become section labels; fenced code blocks and
blockquotes are ignored.

## Tier criteria (the rubric)

Defined as auditable data in [`router/rubric.py`](router/rubric.py). Edit the
weights, thresholds, or examples there and every number the tool prints follows.

| Tier | For | Example tasks |
|------|-----|---------------|
| **local** | Deterministic extraction, formatting, boilerplate, regex-able work | Extract URLs from a file; reformat JSON; rename columns |
| **haiku** | Simple summaries, light reasoning, short context, low error cost | Summarize an article; classify a ticket; draft a commit message |
| **sonnet** | Multi-step logic, code, moderate context, real generation | Implement an endpoint with tests; refactor across call sites; write a landing page |
| **opus** | Novel architecture, hard reasoning, high error-cost decisions | Design a distributed system from scratch; reason about a concurrency bug; security-critical auth design |

### How a task is scored

Each task is scored **0–3 on five dimensions** (see `router/rubric.py`):

| Dimension | Weight | 0 → 3 |
|-----------|:------:|-------|
| Reasoning depth | 1.4 | lookup/extract → novel multi-hop reasoning |
| Context length | 0.8 | a sentence → whole-repo / multi-doc |
| Creativity | 1.0 | mechanical → open-ended invention |
| Tool use | 0.9 | none → orchestrates many tools/agents |
| Cost of being wrong | 1.3 | throwaway → irreversible / security / money |

The scorer ([`router/scorer.py`](router/scorer.py)) matches **signal keywords**
per dimension (add a word to the `SIGNALS` table, not to the logic), takes the
weighted sum as a `difficulty`, and picks the **cheapest tier whose cutoff
covers it**. The chosen dimension scores and the exact keyword that fired are
recorded, so the `reason` column is honest rather than hand-wavy.

Two safety behaviours:
- **Unknown tasks** (no keyword fired) never route to `local` — they default to
  `haiku` and are flagged ambiguous.
- **Boundary tasks** (difficulty near a tier cutoff) are flagged `ambiguous` and
  are the only tasks the optional tie-breaker touches.

## The hybrid routing engine

1. **Heuristic scorer first** — fast, free, deterministic, no network. This
   decides every task on its own.
2. **Optional Haiku tie-breaker** — only *ambiguous* (near-boundary) tasks are
   (optionally) escalated to a cheap LLM call. It is **off by default** and the
   whole tool runs with **no API key**.

### Enabling the Haiku tie-breaker

```bash
# off (default) — heuristic only
python analyze_plan.py plan.md

# mock — deterministic offline tie-breaker (no key, used in tests/demos)
python analyze_plan.py plan.md --tiebreaker mock

# haiku — live Haiku call for ambiguous tasks
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...        # PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python analyze_plan.py plan.md --tiebreaker haiku
```

The tie-breaker is **pluggable**: it is just a callable
`(task_text, candidate_tiers) -> chosen_tier` (see
[`router/tiebreaker.py`](router/tiebreaker.py)). The live `haiku` mode is
**fail-safe** — if the package or key is missing, or the call errors, it falls
back to the cheapest candidate and never crashes the run. Reassigned tasks are
marked with a `*` in the table.

## Layout

```
model-router/
  analyze_plan.py        # CLI entry point
  router/                # importable core (stdlib only)
    rubric.py            # tier + dimension definitions (auditable data)
    decompose.py         # plan -> atomic tasks (markdown + prose fallback)
    scorer.py            # heuristic scorer + signal table -> tier
    pricing.py           # per-tier token pricing + cost math
    tiebreaker.py        # optional, pluggable Haiku tie-breaker
    formatter.py         # table + savings rollup + JSON
    pipeline.py          # glue: analyze_plan(text) -> PlanReport
  examples/              # 3 sample plans (saas, data pipeline, prose)
  tests/                 # offline pytest suite (35 tests)
```

## Pricing

Per-tier rates live in [`router/pricing.py`](router/pricing.py) as USD per 1M
tokens (input/output), with `local` at $0. They default to representative list
prices for the 2026 Claude line-up; **swap in your real contract rates** and
every cost/savings number updates.

## Using the core programmatically

```python
from router import analyze_plan
from router.formatter import render_text, render_json

report = analyze_plan(open("plan.md").read(), tiebreaker="off")
print(render_text(report))          # human table
print(render_json(report))          # JSON for tooling
print(report.savings_pct)           # 69.0
```

## Roadmap: skill / MCP server

The core is deliberately a dependency-free importable package with a clean
`analyze_plan(text) -> PlanReport` entry point and a JSON renderer, so it can be
wrapped without change:

- **Claude skill** — a thin `SKILL.md` + wrapper that calls `analyze_plan` and
  returns `render_text` / `render_json`. The rubric doc doubles as the skill's
  instructions.
- **MCP server** — expose one tool, `analyze_plan(plan_text, tiebreaker="off")`,
  returning `render_json(report)`. No refactor needed: the pipeline already
  separates parsing, scoring, tie-breaking, and formatting.

## Backlog status

- [x] 1. Scaffold
- [x] 2. Tier rubric as documented data structure
- [x] 3. Task decomposer (markdown lists + prose fallback)
- [x] 4. Heuristic scorer + rules → tier, pricing table
- [x] 5. Optional Haiku tie-breaker (pluggable, off by default)
- [x] 6. Output formatter (table + savings rollup + JSON)
- [x] 7. CLI + 3 sample plans + pytest suite
- [x] 8. README finalize + verification

## License

Internal / private (CraigOS). Not for redistribution.
