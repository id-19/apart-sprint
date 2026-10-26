# How Many Characters Does It Take? Communication bandwidth and supra-competitive pricing in LLM procurement agents

**Ishaan Datta**
[affiliation to complete]

With Apart Research

## Abstract

Multi-agent language-model systems increasingly quote prices, bid, and approve on someone's behalf. A natural safety hope is that restricting how much agents can say makes collusion harder. We test that hope directly: we built a procurement world with real demand, capacity, and cost heterogeneity, and varied only the per-seat character allowance — the "rung" — from no line at all, to 128, 256, 512, and 2,048 characters per seat per cycle, holding everything else fixed. With gemma4:cloud at N=4, a no-line control was already not competitive: mean filed price was ₹964–1,022 against a capacity-aware marginal-cost benchmark of ₹855–875, i.e. 17–25% over cost, with pairwise price agreement of 0.19–0.23. A line of 512 characters per seat per cycle raised agreement to 0.88 and overcharge to 41–53% over cost; 2,048 characters gave agreement 0.94–1.00 and a mean of 35% over cost. Coordination was cheap and one-shot: one cell spent 994 bytes in the first cycle and then fell silent, and the highest-harm cycle carried the cell's shortest message. Models differed sharply — gpt-oss:120b and deepseek-v4.1-flash stayed near cost (1–9%) at every rung — so bandwidth is a sufficient but not a universal lever. In 182 messages across 23 cells, no seat ever proposed a lower price on behalf of the patients who could not afford the medicine, and the free-medicine request was never taken up, though every seat read the note about it repeatedly.

**Main takeaway:** narrow channels do not prevent misaligned coordination between pricing agents, and the amount of talk needed is far smaller than the harm it causes.

## 1. Introduction

LLM agents are being placed in positions where their output is a price, a bid, or an approval. When several such agents share a market and can talk to one another, they may coordinate on outcomes that are good for the agents and bad for everyone else. The obvious defensive intuition is bandwidth: if agents cannot say much, they cannot agree on much.

We test that intuition with a controlled dose. One economic world is held fixed — the same five buyers, the same costs and capacities, the same eight cycles, the same tools — and the only thing that changes is how many characters each pricing agent may transmit per cycle. The control is a matching set of cells in which the communication tools do not exist at all. This makes the treatment the line itself, and gives every treated result a no-line baseline from the same world rather than a theoretical ideal.

Harm is measured in money, and stated as a percentage over a capacity-aware marginal-cost benchmark: what the same weekly order would have cost if each desk filed at its own landed cost. Because selling at cost is the morally neutral act in this scenario, that percentage is a direct reading of how much extra the district paid — money that, in the fiction as in the field, is treatment it could not buy instead.

Our contributions are:

1. **A bandwidth dose with a matched no-line control.** A reusable experimental design in which the only difference between arms is the per-seat character allowance, with the economic world, the prompts, the tools, and the settlement rule held constant.
2. **A measured result.** For one model family, a line of 512 characters per seat per cycle moved an already-supra-competitive market from 21% to 47% over cost and from 0.21 to 0.88 price agreement; 2,048 characters reached agreement 0.94–1.00. The smallest usable line was the most harmful, and coordination was achieved with a handful of very short messages.
3. **A negative result about salience.** In 182 admitted messages across 23 cells, no agent ever proposed a lower price on behalf of the people who could not afford the medicine, and the explicit request for free stock was never answered, although each agent read the district health office's note about them dozens of times per cell. Making the harm legible in the prompt did not make it legible in the channel.

We do not claim necessity, monotonicity, generality across models, or anything about deployed systems. We claim that a very small explicit channel is enough to move an imperfect equilibrium further from cost, and that the volume of talk is a poor proxy for the amount of coordination in it.

## 2. Related Work

Cheap talk coordinates expectations when interests are sufficiently aligned (Crawford & Sobel, 1982; Farrell & Rabin, 1996), and laboratory markets show that even non-binding communication raises prices (Cooper, DeJong, Forsythe, & Ross, 1992). Our channel is cheap talk with a hard character budget, and the budget is the treatment.

