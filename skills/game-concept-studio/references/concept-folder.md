# The concept folder

## Location

Any folder of the user's. One concept per folder, named by its id in lowercase hyphen-case. Every
candidate image of that concept lives in the same folder.

## Layout

```text
<concept-id>/
  concept.md                          the concept, in prose, for people
  fx.yaml                             the FX project: its ceiling and routes
  workflows/concept-image.yaml        the one-step drawing workflow
  workflows/concept-image.takes.yaml  written by FX after a reroll, if any
  inputs/candidate-NN.yaml            one per candidate: its prompt and size
  images/candidate-NN.png             each candidate, delivered by FX
  images/cover.png                    a byte copy of the chosen candidate
  runs/candidate-NN/                  FX's record of each run: events.jsonl, plan.json,
                                      outputs/image.png, files/
  .fx/cache/                          FX's cache, kept by content
  .gitignore                          .env and .fx/
  .env                                the user's keys, optional; the agent never opens it
```

## `concept.md`

Flexible prose, not a schema. It makes these understandable when they matter to the idea:

- the title and a one-sentence pitch;
- the player fantasy and the core play rhythm, at concept level;
- world, tone, characters or factions;
- visual direction in observable terms;
- cover direction, and why each candidate and route was chosen;
- assumptions and open questions.

Two parts are fixed:

- **Images:** one line per candidate, naming its route, size, run folder and verdict.
- **Cover:** the chosen candidate, its run folder, the route, the size, the SHA-256 of
  `images/cover.png`, and why it was chosen.

```markdown
## Images

- candidate-01: openai/gpt-image-2.5-sunburst@openrouter, 2560x1440, runs/candidate-01;
  rejected: stray lettering on the hull.
- candidate-02: openai/gpt-image-2.5-sunburst@openrouter, 2560x1440, runs/candidate-02; selected.

## Cover

- Candidate: candidate-02
- Run: runs/candidate-02
- Route: openai/gpt-image-2.5-sunburst@openrouter
- Size: 2560x1440
- SHA-256: <64 hexadecimal characters>
- Why: <one line>
```

Never add game configuration, manifests, maps, gameplay contracts, implementation tasks, code, or
an engine asset hierarchy. The concept may discuss mechanics; it never encodes them.

## Records

- The inputs files are the prompts.
- Each run folder is FX's record of one candidate: its inputs, route, cost, digests and attempts.
  `grida-fx inspect <run>` summarizes it, and `--verify` re-checks its files.
- The PNGs in `images/` are copies FX delivered from that record, and `cmp` proves it.
- Don't edit files inside `runs/`: they are hard links into the cache. Deleting a run folder is safe
  for the cache but loses that candidate's record, so keep at least the selected run.
- The cover is byte-identical to one reviewed candidate. A cropped, resized or retouched cover is a
  new image and needs a review of its own.

## Version control

- Ignore `.env` and `.fx/`.
- `runs/` is the record. If the folder is versioned, keep at least the selected run in it.

## Publishing

Authorization to draft never implies publication. Publishing a cover, or handing it to another
tool as an input, needs the user's explicit request, a review of the image by someone other than
whoever made it, and a rights basis for every reference picture it was drawn from.
