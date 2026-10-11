"use client";

// The live kit of a <UiKit>. The block renders this root with its markup inside; the player in
// lib/players/ui-kit.ts mounts on it after hydration and is torn down with it.

import type { ReactElement } from "react";
import { mount } from "@/lib/players/ui-kit";
import { type RootProps, usePlayer } from "./use-player";

export default function UiKitPlayer({ className, style, children }: RootProps): ReactElement {
  const ref = usePlayer<HTMLDivElement, void>(mount);
  return (
    <div ref={ref} data-ui-kit="" className={className} style={style}>
      {children}
    </div>
  );
}
