# Contributing

The current priority is the custom CPU and its C0-C7 gates in [cpu/architecture.md](cpu/architecture.md). Run `bash sim/cpu/run.sh` for CPU RTL or simulator changes. Keep the existing D0-D9/M0-M6 accelerator research as a separate workstream.

## Local workflow

Use Python 3.11+ and run from the repository root:

```sh
python -B scripts/check_repo.py
```

Run `bash sim/starter/run.sh` with Icarus when changing the historical CPU starter. For new numerical/RTL work, include the relevant independent reference comparisons, fault tests and tool versions. A documentation-only change does not require a hardware run. The repository runner uses a temporary copy so normal verification does not rewrite reviewed evidence.

## Evidence and sources

- Separate assumptions, calculated bounds, synthetic checks, native-model results and physical measurements. Give units, exact workload, source revision and tool versions.
- Cite primary documentation. Date prices and availability. Preserve attribution and license notices for imported code, RTL and specifications.
- Root plans/helpers are maintained; `llm-accelerator/planning-evidence/` contains historical snapshots. Update a snapshot only as an intentional, documented evidence revision.
- `llm-accelerator/plan/reference-source-lock.json` and `llm-accelerator/plan/qualification-fixtures.json` are byte-locked. Do not reformat them or replace expected digests to make a failure disappear. An intentional update needs a version/reason, immutable provenance, independent review and corresponding checker anchors. Preserve previous failures and review identities.
- Changes to arithmetic order, constants, layouts, ABI or fidelity bounds require an explicit versioned decision. Calibration can tighten existing fidelity ceilings; it cannot silently relax them.
- The critic's reviewed hashes identify a historical review. A later design change requires new evidence before inheriting that review's score.

## Pull requests

Describe the problem, resulting behavior and validation. A pull request that calls the CPU good, performant or fast needs a review record under the [CPU review rubric](cpu/review-rubric.md). Include exact reproduction commands and relevant output summaries. For a performance or resource claim, include workload, width/clock, memory topology, effective service rates and whether the result is measured. Explain any unrun gate and the next required evidence.

Keep weights, full waveforms, tool installation trees, credentials and personal machine records out of commits. Preserve compact reproducibility fixtures and meaningful checked-in evidence. Git ignores are conveniences; inspect the actual diff before committing.

Original contributions are made under the repository's MIT license. Imported work retains its upstream terms and must be listed in `THIRD_PARTY_NOTICES.md` with appropriate license text. Do not remove upstream headers or label third-party snapshots as original MIT code.

## Collaboration

Be direct, respectful and specific. Critique the design and evidence, explain disagreements with reproducible examples, and avoid personal attacks or harassment.