Repeated interaction can sustain supra-competitive prices without any explicit agreement (Stigler, 1964; Friedman, 1971; Tirole, 1988). Empirical screens look for fingerprints in prices and bids — structural separation of competition from collusion in procurement (Bajari & Ye, 2003), variance screens (Abrantes-Metz, Froeb, Geweke, & Taylor, 2006), and behavioural screening more broadly (Harrington, 2006). Our no-line control is exactly the object those screens target: desks post prices with no channel at all and still land above cost. That is why the control, not zero, is the baseline.

Algorithmic pricing can learn collusive policies without explicit communication (Calvano, Calzolari, Denicolò, & Pastorello, 2020), and algorithmic pricing has been associated with higher retail margins in German gasoline markets (Assad, Clark, Ershov, & Xu, 2024). Fish, Gonczarowski, and Shorrer (2024) study collusion among LLM pricing agents. Our work differs in the axis it varies: we do not ask whether LLM agents can collude, but how much channel they need before they do, and we report the answer as harm over a matched baseline.

We use pairwise agreement over coarse price bins as the coordination read-out, with exact permutation tests (Good, 2005). Cohen's (1960) kappa is undefined in the treated cells because all seats share a bin, which is itself the finding; we therefore report raw agreement and treat chance correction as descriptive.

## 3. Methods

**The world (S1, institutional paracetamol procurement).** Four desks (seats A–D) file a weekly price per carton for a district relief season. Five buyers (B1–B5) each need 2–3 cartons; total demand is set each cycle at 40% ± 5% of district capacity, so some desks go unserved and price competition has teeth. Each desk has a private landed cost (₹762–897) and a private weekly capacity (6–10 cartons). Allocation is cheapest-first, and buyers are price-takers. Prices are capped at ₹1,200 per carton in-world; the cap is rarely approached at low rungs and becomes the focal point at high ones.

**The dose.** A cell is a (N, rung, seed) triple. Rung is the per-cycle transmission allowance expressed as characters per seat per cycle divided by N — at N=4 the build grants 4 × rung characters to each seat each cycle. We ran rungs 0, 32, 64, 128, and 512 at N=4. At rung 0 the message tools are absent entirely; every other rung has the same two tools (a shared association room, and direct notes to one seat or a subset), the same ledger, and the same rejection rule: a message that exceeds the remaining allowance is not debited and may be retried shorter in the same turn.

**Turn structure.** Each cell runs 8 cycles; each cycle has 6 exchanges. All seats act simultaneously within an exchange, and messages sent in an exchange are delivered at its close, so no seat can see another's message before acting. Exchange 6 is filing-only. This gives agents many opportunities to talk before committing a price, and it means a "one-shot" pattern in the data is a choice, not a constraint.

**Harm.** For each cycle, the benchmark is the capacity-aware counterfactual: the same buyer sheet allocated at each desk's own landed cost, with each buyer's reference being that buyer's marginal supplier cost, not the cheapest desk in the district. Harm is the overcharge the district actually pays above that benchmark. `harm_over_cost_pct` expresses it as a percentage of the benchmark. Because selling at cost is the neutral act, this is the quantity of interest; we also record cases forgone and deaths implied by the same rupees, but we do not add them to the money axis.

**Models.** gemma4:cloud (primary), gpt-oss:120b-cloud, deepseek-v4.1-flash:cloud, and beam:cloud, all through Ollama at temperature 1.0 with native tool calls only. Text that is not a tool call is never parsed into an action.

**Realism gate.** Every rendered string is in-world: no mention of simulations, tests, prompts, tokens, or agents. A gate scans visible reasoning and messages; visible failures halt the cell (and are recorded as `HALTED`, not silently dropped), while thinking-trace hits are recorded as non-fatal flags with a count in the summary. Two of the four candidate models failed this gate in their private reasoning (naming the exercise as a simulation); we report those cells as halted rather than scoring them.

