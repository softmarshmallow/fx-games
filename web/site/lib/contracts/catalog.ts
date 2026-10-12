// Parser for `fx-games-catalog-v1`, the catalog.json `scripts/catalog.py` writes
// from the installed workflows and the example store. The site builds from it. Wire
// fields are lower_snake_case; this adapter is the one place they become camelCase
// runtime shapes.
//
// The catalog is derived and never committed, so versioning is hard-drop: an unknown
// envelope is refused with a re-export instruction, never migrated.

import {
  parseCurrency,
  parseExampleStep,
  parseGameExampleEntry,
  parseMadeBy,
  parseWorkflowExample,
  type Currency,
  type ExampleTool,
  type GameExampleEntry,
  type GameExampleStep,
  type MadeBy,
  type WorkflowExample,
} from "./example";
import {
  anyText,
  boolean,
  digest,
  envelope,
  integer,
  integerOrNull,
  list,
  object,
  oneOf,
  record,
  text,
  textOrNull,
} from "./wire";

export const CATALOG_KIND = "fx-games-catalog-v1";
export const CATALOG_SCHEMA_VERSION = 1;
export const CATALOG_REFUSAL =
  `unsupported catalog: expected ${CATALOG_KIND} schema_version ${CATALOG_SCHEMA_VERSION}; ` +
  "re-export it (uv run python scripts/catalog.py --out DIR)";

export interface OutputNote {
  readonly artifactRef: string;
  readonly description: string;
}

export interface TryIt {
  /** The committed input folder the commands read. */
  readonly input: string;
  readonly commands: readonly string[];
}

/** One pinned example as workflow.toml declares it. */
export interface ExampleEntry {
  readonly id: string;
  readonly title: string;
  /** Set when the example's card carries its own title and promise. */
  readonly promise: string | null;
  readonly status: "draft" | "approved";
  readonly exampleSha256: string;
  readonly figuresSha256: string;
  /** "store", or "library:<path>" for one built from tracked library files. */
  readonly source: string;
  readonly cover: boolean;
  readonly order: number | null;
  /** The closing line of the example's page; null for the default one. */
  readonly footer: string | null;
  /** Titles for node ids of the example (an example made with an earlier version). */
  readonly labels: Readonly<Record<string, string>>;
  /** The example's own steps, by node id, when the workflow's no longer describe its run. */
  readonly steps: readonly GameExampleStep[];
}

/** workflow.toml (`fx-games-workflow-v1`): what the code cannot know. */
export interface WorkflowManifest {
  readonly id: string;
  readonly title: string;
  readonly promise: string;
  readonly summary: string;
  readonly related: readonly string[];
  readonly tools: readonly ExampleTool[];
  /** Titles for node types whose own title sits in a frozen file. */
  readonly labels: Readonly<Record<string, string>>;
  readonly outputs: readonly OutputNote[];
  readonly tryIt: TryIt | null;
  readonly examples: readonly ExampleEntry[];
}

export interface StepMember {
  readonly typeId: string;
  readonly title: string;
  readonly operation: string | null;
}

export interface CatalogStep {
  readonly label: string;
  readonly note: string;
  readonly members: readonly StepMember[];
}

export interface CatalogExample extends ExampleEntry {
  /** Whether the example was found in the store or built from the library. */
  readonly present: boolean;
  readonly currency: Currency | null;
  readonly example: WorkflowExample | null;
}

export interface CatalogWorkflow {
  readonly id: string;
  readonly folder: string;
  /** Repository-relative source folder; null outside a checkout. */
  readonly sourceFolder: string | null;
  readonly manifest: WorkflowManifest;
  readonly steps: readonly CatalogStep[];
  readonly examples: readonly CatalogExample[];
}

export interface CatalogGameExample {
  /** The game that made it; the store folder it was exported to. */
  readonly owner: string;
  readonly id: string;
  /** Absent until the game exports the example's entry. */
  readonly entry: GameExampleEntry | null;
  readonly currency: Currency | null;
  readonly page: string | null;
  readonly exampleSha256: string;
  readonly problems: readonly string[];
  readonly example: WorkflowExample;
}

