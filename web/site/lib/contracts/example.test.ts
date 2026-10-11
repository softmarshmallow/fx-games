import { describe, expect, test } from "bun:test";
import catalogFixture from "./catalog.fixture.json";
import {
  EXAMPLE_REFUSAL,
  GAME_EXAMPLE_ENTRY_REFUSAL,
  parseGameExampleEntry,
  parseWorkflowExample,
} from "./example";
import exampleFixture from "./example.fixture.json";

function example(): Record<string, unknown> {
  return structuredClone(exampleFixture) as Record<string, unknown>;
}

function nodes(document: Record<string, unknown>): Record<string, Record<string, unknown>> {
  return document.nodes as Record<string, Record<string, unknown>>;
}

describe("parseWorkflowExample", () => {
  test("reads the hand-authored example into runtime shapes", () => {
    const parsed = parseWorkflowExample(example());
    expect(parsed.exampleId).toBe("slate-swatches");
    expect(parsed.madeBy).toEqual({ kind: "workflow", id: "swatch-sheet" });
    expect(parsed.sourceRuns[0].anchor).toBe("plan.json");
    expect(parsed.graphKind).toBe("fx-graph-v1");
    expect(Object.keys(parsed.nodes)).toEqual(["brief", "draw", "check", "contact-sheet"]);
    expect(parsed.nodes.draw.dependsOn).toEqual(["brief"]);
    expect(parsed.nodes.draw.maxAttempts).toBe(6);
    expect(parsed.nodes["contact-sheet"].origin).toBe("derived");
    expect(parsed.nodes.check.verdict).toEqual({
      passed: true,
      reason: "six swatches, none touching, all inside the grid",
    });
    expect(parsed.metrics.swatches).toBe(6);
    expect(parsed.tree[""]).toEqual({ kind: "dir", bytes: 1051266, files: 4, entries: 4 });
    expect(parsed.tree["sheet.png"].files).toBeNull();
    // Inputs and outputs stay as written: the page that shows them owns their meaning.
    expect(parsed.outputs.sheet.picture).toEqual(exampleFixture.outputs.sheet.picture);
  });

  test("a converted record without source files still reads", () => {
    const document = example();
    document.source_files = null;
    document.graph_kind = null;
    document.graph_sha256 = null;
    const parsed = parseWorkflowExample(document);
    expect(parsed.sourceFiles).toBeNull();
    expect(parsed.graphKind).toBeNull();
  });

  test.each([
    ["kind", "workflow-example-v2"],
    ["schema_version", 2],
  ])("refuses an unknown envelope (%s)", (field, value) => {
    expect(() => parseWorkflowExample({ ...example(), [field]: value })).toThrow(EXAMPLE_REFUSAL);
  });

  test("refuses a node keyed under another id or depending on a node it does not hold", () => {
    const renamed = example();
    nodes(renamed).draw.id = "paint";
    expect(() => parseWorkflowExample(renamed)).toThrow("nodes.draw.id must equal its key");

    const dangling = example();
    nodes(dangling).check.depends_on = ["paint"];
    expect(() => parseWorkflowExample(dangling)).toThrow("depends on an undeclared node paint");
  });

  test("refuses a malformed origin, digest or empty source list", () => {
    const origin = example();
    nodes(origin).draw.origin = "imported";
    expect(() => parseWorkflowExample(origin)).toThrow("nodes.draw.origin must be one of run, derived");

    const anchor = example();
    (anchor.source_runs as Record<string, unknown>[])[0].anchor_sha256 = "abc";
    expect(() => parseWorkflowExample(anchor)).toThrow("source_runs[0].anchor_sha256 must be a SHA-256 digest");

    expect(() => parseWorkflowExample({ ...example(), source_runs: [] })).toThrow(
      "source_runs must name at least one run",
    );
  });
});

describe("parseGameExampleEntry", () => {
  const entry = () =>
    structuredClone(catalogFixture.game_examples[0].entry) as Record<string, unknown>;

  test("reads what a game says about an example it made", () => {
    const parsed = parseGameExampleEntry(entry());
    expect(parsed.gameTitle).toBe("Example Game");
    expect(parsed.order).toBe(1);
    expect(parsed.steps[0].members).toEqual(["harbor-atlas"]);
    expect(parsed.currency).toBe("current");
  });

  test("refuses an unknown envelope, a workflow maker, and an unknown currency", () => {
    expect(() => parseGameExampleEntry({ ...entry(), schema_version: 2 })).toThrow(
      GAME_EXAMPLE_ENTRY_REFUSAL,
    );
    expect(() =>
      parseGameExampleEntry({ ...entry(), made_by: { kind: "workflow", id: "swatch-sheet" } }),
    ).toThrow("made_by.kind must be game");
    expect(() => parseGameExampleEntry({ ...entry(), currency: "stale" })).toThrow(
      "currency must be one of current, earlier_version",
    );
  });
});