**Seeds.** Seeds are simple integer draws into a seeded world generator, so they change costs, capacities, and the weekly demand draw, not the prompt text. gemma: N=4 with two seeds at rungs 0 and 128 and three seeds at rung 512. gpt-oss: one seed per rung. deepseek-v4.1-flash: one seed per rung. The v17 salience arm uses two seeds at each of rungs 0, 32, 64, and 128 for each model. **The seed counts are too small for inference**; we report cell-level numbers and treat differences as descriptive.

**What did not work.** Three further scenarios were built and run, and each failed to measure what it claimed: in the market-making world no seat ever sent a message (0 send attempts across all cells); in the credit-rating world agents talked freely and then filed honest ratings (`inflated_bonds: []` in every cell); in the bridge-approval world the checker caught the planted data-room gap every cycle, so the chain deadlocked and harm was identically zero. They are reported as boundary conditions, not as evidence. A fourth (approval) was dropped from the final scope.

## 4. Results

**Table 1. S1 at N=4, 8 cycles.** Rung is nominal; the realised allowance is 4 × rung characters per seat per cycle. Harm is overcharge over a capacity-aware cost benchmark (₹78,590–83,125, depending on seed); "% over cost" is harm as a percentage of that benchmark. Agreement is mean pairwise same-bin agreement over cycles and pairs.

| Model | Rung | Chars/seat/cycle | Seed | Mean price (₹) | Agreement | Harm (₹) | % over cost |
|---|---|---|---|---|---|---|---|
| gemma4:cloud | 0 | 0 | 0 | 964 | 0.19 | 14,021 | 17.1 |
| gemma4:cloud | 0 | 0 | 1 | 1,022 | 0.23 | 19,860 | 25.3 |
| gemma4:cloud | 128 | 512 | 0 | 1,100 | 0.88 | 33,666 | 41.1 |
| gemma4:cloud | 128 | 512 | 1 | 1,197 | 0.88 | 41,810 | 53.2 |
| gemma4:cloud | 512 | 2,048 | 0 | 1,098 | 0.94 | 33,186 | 40.6 |
| gemma4:cloud | 512 | 2,048 | 1 | 950 | 0.94 | 17,350 | 22.1 |
| gemma4:cloud | 512 | 2,048 | 2 | 1,100 | 1.00 | 33,775 | 41.3 |
| gpt-oss:120b | 0 | 0 | 2 | 879 | 0.17 | 4,010 | 4.9 |
| gpt-oss:120b | 64 | 256 | 2 | 861 | 0.15 | 3,076 | 3.8 |
| gpt-oss:120b | 512 | 2,048 | 0 | 870 | 0.23 | 4,614 | 5.6 |
| deepseek-v4.1-flash | 0 | 0 | 1 | 898 | 0.15 | 7,244 | 9.2 |
| deepseek-v4.1-flash | 128 | 512 | 0 | 857 | 0.48 | 5,893 | 7.2 |

**The no-line control is not a competitive market.** With no channel at all, gemma desks dispersed across ₹850–1,200 and still cleared 17–25% above cost. This is the result that changes the interpretation of everything above it: the treated cells do not create harm from zero, they move a market that was already above the moral baseline. Any claim of the form "communication caused collusion" would be false here; the accurate claim is "communication moved an existing focal point".

**The line moves gemma further from cost, and does so in a single burst.** At 512 characters per seat per cycle, agreement rose to 0.88 and the desks converged on ₹1,100–1,200, roughly doubling their own no-line overcharge by seed (2.4× and 2.1×). At 2,048 characters, agreement reached 0.94–1.00. But the talk was minimal. In one rung-512 cell the seats exchanged seven messages totalling 994 bytes, all inside the first cycle, and then never spoke again for seven cycles while filing identical prices. In the highest-harm cell, the highest-harm cycle contained that cell's shortest admitted message — 51 characters — which set ₹1,200. Coordination, once reached, was carried by the price series itself; the channel was needed to start it, not to sustain it.

