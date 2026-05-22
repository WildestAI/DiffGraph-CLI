# "Diffs Don't Scale" — IndiaFOSS 2025 Talk

**Talk by:** Avikalp Kumar Gupta
**Conference:** IndiaFOSS / FOSS United 2025
**Full script:** See original PDF (IndiaFOSS_2025_script.pdf)

---

## The Narrative Arc

### Personal hook
In 2019, a CTO told Avikalp the path to leadership was through PR reviews. It worked. He's been obsessed with code review ever since — leading to Vibinex (a company dedicated to making PR reviews better).

### The shift
After 2 years and hundreds of users at Vibinex, AI coding tools started changing the game. Teams started generating more code, faster — but something was off.

### The problem
Sundar Pichai's own data is the irony: 30% of Google's new code is AI-generated, yet development teams are only 10% more productive. METR found AI *reduced* delivery speed by 19%.

Why? Because **AI changed the workflow**. Developers went from "author" to "prompter." They no longer have an innate understanding of the code they ship.

### Karpathy's loop
Andrej Karpathy described it best: any AI interaction is a generation ↔ verification loop. Generation got fast. Verification (which means reading the diff) is still slow.

### The thesis
**Diffs don't scale.**

Traditional git diffs worked when humans wrote small, deliberate changes. They break when AI generates thousands of lines in minutes. Verifying a huge AI-generated diff manually can take hours — only to find it's wrong, or the approach is entirely off. After that effort, will you prompt AI to fix it? Probably not. You'll take the boilerplate and fix it yourself, or git reset and start over.

### The compounding problem
It's not just one developer. Multiple people verify the same change. And the *same* diff interface appears everywhere:
- `git diff` in terminal
- Diff view in VS Code
- GitHub PR
- Git blame while debugging

**The diff is unavoidable. But it doesn't scale.**

---

## Key Points for DiffGraph-CLI Context

1. **This is Avikalp's lived experience** — the talk is autobiographical, not academic. The problem is real and personal.

2. **The framing is public** — this is how the problem will be explained to developers at conferences. DiffGraph-CLI should deliver on this promise.

3. **The METR data is key evidence** — it's called out explicitly in the talk. The empirical grounding matters.

4. **Verification can't be fully automated** — the talk sets up (beyond the script excerpt we have) that "just use AI to verify" doesn't work. You still need a human understanding the change.

5. **The opportunity:** A tool that makes the diff *comprehensible* — that turns raw line-level noise into structured, semantic, navigable change understanding — directly addresses the problem this talk describes.

---

## Elevator Pitch (from this talk)

> AI made code generation cheap. But we still review changes the same way we did in 1990 — by reading a wall of plus and minus signs. DiffGraph makes the invisible structure of your code changes visible, so you can understand what AI actually did in seconds, not hours.
