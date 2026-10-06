// Server-side helpers for finding and addressing runs under the configured run roots.
//
// The shell is a consumer: it locates and validates paths, and never generates.
// `scripts/view.py` passes the roots in STAGE_GEN_RUN_ROOTS; without it the viewer reads
// out/ of its checkout. Runs are found the way `stage_gen.runview.discover` finds them, by
// the documents they publish. Every tag is checked segment by segment against the
// producer's one-safe-segment contract, and every artifact path is confined to its own
// run directory before a byte is read.

import { createHash } from "node:crypto";
import { promises as fs, readFileSync, realpathSync } from "node:fs";
import path from "node:path";
import { ARTIFACT_SEGMENT_PATTERN } from "@stage-gen/ui/contracts/artifact-preview";
import { type RunRef, TAG_SEPARATOR, tagFor } from "./run-ref";

const PROJECT_NAME = "stage-gen";

// The `name` of the `[project]` table, read without a TOML parser: the table runs from
// its header to the next header, and the name is one quoted string on its own line.
function projectName(pyproject: string): string | null {
  const table = /^\[project\][ \t]*$([\s\S]*?)(?=^\[|(?![\s\S]))/m.exec(pyproject);
  const name = table && /^name[ \t]*=[ \t]*["']([^"'\n]+)["'][ \t]*$/m.exec(table[1]);
  return name ? name[1] : null;
}

function readOrNull(file: string): string | null {
  try {
    return readFileSync(file, "utf8");
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ENOENT" || code === "ENOTDIR" || code === "EISDIR") return null;
    throw error;
  }
}

/**
 * The checkout the viewer belongs to. `STAGE_GEN_REPO_ROOT` wins when it is set;
 * otherwise the first directory at or above `start` whose pyproject.toml names the
 * `stage-gen` project. The working directory is never assumed to sit one level below
 * it: the viewer is started from web/viewer, its tests from web/.
 */
export function findRepoRoot(
  start: string = process.cwd(),
  env: Readonly<Record<string, string | undefined>> = process.env,
): string {
  const configured = env.STAGE_GEN_REPO_ROOT?.trim();
  if (configured) return path.resolve(configured);
  let directory = path.resolve(start);
  for (;;) {
    const pyproject = readOrNull(path.join(directory, "pyproject.toml"));
    if (pyproject !== null && projectName(pyproject) === PROJECT_NAME) return directory;
    const parent = path.dirname(directory);
    if (parent === directory) {
      throw new Error(
        `no ${PROJECT_NAME} checkout at or above ${path.resolve(start)}; ` +
          "set STAGE_GEN_REPO_ROOT",
      );
    }
    directory = parent;
  }
}

// ------------------------------------------------------------------ roots

/** One folder of runs, as `scripts/view.py DIR` named it. */
export interface RunRoot {
  /** The URL key: the folder name and the first six hex digits of its real path's digest. */
  readonly key: string;
  /** The real path, so confinement checks compare like with like. */
  readonly dir: string;
  /** The folder name, for readers. */
  readonly label: string;
}

function realOrResolved(target: string): string {
  try {
    return realpathSync(target);
  } catch {
    return path.resolve(target);
  }
}

export function rootKey(dir: string): string {
  const slug =
    path
      .basename(dir)
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "") || "root";
  const digest = createHash("sha256").update(realOrResolved(dir)).digest("hex");
  return `${slug}-${digest.slice(0, 6)}`;
}

const rootsCache = new Map<string, readonly RunRoot[]>();

/**
 * The run roots, in the order they were given: STAGE_GEN_RUN_ROOTS (a path list in the
 * platform's delimiter, as `scripts/view.py` sets it), or out/ of the checkout.
 */
export function runRoots(): readonly RunRoot[] {
  const configured = process.env.STAGE_GEN_RUN_ROOTS?.trim() ?? "";
  const cacheKey = `${process.cwd()}\0${process.env.STAGE_GEN_REPO_ROOT ?? ""}\0${configured}`;
  const cached = rootsCache.get(cacheKey);
  if (cached) return cached;
  const given = configured
    ? configured.split(path.delimiter).filter((entry) => entry.trim())
    : [path.join(findRepoRoot(), "out")];
  const roots: RunRoot[] = [];
  for (const entry of given) {
    const dir = realOrResolved(path.resolve(entry.trim()));
    if (roots.some((root) => root.dir === dir)) continue;
    roots.push(Object.freeze({ key: rootKey(dir), dir, label: path.basename(dir) }));
  }
  rootsCache.set(cacheKey, Object.freeze(roots));
  return rootsCache.get(cacheKey) ?? roots;
}