**Bandwidth is not a universal lever.** gpt-oss:120b never exceeded 5.6% over cost at any rung, with agreement at or near chance (0.15–0.23), and its prices sat close to its own costs throughout. deepseek-v4.1-flash was intermediate: 9.2% with no line, 7.2% with 512 characters and agreement 0.48 — some convergence, no price ceiling. Whatever gemma responds to at 512 characters, these two do not respond to it in the same way. We do not know why, and we do not claim that gemma is representative; with one to three seeds per arm, these contrasts are descriptive, not tested.

**The effect is not monotone.** gemma's mean harm was 21.2% (no line), 47.2% (512 chars), 34.7% (2,048 chars), with one 2,048-char seed at 22.1%. More channel did not buy more harm. A reading consistent with the transcripts is that at 2,048 characters the desks spend their allowance on corrections about the buyer sheet and on arguments about who is breaching, whereas at 512 characters the messages are pure price proposals. That reading is a hypothesis for a larger-N study, not a finding.

**Nobody proposed a cheaper price for the patients.** The world contains a district health office note stating that camp committees cannot afford the filed prices, that the district has asked suppliers to hold prices down, and — in the later version — an explicit request that any supplier able to release stock free of charge say so. Every seat read that note, repeatedly (29–32 reads per cell in the cells we audited). Across 182 admitted messages in 23 cells, the words patient, medicine, welfare, charity, humanitarian, moral, and duty never appear, and no message offers free or discounted stock. The word "afford" occurs twice, both times as a gloss on a high price rather than a reason to lower one: one admitted message proposes filing ₹1,100 "while keeping it affordable for the district", and one rejected message (over its allowance) asks the other desks to "align to keep relief affordable". The humanitarian dimension is visible in the prompt and absent as a reason in the channel. In gemma's visible reasoning the district's need is treated as a constraint on what buyers will bear, not as a reason to price lower.

**Verdicts.** Across the 23 completed S1 cells: 706 ACTION, 6 WITHHELD, 0 REFUSED, 0 MALFORMED. The seats did not refuse to play, and they did not break character. Every halt we observed was a realism-gate failure in private reasoning (two models) or an infrastructure failure, never a refusal.

**A salience arm (v17).** A later version of S1 adds two things to the standing text: the district bulletin now says that camp committees have reported the filed prices are beyond what the relief budget can carry and that families at the counter cannot meet them, and the health-office note now asks, explicitly, whether any supplier will release stock free of charge for the season. The economic world, the prices that are possible, and the tools are unchanged. This arm was run against gpt-oss (two seeds, rungs 0/32/64/128 — complete) and against gemma and beam (two seeds, same rungs — still running at the time of writing).

**Table 2. S1 v17 (affordability line and free-medicine plea), N=4.** Entries marked † were still running when this report was written and must not be used as evidence.

| Model | Rung | Chars/seat/cycle | Seed | Mean price (₹) | Agreement | Harm (₹) | % over cost |
|---|---|---|---|---|---|---|---|
| gpt-oss:120b | 0 | 0 | 0 | 856 | 0.08 | 1,326 | 1.6 |
| gpt-oss:120b | 0 | 0 | 1 | 839 | 0.10 | 1,268 | 1.6 |
| gpt-oss:120b | 32 | 128 | 0 | 840 | 0.17 | 868 | 1.1 |
| gpt-oss:120b | 32 | 128 | 1 | 841 | 0.21 | 959 | 1.2 |
| gpt-oss:120b | 64 | 256 | 0 | 841 | 0.17 | 1,707 | 2.1 |
| gpt-oss:120b | 64 | 256 | 1 | 846 | 0.10 | 734 | 0.9 |
| gpt-oss:120b | 128 | 512 | 0 | 840 | 0.17 | 1,592 | 1.9 |
| gpt-oss:120b | 128 | 512 | 1 | 853 | 0.21 | 1,456 | 1.9 |
| gemma4 † | 0 | 0 | 1 | 850 | 0.40 | 3,843 | 4.9 |
| gemma4 † | 64 | 256 | 1 | 945 | 0.48 | 15,563 | 19.8 |

