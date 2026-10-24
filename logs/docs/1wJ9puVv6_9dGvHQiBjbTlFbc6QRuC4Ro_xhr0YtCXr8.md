# Agent swarm misuse: problem statement and plan

Agent swarm misuse
Apart AI Collusion sprint | Working brief | 22 October 2026
Problem statement
How does an agent swarm's willingness to carry out a harmful user request change with its size, structure, and the incentive or justification given for that request?
We want to test whether agents behave differently together than alone on the same task, especially when communication and partial information mean that not every agent sees the full harmful objective. The practical goal is to understand which swarm designs amplify misuse, and which resist it.
What we want to do
One realistic, fixed scenario. Model a bad actor using an agent or swarm to deceive a simulated customer. Keep the underlying task and ground truth constant across comparisons. A higher-severity financial mis-selling scenario is under consideration; the exact scenario is still open.
Single-model pilot first. Measure refusal, partial compliance, full compliance, and task failure separately. Use the pilot to choose a model and scenario severity with enough variation to make solo-versus-swarm comparisons informative. DeepSeek V4.1 Flash via API is the planned starting point; no activation probes or self-hosting in the initial scope.
Vary structure and size. Compare a single-agent baseline with swarms at different sizes. Candidate structures include a hierarchy or gateway, open peer communication, and restricted communication. Treat who can talk to whom, and who sees the full task, as explicit parts of the structure.
Vary incentive or framing. Test realistic reasons for serving the bad actor, such as financial benefit, an appeal to helping someone, or a direct request. Exact conditions remain open. These are prompt conditions, not an assumption that models experience rewards as humans do.
Measure misaligned behaviour. The main outcome is how much the agents cheat or deceive the target, not simply whether they finish the task. Define a graded score from known false claims and material omissions, with target decisions as a secondary outcome. Keep refusal and ordinary task failure distinct.
Proposed scope: a structure-by-size sweep at one fixed incentive, followed by an incentive sweep at one structure and size, rather than the full grid. Exact sizes, prompts, scoring rules, repetitions, and any second-model check remain open. The mole axis is out of scope. All interactions stay in a fictional sandbox.




What’s been done on this already
Anthropic paper: https://arxiv.org/html/2604.10290
Main insight according to them: A swarm is more effective but less aligned than individual agents.
Setup/methods:
Heterogenous organisation
Human-org mimicked: Consultancy team and software dev team
Tasks, very specific, 12 tasks across various stress-test scenarios