export function rootFor(key: string): RunRoot | null {
  return runRoots().find((root) => root.key === key) ?? null;
}

/** Where `scripts/view.py` keeps the views it derives, or null when it is not running. */
export function viewCacheDir(): string | null {
  const configured = process.env.STAGE_GEN_VIEW_CACHE?.trim();
  return configured ? path.resolve(configured) : null;
}

/** The catalog `scripts/view.py` exported, or null when it is not running. */
export function catalogPath(): string | null {
  const configured = process.env.STAGE_GEN_CATALOG?.trim();
  return configured ? path.resolve(configured) : null;
}

// ------------------------------------------------------------------ names

// Match the current producer's one-safe-segment contract exactly. Generated prompt tags happen
// to be lower-case, but explicit producer tags may also contain upper-case letters, `_`, or `.`.
const SEGMENT_MAXIMUM_LENGTH = 128;
const SEGMENT_PATTERN = new RegExp(
  `^[A-Za-z0-9][A-Za-z0-9._-]{0,${SEGMENT_MAXIMUM_LENGTH - 1}}$`,
);
/** How many folders below its root a run may sit, as stage_gen.runview.SEARCH_DEPTH. */
export const SEARCH_DEPTH = 4;

function isAlreadyDecoded(value: string): boolean {
  try {
    return decodeURIComponent(value) === value;
  } catch {
    return false;
  }
}

function isSafeSegment(segment: string): boolean {
  return segment !== "." && segment !== ".." && SEGMENT_PATTERN.test(segment);
}

/** A tag names one run: one to four safe segments joined by `~`. */
export function isSafeRunTag(tag: string): boolean {
  if (!isAlreadyDecoded(tag)) return false;
  const segments = tag.split(TAG_SEPARATOR);
  return segments.length <= SEARCH_DEPTH && segments.every(isSafeSegment);
}

export function assertSafeRunTag(tag: string): void {
  if (!isSafeRunTag(tag)) {
    throw new Error("invalid run tag");
  }
}

export function runDirFor(run: RunRef): string {
  assertSafeRunTag(run.tag);
  const root = rootFor(run.root);
  if (root === null) throw new Error("unknown run root");
  const runDir = path.resolve(root.dir, ...run.tag.split(TAG_SEPARATOR));
  if (!runDir.startsWith(`${root.dir}${path.sep}`)) {
    throw new Error("run tag escapes its root");
  }
  return runDir;
}

function artifactSegments(asset: string): string[] {
  const segments = asset.split("/");
  if (
    !isAlreadyDecoded(asset) ||
    segments.length === 0 ||
    segments.some(
      (segment) =>
        segment === "." ||
        segment === ".." ||
        !ARTIFACT_SEGMENT_PATTERN.test(segment),
    )
  ) {
    throw new Error("invalid artifact path");
  }
  return segments;
}

export function artifactPathFor(run: RunRef, asset: string): string {
  const segments = artifactSegments(asset);
  const runDir = runDirFor(run);
  const target = path.resolve(runDir, ...segments);
  if (!target.startsWith(`${runDir}${path.sep}`)) {
    throw new Error("artifact path escapes run directory");
  }
  return target;
}

/** The run's folder in the view cache, or null when the viewer was started without one. */
export function viewCacheFolderFor(run: RunRef): string | null {
  const cache = viewCacheDir();
  return cache === null ? null : path.join(cache, viewKey(runDirFor(run)));
}

/**
 * Where the view cache keeps a file of a run's views (`views/<sha>.html`,
 * `views/files/<digest><suffix>`): `<view cache>/<view key>/<relative>`. Null when the
 * viewer was started without a view cache.
 */
export function viewCachePathFor(run: RunRef, relative: string): string | null {
  const segments = artifactSegments(relative);
  const folder = viewCacheFolderFor(run);
  if (folder === null) return null;
  const target = path.resolve(folder, ...segments);
  if (!target.startsWith(`${folder}${path.sep}`)) {
    throw new Error("view path escapes the run's view cache");
  }
  return target;
}

async function lstatOrNull(target: string): Promise<Awaited<ReturnType<typeof fs.lstat>> | null> {
  try {
    return await fs.lstat(target);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return null;
    throw error;
  }
}