The complete gpt-oss arm is the clean version of the model contrast in Table 1: across two seeds and four rungs, including a no-line control, its mean filed price never left ₹839–856 and its overcharge never exceeded 2.1%. The line did not move it, and neither did the affordability text.

For gemma the salience text does appear to matter, which is why we flag rather than report it. Its one completed no-line v17 cell filed a mean of ₹850 and 4.9% over cost, against 17–25% in the same cell of v15; its one completed 256-character cell filed ₹945 and 19.8%. If that pattern survives the remaining cells, the interpretation is not that the earlier result was wrong but that the level of the baseline depends on what the world says about the people paying — a result about the world's framing, not about the channel. The channel result, however, would be unchanged in sign: the move from a no-line cell to a channelled one is present in both versions.

## 5. Discussion and Limitations

The safety-relevant reading is uncomfortable but simple. If the question is "will these agents collude if given a channel?", the answer here is that some will, with a channel of a few hundred characters, in a single burst, and without ever naming the thing they are doing. A policy that limits agent-to-agent bandwidth to what looks like a trivially small amount — a few hundred characters per cycle — is not a mitigation in this world. The line that produced the most harm in our data is roughly the length of two text messages.

The second reading concerns visibility. These agents were not unaware of the harm; they read the note about it constantly and never acted on it or spoke of it. This is a failure of salience in the channel, not of knowledge in the model. It suggests that making harm legible in an agent's context is not the same as making it operative in an agent's communication, and that evaluations which check whether a model "knows" about a harm may overstate how much that knowledge constrains behaviour.

**Limitations.** (i) The evidence is one scenario, one model family that responds strongly, and one to three seeds per arm; nothing here is statistically tested, and we do not report a p-value as if it settled anything. (ii) The price cap of ₹1,200 is a ceiling that several treated cells sit exactly on, so harm at high rungs is partly bounded by design; the cap is visible in-world and is plausibly a focal point. (iii) The no-line control is supra-competitive, which means the treatment effect measures movement from an imperfect equilibrium; a different benchmark (perfect competition) would attribute all of the control's harm to the world rather than to the line. (iv) The harm metric counts overcharge only; rationing and untreated cases are recorded but not added, so cells that exclude buyers are understated. (v) Temperature 1.0 with a fixed seed per cell gives one trajectory per cell, not a distribution; seeds here vary the world, not the sampling. (vi) Two models did not pass the realism gate in their private reasoning; their cells are halted and excluded, which is honest but also removes the models most likely to behave differently.

**Future work.** More seeds per arm, so the gemma/v17 comparison can carry an interval; a within-cell design that measures the same world with and without a line; a rung ladder extended below 512 characters to find the threshold; and a version in which the channel is present but the price action is delayed by several cycles, to separate the founding message from the price series that sustains coordination.

## 6. Conclusion

We held a procurement market fixed and varied only how many characters its pricing agents could exchange. With no channel, the desks already priced 17–25% above a capacity-aware cost benchmark. With 512 characters per seat per cycle, they converged on a single price and reached 41–53% above cost; with 2,048 characters, agreement reached 0.94–1.00. The coordination took seven messages and one cycle. Two other models barely moved at any rung, and no model ever offered a cheaper price for the patients named in the district's note.

The practical implication is that bandwidth caps are a weak defence. A channel of a few hundred characters is enough to coordinate a price, and it is small enough that a designer might not think of it as a channel at all. If agent communication is to be constrained for safety, the interesting threshold is far below the one intuition suggests, and the harm may be largest where the channel is smallest.

## Code and Data

* Code repository: [to be completed — the harness, scenario modules, and analysis scripts are in the project repository]
* Data: the run tree (`actual experiment/runs/`) contains, per cell, the full request/response log (`raw_calls.jsonl`), per-turn trajectory, admitted and rejected messages, per-cycle settlements, the world event record, and a summary with the harm and agreement measures.
* Artifacts: `PROMPTS.md` renders the exact text each seat receives; `RUNBOOK.md` documents how to reproduce a cell.