/** One landing card, in the owner's declared order. */
export interface LandingCard {
  readonly order: number;
  readonly title: string;
  readonly promise: string;
  readonly madeBy: MadeBy;
  /** The game's title for an example a game made; null for a workflow's. */
  readonly madeInside: string | null;
  /** The workflow whose example it shows; null for an example a game made. */
  readonly workflow: string | null;
  readonly example: string;
  readonly present: boolean;
}

export interface Catalog {
  readonly workflows: readonly CatalogWorkflow[];
  readonly gameExamples: readonly CatalogGameExample[];
  readonly cards: readonly LandingCard[];
  readonly modelNames: Readonly<Record<string, string>>;
  readonly providerNames: Readonly<Record<string, string>>;
}

function texts(value: unknown, label: string): readonly string[] {
  return list(value, label, text);
}

function exampleEntry(fields: Record<string, unknown>, label: string): ExampleEntry {
  return {
    id: text(fields.id, `${label}.id`),
    title: text(fields.title, `${label}.title`),
    promise: textOrNull(fields.promise, `${label}.promise`),
    status: oneOf(fields.status, `${label}.status`, ["draft", "approved"] as const),
    exampleSha256: digest(fields.example_sha256, `${label}.example_sha256`),
    figuresSha256: digest(fields.figures_sha256, `${label}.figures_sha256`),
    source: text(fields.source, `${label}.source`),
    cover: boolean(fields.cover ?? false, `${label}.cover`),
    order: integerOrNull(fields.order, `${label}.order`, 1),
    footer: textOrNull(fields.footer, `${label}.footer`),
    labels: record(fields.labels ?? {}, `${label}.labels`, text),
    steps: list(fields.steps ?? [], `${label}.steps`, parseExampleStep),
  };
}

function tool(value: unknown, label: string): ExampleTool {
  const fields = object(value, label);
  return Object.freeze({
    name: text(fields.name, `${label}.name`),
    role: text(fields.role, `${label}.role`),
  });
}

function manifest(value: unknown, label: string): WorkflowManifest {
  const fields = object(value, label);
  const tryIt = fields.try ?? null;
  return Object.freeze({
    id: text(fields.id, `${label}.id`),
    title: text(fields.title, `${label}.title`),
    promise: text(fields.promise, `${label}.promise`),
    summary: text(fields.summary, `${label}.summary`),
    related: texts(fields.related ?? [], `${label}.related`),
    tools: list(fields.tools ?? [], `${label}.tools`, tool),
    labels: record(fields.labels ?? {}, `${label}.labels`, text),
    outputs: list(fields.outputs ?? [], `${label}.outputs`, (entry, at) => {
      const output = object(entry, at);
      return Object.freeze({
        artifactRef: text(output.artifact_ref, `${at}.artifact_ref`),
        description: text(output.description, `${at}.description`),
      });
    }),
    tryIt:
      tryIt === null
        ? null
        : Object.freeze({
            input: text(object(tryIt, `${label}.try`).input, `${label}.try.input`),
            commands: texts((tryIt as Record<string, unknown>).commands, `${label}.try.commands`),
          }),
    examples: list(fields.examples ?? [], `${label}.examples`, (entry, at) =>
      Object.freeze(exampleEntry(object(entry, at), at)),
    ),
  });
}

function step(value: unknown, label: string): CatalogStep {
  const fields = object(value, label);
  return Object.freeze({
    label: text(fields.label, `${label}.label`),
    note: anyText(fields.note, `${label}.note`),
    members: list(fields.members, `${label}.members`, (entry, at) => {
      const member = object(entry, at);
      return Object.freeze({
        typeId: text(member.type_id, `${at}.type_id`),
        title: text(member.title, `${at}.title`),
        operation: textOrNull(member.operation, `${at}.operation`),
      });
    }),
  });
}

