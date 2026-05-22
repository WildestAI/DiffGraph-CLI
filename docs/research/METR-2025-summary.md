# METR 2025: Impact of AI on OSS Developer Productivity

**Source:** "Measuring the Impact of Early-2025 AI on Experienced Open-Source Developer Productivity" (METR, 2025)

## Headline Finding

Experienced open-source developers using early-2025 AI tools were **19% slower** on average — not faster.

This contradicted all prior estimates:
- Economics experts forecast: **+39% speedup**
- ML experts forecast: **+38% speedup**
- Developer self-forecast (before task): **+24% speedup**
- Developer self-report (after task): still believed **+20% speedup**

The gap between perceived and actual impact is itself a key finding: developers couldn't detect the slowdown even after experiencing it.

## Methodology

- Randomized controlled trial: 16 experienced developers, 246 real tasks
- Tasks averaged 2 hours on mature, popular repos (avg. 23k stars, 1.1M LOC, 10 years old)
- Developers averaged 5 years experience, 1,500 commits on their repo
- Tasks were defined *before* randomization (avoiding AI changing task scope)
- Primary outcome: actual wall-clock completion time
- Supporting data: 143 hours of manually labeled screen recordings, exit interviews, Cursor analytics
- AI tool used: Cursor Pro with Claude 3.5/3.7 Sonnet

## What Explains the Slowdown? (Top 5 Factors)

1. **Over-optimism about AI usefulness** — Developers used AI even when counterproductive
2. **High developer familiarity** — On tasks they knew well, AI couldn't outperform deep expertise
3. **Large, complex repos** — AI performed worse in mature, sprawling codebases vs. greenfield
4. **Low AI reliability** — <44% of suggestions accepted; 9% of total time spent reviewing/cleaning AI outputs
5. **Implicit repo context** — AI lacked the tacit knowledge (conventions, edge cases, design decisions) experienced contributors rely on

## What Ruled Out

- Not from avoiding AI (used in ~84% of allowed cases)
- Not from Cursor unfamiliarity (similar for experienced Cursor users)
- Not from weak models (mostly Claude 3.5/3.7 Sonnet)
- Not from outcome measure choice (robust to alternatives)

## Relevance to WildestAI / DiffGraph-CLI

This study validates the core WildestAI thesis in two ways:

**1. Verification is the bottleneck.** The screen recordings showed developers spending *less* time coding and reading with AI, but *more* time prompting, waiting, reviewing AI code, and being idle. The generation got faster; the understanding did not. That's exactly the generation-verification gap.

**2. Organizational context matters most.** AI failed hardest where developers had the deepest contextual knowledge — mature codebases with tribal knowledge, architectural constraints, and implicit contracts. This is precisely where DiffGraph-CLI needs to help: making that hidden context visible at the moment of change.

**Quote to keep in mind:**
> "Developers accepted less than 44% of AI suggestions, and 9% of total time was spent reviewing and cleaning up AI outputs."

That 9% overhead is recoverable — if the verification step becomes significantly cheaper.