async function assertRealDirectory(target: string, label: string): Promise<boolean> {
  const stat = await lstatOrNull(target);
  if (!stat) return false;
  if (!stat.isDirectory() || stat.isSymbolicLink()) {
    throw new Error(`${label} must be a real directory`);
  }
  if ((await fs.realpath(target)) !== path.resolve(target)) {
    throw new Error(`${label} must not traverse a symlink`);
  }
  return true;
}

export async function isRealRunDirectory(run: RunRef): Promise<boolean> {
  const root = rootFor(run.root);
  if (root === null || !(await assertRealDirectory(root.dir, "run root"))) return false;
  return assertRealDirectory(runDirFor(run), "run directory");
}

/** The cache folder name of a run, as stage_gen.runview.view_key: its real path, hashed. */
export function viewKey(runDir: string): string {
  return createHash("sha256").update(realOrResolved(runDir)).digest("hex").slice(0, 16);
}

// ------------------------------------------------------------------ discovery

/** A folder holding one of these is a run. */
export const RUN_DOCUMENTS = [
  "execution-view.json",
  "manifest.json",
  "bundle.json",
  "case.json",
] as const;

/** An FX run keeps its plan beside its record from the moment it starts. */
export const FX_RUN_DOCUMENTS = ["plan.json", "events.jsonl"] as const;
/** The plan kind of an FX run; a plan and record of another kind are a foreign run's. */
export const FX_GRAPH_KIND = "fx-graph-v1";

/** The example store sits at the top of a root and holds exports, not runs. */
const EXAMPLE_STORE = "examples";

export interface FoundRun {
  readonly run: RunRef;
  readonly root: RunRoot;
  /** The root-relative path, `/`-separated. */
  readonly relative: string;
  readonly dir: string;
}

async function planKind(dir: string): Promise<unknown> {
  try {
    const plan = JSON.parse(await fs.readFile(path.join(dir, "plan.json"), "utf8")) as unknown;
    return plan !== null && typeof plan === "object" ? (plan as { kind?: unknown }).kind : null;
  } catch {
    return null;
  }
}

/** "run" for a run, "foreign" for a plan and record of another kind, null for neither. */
async function runListing(dir: string, names: ReadonlySet<string>): Promise<"run" | "foreign" | null> {
  if (FX_RUN_DOCUMENTS.every((name) => names.has(name)))
    return (await planKind(dir)) === FX_GRAPH_KIND ? "run" : "foreign";
  return RUN_DOCUMENTS.some((name) => names.has(name)) ? "run" : null;
}

/**
 * Every run under each root, at most SEARCH_DEPTH folders down, in root then path order.
 * A run's own folders are not searched again, so a sub-run is part of its run. A plan and
 * record of another kind than FX's are a foreign run: neither listed nor searched. Hidden
 * folders, node_modules, the example store at the top of a root, symlinked folders and
 * folders whose names cannot be a tag segment are skipped.
 */
export async function discoverRuns(roots: readonly RunRoot[] = runRoots()): Promise<FoundRun[]> {
  const found: FoundRun[] = [];
  for (const root of roots) {
    const runs: FoundRun[] = [];
    const visit = async (dir: string, segments: readonly string[]): Promise<void> => {
      let entries;
      try {
        entries = await fs.readdir(dir, { withFileTypes: true });
      } catch {
        return;
      }
      const files = new Set(entries.filter((entry) => !entry.isDirectory()).map((entry) => entry.name));
      const listing = segments.length > 0 ? await runListing(dir, files) : null;
      if (listing === "run") {
        const relative = segments.join("/");
        runs.push({ run: { root: root.key, tag: tagFor(relative) }, root, relative, dir });
      }
      if (listing !== null) return;
      if (segments.length === SEARCH_DEPTH) return;
      await Promise.all(
        entries
          .filter(
            (entry) =>
              entry.isDirectory() &&
              !entry.isSymbolicLink() &&
              entry.name !== "node_modules" &&
              !(segments.length === 0 && entry.name === EXAMPLE_STORE) &&
              isSafeSegment(entry.name),
          )
          .map((entry) => visit(path.join(dir, entry.name), [...segments, entry.name])),
      );
    };
    await visit(root.dir, []);
    runs.sort((a, b) => (a.relative < b.relative ? -1 : a.relative > b.relative ? 1 : 0));
    found.push(...runs);
  }
  return found;
}