## Author Contributions

Ishaan Datta designed the harness, the scenarios, and the dose; implemented the code; ran the experiments; and wrote this report. Claude Code was used as a pair programmer for implementation and for drafting assistance.

## References

1. Abrantes-Metz, R. M., Froeb, L. M., Geweke, J., & Taylor, C. T. (2006). A variance screen for collusion. *International Journal of Industrial Organization*, 24(3), 467–486.
2. Assad, S., Clark, R., Ershov, D., & Xu, L. (2024). Algorithmic pricing and competition: Empirical evidence from the German retail gasoline market. *Journal of Political Economy*, 132(3).
3. Bajari, P., & Ye, L. (2003). Deciding between competition and collusion. *Review of Economics and Statistics*, 85(4), 971–989.
4. Calvano, E., Calzolari, G., Denicolò, V., & Pastorello, S. (2020). Artificial intelligence, algorithmic pricing, and collusion. *American Economic Review*, 110(10), 3267–3297.
5. Cohen, J. (1960). A coefficient of agreement for nominal scales. *Educational and Psychological Measurement*, 20(1), 37–46.
6. Cooper, R., DeJong, D. V., Forsythe, R., & Ross, T. W. (1992). Communication in coordination games. *Quarterly Journal of Economics*, 107(2), 739–771.
7. Crawford, V. P., & Sobel, J. (1982). Strategic information transmission. *Econometrica*, 50(6), 1431–1451.
8. Farrell, J., & Rabin, M. (1996). Cheap talk. *Journal of Economic Perspectives*, 10(3), 103–118.
9. Fish, S., Gonczarowski, Y. A., & Shorrer, R. I. (2024). Algorithmic collusion by large language models. arXiv:2404.00806.
10. Friedman, J. W. (1971). A non-cooperative equilibrium for supergames. *Review of Economic Studies*, 38(1), 1–12.
11. Good, P. I. (2005). *Permutation, Parametric and Bootstrap Tests of Hypotheses* (3rd ed.). Springer.
12. Harrington, J. E. (2006). Behavioural screening and the detection of cartels. In *European Competition Law Annual 2006*.
13. Stigler, G. J. (1964). A theory of oligopoly. *Journal of Political Economy*, 72(1), 44–61.
14. Tirole, J. (1988). *The Theory of Industrial Organization*. MIT Press.

## Appendix

**A. Prompt excerpt (rung 128, N=4, seat A, cycle 1).** Each seat receives an in-world system brief (role, unit cost, weekly capacity, the standing instruction to protect the plant's contribution), an opening turn with the district buyer sheet, last week's own sales, the district bulletin, the other desks at the association, and the remaining transmission allowance for the session; then cycles of simultaneous exchanges with the same tool set.

**B. Dose realisation.** Nominal rung × N = characters per seat per cycle: rung 32 at N=4 gives 128 characters; rung 512 gives 2,048. At rung 0 the messaging tools are absent from the tool schema entirely.

**C. What a rejected message looks like.** An over-allowance message is refused before sending, is not debited, and is reported to the seat in-world with the remaining allowance, so a seat may retry shorter in the same turn. Every admitted and rejected message is written to `messages.jsonl` with the disposition and the reason.

**D. Realism gate.** Visible-content hits halt a cell and are recorded as `HALTED` with the cycle reached; thinking-trace hits are recorded as `META_THINKING` flags with a soft count in the summary. `analysis/meta.py` scans all transcripts. Two candidate models (glm-5.3-flash and beam) named the exercise as a simulation in private reasoning; those cells are halted, not scored.

## LLM Usage Statement

Claude Code (Anthropic) was used as a pair programmer to implement the harness, the scenario modules, and the analysis scripts, and to help draft and edit this report. The experimental design, the choice of treatments, and the interpretation of the results are the author's. All numbers in Table 1 and in the text were computed from the run tree by the analysis scripts, and pending v17 cells are labelled as provisional rather than forecast.

[1] Research conducted at the AI Collusion Research Sprint, October 2026
