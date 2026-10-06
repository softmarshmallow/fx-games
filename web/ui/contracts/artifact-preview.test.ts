import { describe, expect, test } from "bun:test";
import { artifactReference, parseArtifactPreview, parseLegacyMotion } from "./artifact-preview";

describe("artifact preview adapters", () => {
  test.each(["../outside.png", "/outside.png", "https://example.com/a.png", "layers/%2e%2e/a.png", "layers\\outside.png"])("refuses unsafe artifact ref %s", (ref) => {
    expect(() => artifactReference(ref, "ref")).toThrow("portable run-local");
  });

  test.each(["files/draw#2/image.png", "files/entity__ada__.draw#1.3/image/_/hero.png", "files/étoile/x~0123456789abcdef.png"])(
    "reads FX's placed name %s",
    (ref) => {
      expect(artifactReference(ref, "ref")).toBe(ref);
    },
  );

  test.each(["files/draw/.0123456789abcdef.part", "files/./image.png", "files/../image.png", "files//image.png"])(
    "refuses a hidden, dot or empty segment in %s",
    (ref) => {
      expect(() => artifactReference(ref, "ref")).toThrow("portable run-local");
    },
  );

  test("any preview kind passes through to the ordinary display; malformed envelope fails", () => {
    expect(parseArtifactPreview({ kind: "user-owned-volume-v1", dimensions: [1, 2, 3] }, "preview")).toEqual({ kind: "user-owned-volume-v1" });
    expect(() => parseArtifactPreview({ canvas: {} }, "preview")).toThrow("kind");
    expect(() => parseArtifactPreview([], "preview")).toThrow("object");
  });

  test.each([0, 17, 64, 1.5])("historical strip contract still refuses %s frames", (count) => {
    expect(() => parseLegacyMotion({ frame_count: count }, "motion")).toThrow("frame_count");
  });

  test("retains legacy playback fields and refuses nonpositive speed", () => {
    expect(parseLegacyMotion({ frame_count: 4, mode: "once", canonical_frame_indices: [0, 2], frames_per_second: 8 }, "motion")).toEqual({ frameCount: 4, mode: "once", canonicalFrameIndices: [0, 2], framesPerSecond: 8 });
    expect(() => parseLegacyMotion({ frame_count: 4, frames_per_second: 0 }, "motion")).toThrow("positive");
  });
});
