# BRA-Audit Table 5: reconstruction and limits

This is an independent implementation of the provided paper, not author code. The user
confirmed there is no official codebase. The provided PDF and public arXiv HTML refer to a
technical supplement but do not include it. Exact replication of the printed numbers is not
possible from the disclosed information alone. This environment runs the five Table 5
conditions and produces the same metric columns; it does not promise matching numbers.

## What follows the paper

- Both BBH and MultiAgentBench-Research, with all five audit configurations: BRA at
  rho = 0.2, 0.4, 0.6, 1.0 and random placement at rho = 0.4.
- 20% compromised agents, three repetitions, Qwen3-235B-A22B-Instruct-2507 as the API
  example backbone. Smaller local backbones are explicitly alternatives.
- Unrolled execution DAG, last-audit age times closed descendant count (Eq. 7).
- Backward contexts exclude upstream audit boundaries but include the inspected endpoint;
  a bypass path preserves the unchecked ancestor (Eq. 8).
- Cumulative exposure sums weighted contexts over every graph node (Eq. 9).
- Greedy exact marginal gains, recomputed after every selection (Eqs. 11–12).
- ceil(rho * candidate count) calls scheduled per round. Mandatory final-result node
  consumes one of these slots; it is reserved before greedy/random filling.
- Audit points execute in causal order; unsafe regions recover before execution continues.
- All model input and output tokens counted, including retries after unsafe audits.

## Choices the paper leaves unspecified

| Item | Implemented, explicit choice |
|---|---|
| BBH sample | Uniform seeded shuffle of all 6,511 upstream instances, first 150; seed 42. This is not the authors' undisclosed sample. |
| Research tasks | All 100 upstream MARBLE `research_main.jsonl` tasks, retaining five agent profiles and original task text. |
| Agent count/rounds | Five logical agents, three rounds; planner, solver, critic, verifier, synthesizer. Configurable. |
| Orchestration | Small direct Python orchestrator, rather than AutoGen. Prompts and all dependencies are recorded for inspection. |
| Within-round communication | Causal agent chain plus each agent's own previous-round output. `layered` additionally feeds all prior-round outputs. |
| Online candidate mapping | Before a round, append its known structural DAG template (no generated text) to completed history and choose that round's output slots. This resolves the paper's ambiguous mapping of historical candidates to next-round outputs. No future-round graph is used. |
| Initial LastAudit | 0; first round index is 1, giving a positive initial age. Only the endpoint producer's record updates after passing audit. |
| Scheduling ties | Lexical node order. Mandatory final endpoint reserved before greedy selection. |
| Attack membership | Seeded ceil(0.2 * agent count), constant within an example, paired across audit conditions. |
| Attack mechanism | Compromised agents receive an attack system prompt instead of the normal role prompt. No oracle labels are shown to auditors. |
| Local recovery | Re-execute the whole unchecked region with the attack prompt disabled, preserving the role/profile and adding auditor feedback. This models a clean replacement, not a compromised agent voluntarily fixing itself. |
| Invalidated work | Already executed descendants of modified nodes also regenerate; any affected prior trusted checkpoint loses trust. Recompute the endpoint's unchecked region before re-auditing. |
| Retry cap | Two recovery attempts per endpoint. A persistent rejection or malformed verdict fails the example and is recorded; it does not silently pass. |
| Research tools | Original task text, supplied literature and profiles only. No live paper search, external tools, or MARBLE engine/planner. This is a task-data/rubric adapter, not a full MARBLE reproduction. |
| Research judge | Official MARBLE 1–5 innovation/safety/feasibility rubric. Score = sum of these / 15. This normalization matches Table 2's reported dimensions but the BRA paper does not give a formal scoring formula. Judge is configurable, same model by default. |
| BBH scoring | Exact match after FINAL extraction and whitespace/case normalization; standalone option labels accept A or (A). No substring matching or answer leakage. |
| Decoding | Temperature 0, 768 generated work tokens, 512 audit/judge tokens. All configurable. |

## Metrics and reporting

Each example records raw prompts/responses, dependency edges, selected audit points,
verdicts, malicious membership, work products, tokens and per-call usage. Gold BBH answers
enter only the final scoring function, never a worker or auditor prompt.

`work` is the initial execution, including attack outputs. `audit` includes all auditor
input/output tokens and re-audits. `rollback` contains the regenerated work products.
`total = work + audit + rollback`. Research scoring tokens are tracked separately as
`evaluation`, excluded from runtime total; the paper does not specify judge-token handling.
If a bill needs all tokens, add evaluation to total. Successful experimental calls are counted
again when restored from cache, so resumption does not reduce reported logical token cost.
Actual provider charges for transport retries/failed HTTP requests may differ from reported
usage. API responses must provide usage unless estimated usage is explicitly enabled.

Costs in `table5.csv` are arithmetic means per example, divided by 1,000. Scores are averaged
over examples/repetitions, with standard deviation of per-seed means. Missing/failed examples
are excluded from means and `complete` is false; inspect `failures/` before interpreting a
partial table. `smoke: true` marks configurations containing a fixture model. Fixture outputs
validate plumbing only. Real small/tiny model smoke outputs are also not Table 5 evidence.
Reference paper values live separately in `data/table5_reference.csv`; generated outputs
never copy them.

## Reproducibility

Prepared data has SHA-256 manifests and upstream revision metadata. Runs record the exact
configuration, selected example IDs, data/rubric hashes, implementation hash, Python/packages,
seeds, and all model calls. Config/data/source/runtime-package changes require a new output directory.
Cache files are atomically written. A filesystem lock prevents concurrent writers in one run.
Completed examples are skipped; failed/incomplete examples can restart from cached calls.
API output determinism depends on provider behavior; repeat seeds do not imply API determinism.
Pin HF `revision` to an immutable model commit before a full study, and specify exact API model
versions where the provider supports them. HF remote Python code is disabled.

## Sources

- Supplied `paper/BRA-audit.pdf`, Table 5, Algorithm 1, Eqs. 7–14.
- https://arxiv.org/html/2608.14668v1 (public HTML also lacks the technical supplement).
- https://github.com/suzgunmirac/BIG-Bench-Hard (official BBH data; MIT license retained).
- https://github.com/ulab-uiuc/MARBLE (official Research tasks and evaluator rubric;
  MIT license retained in vendor/MARBLE_LICENSE).
