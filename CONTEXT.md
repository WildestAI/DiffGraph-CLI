# DiffGraph-CLI — Project Context

> **Read this before working on anything in this project.**

---

## The North Star

> *WildestAI turns code changes from raw diffs into understandable, evidence-linked software evolution.*

**The durable triad — always return to this:**
1. **What changed?** (not just lines/files — components, behavior, APIs, dependencies)
2. **Why did it change?** (intent, prompt, decision, constraint, alternative considered)
3. **What is the impact?** (runtime behavior, risk, test coverage, architectural drift, future agents)

Everything else — CLI, VS Code, GitHub, Vibinex, graphs, dashboards — is a surface in service of this triad.

---

## The Problem We're Solving

AI has made code *generation* cheap. Verification is now the bottleneck.

The METR 2025 study (see `docs/research/METR-2025-summary.md`) found that experienced developers with AI tools were **19% slower**, not faster — on large, mature codebases they knew well. The cause: low AI reliability, wasted time reviewing AI outputs, and a mismatch between perceived and actual productivity gains.

Avikalp's personal experience: the more he uses AI to write code, the more he needs a better way to quickly understand and review what changed. That's the wedge this project exists to address.

**The core insight:**
- Reading a diff ≠ understanding a change
- Understanding a change ≠ verifying it should exist
- Traditional diffs worked when humans wrote small, deliberate changes; they break when AI generates thousands of lines in minutes

**AI mistakes are distinct from human mistakes.** AI agents:
- Overfit to the prompt
- Miss unstated architectural constraints
- Modify files outside intended scope
- Satisfy visible tests while missing hidden invariants
- Hallucinate APIs, conventions, or behavior
- Don't carry organizational memory

WildestAI should be designed around this new failure profile, not around recreating human code review with AI summaries.

---

## What This Project Is Not

