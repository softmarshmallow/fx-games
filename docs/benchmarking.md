# Benchmarking and research

Benchmarking belongs to the authoritative Python headless package, not the
optional web preview. Every workflow and game build runs on Grida FX, whose public entry
point is:

```sh
uv run python -m grida.fx --help
```

Use the CLI help as the source of truth for currently implemented pipeline and
benchmark arguments. Do not document an aspirational subcommand as shipped.

The offline evidence a change is expected to produce is the plan, provider-free, and
the builder's own tests, which run a whole build on stand-in calls:

```sh
(cd godot/games/bellweather && uv run python -m grida.fx plan pipeline/workflow.py:build --arg package=inputs/default)
uv run pytest tests/unit/games/sideview_platformer/test_workflow.py
```

There is no separate benchmark subcommand. A suite whose only assertion was that
the registry still listed itself measured nothing the test suite did not already
prove, and it is gone rather than kept as a shell to hang future suites on.

## Evidence bundle

Every benchmark case preserves:

- a neutral, rights-safe case identifier and input manifest;
- exact component/pipeline revision;
- provider/model/endpoint identifiers and non-secret parameters;
- hashes of every reference input;
- raw provider metadata where policy permits;
- normalized artifact and provenance sidecar;
- attempt count, latency per attempt, and total wall time;
- deterministic validation output; and
- an explicit pass/fail reason.

Secrets, authorization headers, signed URLs, and populated env files never
belong in an evidence bundle.

## Evaluation layers

1. **Contract tests and stand-in runs** exercise schemas, path isolation, media
   parsing, provenance and whole workflows without paid calls: a stand-in
   (`grida.fx.run(..., stand_in=...)`) answers each paid call. Retries and provider
   envelopes belong to FX and are tested by FX's own gates.
2. **Provider smoke runs** are the smallest useful live run (`--live` with a small
   `--max-usd`) and prove the live envelope. They are opt-in, and the FX run record
   keeps their cost, usage and attempts.
3. **Component benchmarks** compare one operation against its declared media
   contract without a game runtime.
4. **Pipeline benchmarks** validate cross-asset consistency and resumability.
5. **Preview verification** checks only that an adapter can consume a complete
   manifest; it is not the quality oracle for the core pipeline.

Any visual output is independently reviewed by a verifier that sees the spec
and rendered output, not the generation prompt. Use bounded retries and retain
the verifier's structured verdict. Audio checks should combine deterministic
media inspection with a separately recorded human/agent listening verdict.

## Initial release gates

- Image: live request, reference input, returned media validation, deterministic
  normalization, and provenance all pass.
- Background removal: alpha-bearing output and optional mask behavior pass on
  representative edge detail.
- Music: live Lyria response envelope is captured and decoded; container,
  duration, channels, and sample rate come from the returned file rather than
  documentation assumptions.
- Secret scan and history scan find no credential or removed third-party media.
- A repeated run of the same plan takes every result from the store and bills nothing.
