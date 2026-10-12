// The docs' own checks, runnable without a staged catalog: a doc's relative links pointed at
// the site's pages.

import { describe, expect, test } from "bun:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { compileSource, docComponents } from "@/lib/mdx";

describe("doc links", () => {
  test("a relative link leads to the site's page, or keeps only its words", async () => {
    const source = "See the [site](site.md#pages), the [runs code](../src/fx_games/runs.py) and [uv](https://docs.astral.sh/uv/).";
    const resolve = (target: string) => (target.startsWith("site.md") ? `/docs/site/${target.slice("site.md".length)}` : null);
    const Content = await compileSource(source, "md", { from: "docs/getting-started.md", resolve });
    const html = renderToStaticMarkup(createElement(Content, { components: docComponents() }));
    expect(html).toContain('href="/docs/site/#pages"');
    expect(html).toContain("the runs code and");
    expect(html).not.toContain("runs.py");
    expect(html).toContain('href="https://docs.astral.sh/uv/"');
  });

  test("a relative image the site does not publish keeps its alt text", async () => {
    const source = "Before.\n\n![The loop node in the map branch](../../../../docs/diagrams/loop.svg)\n\nAfter.";
    const Content = await compileSource(source, "md", { from: "src/fx_games/workflows/x/contract.md", resolve: () => null });
    const html = renderToStaticMarkup(createElement(Content, { components: docComponents() }));
    expect(html).toContain("The loop node in the map branch");
    expect(html).not.toContain("<img");
    expect(html).not.toContain("loop.svg");
  });
});
