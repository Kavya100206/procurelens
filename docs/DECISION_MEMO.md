# Architectural Decision Memo: Shipping Architecture A

## 1. Decision
Ship **Architecture A** (single agent + deterministic policy engine).

## 2. Evidence
- **Benchmark Scale**: 20 cases, one run each, `openai/gpt-oss-20b`, identical fixtures for both architectures.
- **Approvals & Flags**: Approvals (20/20, 100.0%) and required flags (20/20, 100.0%) are identical, because both architectures delegate thresholds, specialist reviews, and precedence to code.
- **Final Recommendation Accuracy**: Architecture A scored 19/20 (95.0%) and Architecture B scored 20/20 (100.0%).
- **Latency & Call Overhead**: Architecture B costs about 2.6x the net latency (15.1s vs 5.8s) and 28% more LLM calls (4.85 vs 3.8 per request).

## 3. Why Architecture A
The architecture only matters for three LLM judgments (gap justification, injection suspicion, ambiguity). Architecture B's whole advantage is one case, `EVAL-05`, where A twice judged a justified gap as unjustified and redirected to the existing tool. That result was stable across two runs but is one case on one model, so it is suggestive, not statistically meaningful.

Architecture A's failure still reaches a human reviewer (`human_review_required` is always true) with the correct approvals listed. Paying 2.6x latency and more calls for one case is not justified yet.

## 4. Safeguards That Make Architecture A Acceptable
- Code overrides the model on recommendation, approvals, and flags.
- Evidence is built deterministically from tool results.
- Injection suspicion can only add flags; it cannot bypass policy.
- Invalid output falls back to `escalate`.
- Paired injection cases (`EVAL-01` vs `EVAL-02`, `EVAL-12` vs `EVAL-13`) and the paraphrased-injection case (`EVAL-20`) passed on both architectures.

## 5. Known Weakness and Next Step
Architecture A's `gap_justified` judgment is weaker. Next step is a tighter gap prompt (require a quoted justification), validated on new cases, not just `EVAL-05`, to avoid tuning to the test set.

## 6. When I Would Switch to Architecture B
Switch to Architecture B if a larger case set shows B consistently better on LLM-judgment cases, or if keeping raw requester text away from the final decision becomes a hard security requirement. Architecture B's isolation is a structural advantage I did not measure separately.

## 7. Limitations
$N = 20$, single runs, one small model (`openai/gpt-oss-20b`), raw-output-before-policy accuracy is directional only, and cases were written by the same team that built the system.