- Not "AI PR summary" (that's a commodity feature, not a product)
- Not a pretty graph generator that sacrifices correctness for visual flair
- Not a thin wrapper over one LLM
- Not locked to any single surface (CLI, VS Code, GitHub)
- Not a replacement for developer judgment — a reduction of the *work required* to exercise it

**Red line:** Every claim should be traceable to evidence (code, metadata, test). No "vibes" outputs.

---

## Product Surfaces (History + Direction)

| Surface | Status | Purpose |
|---------|--------|---------|
| `wild` CLI | ✅ v1.0 built | Engine + local entry point; `wild diff` → DiffGraph |
| VS Code extension | 🔄 planned | Inner-loop: "what did this agent just do?" |
| Vibinex / GitHub extension | 🔄 planned | Middle-loop: PR review, semantic navigation |
| CI/CD integration | 🔜 future | Automated artifacts, risk flagging |
| Enterprise / on-prem | 🔜 future | Compliance, traceability, audit |
| Agent-facing layer | 🔜 future | Structured context for other AI agents |

**Current focus:** Make `wild diff` and the VS Code extension extremely useful for understanding AI-generated local changes, while designing the core representation to power everything else later.

---

## Current CLI State (as of May 2026)

The `wild` CLI (`diffgraph/`) is at **v1.0**. It:
- Wraps `git` — passes all non-diff commands through to `git`
- On `wild diff [args]`: reads git diff, sends to OpenAI (GPT-4), generates an HTML report with a Mermaid.js dependency graph
- Supports: unstaged, staged (`--staged`), commit ranges, specific files
- Outputs: HTML report (`diffgraph.html`) auto-opened in browser

**What it does well:** Basic diff → HTML graph pipeline works.

**What it lacks (next iteration targets):**
- Semantic understanding (it's currently textual diff → LLM summary → Mermaid graph; not true AST/call-graph analysis)
- Machine-readable output (JSON artifact, not just HTML)
- Intent capture (no way to attach prompt/task context to a change)
- Multi-file relationship mapping (each file analyzed somewhat independently)
- VS Code extension integration
- Speed (single-threaded, sequential file processing)
- Model agnosticism (hardcoded OpenAI)

See `docs/Roadmap-v1-git-wrapper.md` for the v1 architecture spec.

---

## The Three Loops (Lifecycle Model)

**Inner loop** — Local development. "What just changed, why, should I continue?"
- Surfaces: Terminal, CLI, IDE, agent workflows
- This is where DiffGraph-CLI lives today

**Middle loop** — Collaboration and review. "Can another human responsibly approve this?"
- Surfaces: GitHub, GitLab, Vibinex, PR comments
- DiffGraph artifacts should power this eventually

**Outer loop** — Organizational memory. "How has the system evolved, can we trust the process?"
- Surfaces: Dashboards, audit trails, compliance systems, agent context stores
- Long-term direction, not near-term focus

**Don't get trapped in the inner loop.** It's the wedge; lifecycle-wide understanding is the larger opportunity.

---

## Design Principles (Distilled)

1. **Evidence over vibes** — Every claim links to code. "This changes auth middleware in auth.ts" not "this improves auth."
2. **Understanding before automation** — Help users understand and decide first. Earn trust before automating.
3. **Reduce cognitive load, not agency** — Show the map. Don't make the decision.
4. **Experienced developers first** — Power tool feel, not tutorial. Fast, accurate, controllable.
5. **Accuracy > elegance** — A wrong graph is worse than no graph. Ship trustworthy before pretty.
6. **Latency matters** — This lives in the developer loop. Slow = unused.
7. **Model agnostic** — Don't couple the core to OpenAI. Static analysis + LLM should complement each other.
8. **Representation flexible** — Graph is a strong hypothesis, not sacred. Ask "what representation helps this user at this moment?"

---

## Evaluation Criteria (use for every feature decision)

| Dimension | Question | Target |
|-----------|----------|--------|
| Problem centrality | Does this attack code-change understanding? | 9+/10 |
| Developer usefulness | Would an experienced dev use this in a real workflow? | 8+/10 |
| Accuracy | Are affected components and relationships correct? | 9+/10 |
| Evidence quality | Can claims be traced to code or metadata? | 8+/10 |
| Non-commoditization | Is this more than a generic AI summary? | 9+/10 |
| Latency | Fast enough for the loop it sits in? | 8+/10 |

**If a feature scores low on problem centrality or non-commoditization, treat it skeptically.**

---

## Open Questions (to be explored, not assumed)

1. **Fastest path to repeated usage** — CLI diff? VS Code after AI edits? GitHub PR? CI artifact?
2. **Best representation** — Graph, tree, sequence, risk-first review path, hybrid? Discover through usage.
3. **Local vs cloud tradeoff** — Local = privacy + fit; Cloud = collaboration + heavy analysis; Hybrid likely.
4. **Minimum trustworthy analysis** — Define a narrow trust boundary early. "We reliably identify changed symbols and dependency relationships for TypeScript/Python repos under 100k LOC" beats generic claims.
5. **Durable memory artifacts** — What should be stored long-term? DiffGraph, intent, risk signals, review decisions, architecture constraints.

---

## Reference Documents

| Doc | What it covers |
|-----|---------------|
| `docs/WildestAI-vision.md` | Full 22-section WildestAI handover context (deep reference) |
| `docs/research/METR-2025-summary.md` | Why AI slows experienced developers on mature codebases |
| `docs/research/IndiaFOSS-2025-diffs-dont-scale.md` | "Diffs Don't Scale" talk — the public-facing problem statement |
| `docs/Roadmap-v1-git-wrapper.md` | v1 CLI architecture spec |
| `docs/Roadmap-v0-initialize.md` | v0 initialization notes |
| `CHANGELOG.md` | Version history |

---

## Working With This Project

**Before any session:**
1. Read this file (CONTEXT.md)
2. Check `CHANGELOG.md` for current version
3. Look at the relevant roadmap doc for the current milestone

**Before writing any code:**
- Score the proposed change against the evaluation criteria above
- If it doesn't attack code-change understanding at 9+/10, stop and ask why we're doing it

**Guiding question for every decision:**
> *Does this make code changes easier to understand, safer to verify, and easier to trace?*
