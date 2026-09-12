---
name: pipeline-throughput
description: Time stages 2-3 over a sample batch and stage 4 over a single image, then report whether the 800-image cap holds or should drop to 300
disable-model-invocation: true
---

# pipeline-throughput

`ARCHITECTURE.md` calls out one number that decides whether Retrace's 800-image cap is realistic: stages 2-3 are supposed to be cheap (~0ms and ~100-300ms/image), and stage 4 is expensive (~1-3s/image) but should only see ~5% of the library. This skill measures that, rather than assuming it.

## What to do when invoked

1. Find a sample batch of images to test against:
   - Prefer `tests/needles/docs/` if it exists (real, varied documents)
   - Otherwise ask the user for a sample folder, or use whatever staging directory Phase 3 of `plan.md` has produced
   - Aim for ~50 images; if fewer are available, use what exists and say so in the report
2. **Stages 2-3 timing:** run the metadata gate and OCR gate over the full sample batch, wall-clock timed. Report total time and ms/image average.
3. **Stage 4 timing:** run a single image (one that's expected to survive stages 2-3) end-to-end through the stage-4 extraction call (local Ollama Gemma vision call + strict JSON parse), wall-clock timed. Report seconds for that one call.
4. **Projection:** using the survival rate observed in step 2 (how many of the 50 survived to be extraction-eligible) as a proxy for the expected ~5% figure, project total pipeline time for:
   - 800 images at the observed survival rate
   - 300 images at the observed survival rate
5. **Recommendation:** state plainly whether 800 is realistic within the time budget, or whether the cap should drop to 300 — and why, citing the actual numbers.
6. If either stage 2-3 code or stage 4 code doesn't exist yet, say so and stop rather than fabricating numbers — this skill is meant to be run for real, ideally in Phase 1 of `plan.md` before the rest of the pipeline is built (a throwaway script is fine for that first run), and again once the real pipeline modules exist.

## Notes

- Record the result of each run (date, numbers, cap decision) as a short append to the "Phase 1 — Throughput spike" section of `plan.md` so the decision has a paper trail, not just a Slack message someone forgets.
- Don't average across runs or smooth outliers — report what actually happened this run. Serving latency (especially local Ollama on first load) can vary a lot; if the first stage-4 call looks like a cold start, note that and optionally re-time a second call.