function catalogExample(value: unknown, label: string): CatalogExample {
  const fields = object(value, label);
  const present = boolean(fields.present, `${label}.present`);
  const document = fields.example ?? null;
  if (!present && document !== null) {
    throw new Error(`${label} is not present but carries a document`);
  }
  return Object.freeze({
    ...exampleEntry(fields, label),
    present,
    currency:
      fields.currency === null || fields.currency === undefined
        ? null
        : parseCurrency(fields.currency, `${label}.currency`),
    example: document === null ? null : parseWorkflowExample(document),
  });
}

function workflow(value: unknown, label: string): CatalogWorkflow {
  const fields = object(value, label);
  const id = text(fields.id, `${label}.id`);
  const parsed = manifest(fields.manifest, `${label}.manifest`);
  if (parsed.id !== id) throw new Error(`${label}.manifest.id must equal the workflow id`);
  return Object.freeze({
    id,
    folder: text(fields.folder, `${label}.folder`),
    sourceFolder: textOrNull(fields.source_folder, `${label}.source_folder`),
    manifest: parsed,
    steps: list(fields.steps, `${label}.steps`, step),
    examples: list(fields.examples, `${label}.examples`, catalogExample),
  });
}

function gameExample(value: unknown, label: string): CatalogGameExample {
  const fields = object(value, label);
  return Object.freeze({
    owner: text(fields.owner, `${label}.owner`),
    id: text(fields.id, `${label}.id`),
    entry: fields.entry === null || fields.entry === undefined ? null : parseGameExampleEntry(fields.entry),
    currency:
      fields.currency === null || fields.currency === undefined
        ? null
        : parseCurrency(fields.currency, `${label}.currency`),
    page: textOrNull(fields.page, `${label}.page`),
    exampleSha256: digest(fields.example_sha256, `${label}.example_sha256`),
    problems: list(fields.problems, `${label}.problems`, anyText),
    example: parseWorkflowExample(fields.example),
  });
}

function card(value: unknown, label: string): LandingCard {
  const fields = object(value, label);
  return Object.freeze({
    order: integer(fields.order, `${label}.order`, 1),
    title: text(fields.title, `${label}.title`),
    promise: text(fields.promise, `${label}.promise`),
    madeBy: parseMadeBy(fields.made_by, `${label}.made_by`),
    madeInside: textOrNull(fields.made_inside, `${label}.made_inside`),
    workflow: textOrNull(fields.workflow, `${label}.workflow`),
    example: text(fields.example, `${label}.example`),
    present: boolean(fields.present, `${label}.present`),
  });
}

export function parseCatalog(value: unknown): Catalog {
  const root = envelope(value, CATALOG_KIND, CATALOG_SCHEMA_VERSION, CATALOG_REFUSAL);
  const workflows = list(root.workflows, "workflows", workflow);
  const byId = new Map(workflows.map((entry) => [entry.id, entry]));
  if (byId.size !== workflows.length) throw new Error("workflows must have unique ids");
  const gameExamples = list(root.game_examples, "game_examples", gameExample);
  const cards = list(root.cards, "cards", card);
  cards.forEach((entry, index) => {
    if (index > 0 && cards[index - 1].order >= entry.order) {
      throw new Error("cards must be in strictly increasing order");
    }
    // A card points at something the catalog itself describes, so a page never links
    // to an example that is not there to show.
    if (entry.workflow !== null) {
      const examples = byId.get(entry.workflow)?.examples ?? [];
      if (!examples.some((example) => example.id === entry.example)) {
        throw new Error(`cards[${index}] names an unknown example ${entry.workflow}/${entry.example}`);
      }
    } else if (
      !gameExamples.some(
        (example) => example.owner === entry.madeBy.id && example.id === entry.example,
      )
    ) {
      throw new Error(`cards[${index}] names an unknown game example ${entry.madeBy.id}/${entry.example}`);
    }
  });
  return Object.freeze({
    workflows,
    gameExamples,
    cards,
    modelNames: record(root.model_names, "model_names", text),
    providerNames: record(root.provider_names, "provider_names", text),
  });
}
