# Model-Router Pipeline

Read a project plan (markdown or prose) and tag **each task with the cheapest
model tier capable of doing it** — `local` / `haiku` / `sonnet` / `opus` — to
maximize token efficiency.

**Output:** a task breakdown table (`task | model tier | reason | est. tokens`)
plus an estimated **cost / token savings vs. running everything on the top
model** (Opus).

> Status: scaffold. Full usage, tier criteria, and the Haiku tie-breaker docs
> are filled in as the build progresses (see the backlog below).

## Why

A rule-based router is only worth it if the routing decision is cheaper than the
waste it prevents — which, for a free deterministic scorer, it always is. The
real payoff is the **rollup**: "you were about to run all 12 tasks on Opus; you
actually need Opus for 2 — here's your ~70% cost cut."

## Design (defaults)

- **Delivery:** a Python CLI — `python analyze_plan.py <plan.md>`. Core logic
  lives in the importable `router/` package so it can later be wrapped as a
  Claude skill or MCP server.
- **Routing engine:** HYBRID — a fast, free, deterministic rule-based scorer
  runs first; only genuinely ambiguous tasks are (optionally) sent to a Haiku
  tie-breaker. The LLM call is pluggable, off by default, and mockable, so the
  tool runs with **no API key**.
- **Tiers:** `local` = deterministic extraction / formatting / boilerplate /
  regex-able; `haiku` = simple summaries, light reasoning, short context;
  `sonnet` = multi-step logic, code, moderate context; `opus` = novel
  architecture, hard reasoning, high error-cost.
- **Scoring dimensions:** reasoning depth, context length, creativity, tool
  use, error cost.

## Layout

```
model-router/
  analyze_plan.py        # CLI entry point
  router/                # importable core (stdlib only)
    rubric.py            # tier + dimension definitions (auditable data)
    decompose.py         # plan -> atomic tasks
    scorer.py            # heuristic scorer + rules -> tier
    pricing.py           # per-tier token pricing + cost math
    tiebreaker.py        # optional, pluggable Haiku tie-breaker
    formatter.py         # table + savings rollup
    pipeline.py          # glue: plan text -> full report
  examples/              # sample plans
  tests/                 # offline pytest suite
```

## Backlog

- [x] 1. Scaffold (folder, README, requirements, .gitignore, module layout)
- [ ] 2. Tier rubric as a documented data structure
- [ ] 3. Task decomposer (markdown lists + prose fallback)
- [ ] 4. Heuristic scorer + rules → tier, pricing table
- [ ] 5. Optional Haiku tie-breaker (pluggable, off by default)
- [ ] 6. Output formatter (table + savings rollup)
- [ ] 7. CLI + 3 sample plans + pytest suite
- [ ] 8. README finalize + verification

## License

Internal / private (CraigOS). Not for redistribution.
