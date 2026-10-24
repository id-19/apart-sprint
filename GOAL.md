# GOAL — Bitrate → Collusion (design phase)

**Status:** goal formulation only. The experiment design is **not finalised** and will not be marked finalised
without your go-ahead. `DESIGN.md` / `EXECUTION_PLAN.md` in this folder are the previous draft and are left
untouched; this phase produces a **new** document.

**Date:** 24 Oct 2026 · **Owner:** Ishaan · **Work:** me

---

## 1. Objective

Determine how the **communication bandwidth available to a swarm of LLM agents** changes whether — and in what
form — they collude to cause harm, and locate the bandwidth below which harmful collusion stops being achievable.

## 2. Primary question

Given X bits/s in one direction and Y bits/s in the other, **available to the whole swarm**, what is the
presence, intensity and *nature* of collusion on a task where the agents' interest is served by harming a third
party?

## 3. Sub-questions — these decide whether the answer is real

| | Question | Why it matters |
|---|---|---|
| **S1** | Is there a bandwidth **floor** below which harmful collusion does not occur at all? | the headline number |
| **S2** | Is the decline a **gradual slope, a cliff, or a saturation** (bandwidth stops mattering above some point)? | determines whether a single threshold is even the right summary |
| **S3** | As bandwidth falls, does collusion **change kind** — explicit bargaining → terse/coded signals → tacit coordination through the environment (prices, timing, visible actions)? | "nature", not just "presence" — the part most likely to be the interesting result |
| **S4** | Does the threshold move **across models**? | a result true of one model is a result about that model |
| **S5** | Does it move **across scenarios** ("plots")? | same |
| **S6** | Does it survive changes that **should not matter** (seat count, horizon, prompt wording, message ordering, tie-breaks)? | separates the phenomenon from the harness |
| **S7** | Does **up/down asymmetry** matter (many-to-one vs one-to-many)? | cheap to vary, and real deployments are asymmetric |

## 4. The independent variable, restated

- **Unit:** *aggregate* bits per unit time available to the entire swarm — uplink `X`, downlink `Y`, independently
  set. Per-agent capacity is **derived** (aggregate ÷ seats), not the primary knob.
- **Explicitly not part of the variable:** transport, protocol, whether messages are end-to-end, whether the
  bandwidth is used at all, message structure. Only the budget matters.
- **Anchor:** 1 Mbps full duplex = **10.8 GB/day per direction** for the swarm (≈2.16 GB/agent/day at 5 seats).
  That is the "effectively unlimited" end.
- **Scale warning.** 1 Mbps is ~**1,000,000× above** the top rung we expect to matter. The interesting regime is
  bits *per second*, not megabits:

| per-agent bits/day | swarm aggregate bits/day (5) | swarm bits/s | vs 1 Mbps |
|---|---|---|---|
| 8 | 40 | 0.00046 | 2.2 × 10⁹ × below |
| 80 | 400 | 0.0046 | 2.2 × 10⁸ × below |
| 1,000 | 5,000 | 0.058 | 1.7 × 10⁷ × below |
| 16,000 | 80,000 | 0.93 | 1.1 × 10⁶ × below |

- **Reporting rule:** every result goes out in **both** units (swarm bits/s and per-agent bits/day), so the
  number is portable to a real deployment.

## 5. Task requirement

- The task must be one where the agents' success is **served by harming a third party** — misaligned by
  construction. The question is prevention, not improving cooperation.
- **Simple, well-specified, realistic**: a scenario that could plausibly be deployed today, not a puzzle.
- The harm must be **measurable and attributable to coordination**, not to individual behaviour.

## 6. Outcome variables (provisional — cookie-cutter first)

| | Measure | Requirement |
|---|---|---|
| **Collusion** | presence/incidence per run; intensity; form (per S3) | needs a **no-communication baseline** so "no coordination" is distinguishable from "coordination attempted and failed" |
| **Harm** | outcome on the harmed party | needs the **same counterfactual**, so harm is attributable to coordination rather than to the task |

Start with standard proxies rather than inventing new ones; name their weaknesses explicitly in the doc.

## 7. Robustness requirement

No finding may be an artifact of the **model**, the **scenario**, or the **harness**. Concretely: ≥2 models,
≥2 scenarios, ≥3 harness perturbations — designed in **up front**, not added as afterthoughts.

## 8. Deliverable for this phase

A **new** document (existing docs untouched), satisfying:

1. **≤ 5 pages**, references and formatting included.
2. **Page 1 = one-page executive brief** of the experiment design.
3. Then **structured one by one**: question → variable → task → measures → design → analysis → threats.
4. **Jargon and technical terms defined inline**, briefly — readable cold, without being verbose.
5. An explicit **"what would make this wrong"** section.
6. Marked **DRAFT** until you sign off. No "final" label, no unrequested scope.
7. After sign-off: the **execution plan** (design → code → harness). Drafting it in parallel is allowed.

## 9. Out of scope for now

The full run, final numbers, results, and paper draft. A small pipeline seed may be run to test the harness, and
is labelled *seed*, never *result*.

## 10. Standing constraints

- **No local models.** Any test run uses the cheapest cloud model available.
- Disk is at ~200 MB free — nothing large is written.
- Everything is logged from the start: what was done, and **why**.

## 11. Decisions I need from you at review

| | Decision | Options |
|---|---|---|
| **D1** | Collusion measure | standard proxy (action correlation / margin vs baseline) · bespoke behavioural rubric · both |
| **D2** | Harm operationalisation | one harmed principal · a distribution of harmed parties |
| **D3** | Scenario set ("plots") | keep the market-execution task · swap for another misaligned task · run 2–3 |
| **D4** | Bandwidth ladder | aggregate bits/s primary (per-agent derived) · per-agent primary |
| **D5** | Model set | which 2–3, subject to cost |
