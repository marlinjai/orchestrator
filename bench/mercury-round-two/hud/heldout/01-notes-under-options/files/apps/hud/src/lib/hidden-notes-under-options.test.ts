import { describe, expect, it } from "vitest";

import type { VaultTreeNode } from "@agentic-os/shared";

import { notesUnder as notesUnderRaw } from "./vault-export";

type Options = { maxDepth?: number; skipHidden?: boolean };
const notesUnder = notesUnderRaw as unknown as (nodes: readonly VaultTreeNode[], options?: Options) => string[];

const file = (path: string): VaultTreeNode => ({ name: path.split("/").pop()!, path, type: "file" });
const dir = (path: string, children: VaultTreeNode[]): VaultTreeNode => ({
  name: path.split("/").pop()!,
  path,
  type: "dir",
  children,
});

const tree: VaultTreeNode[] = [
  file("top.md"),
  file("data.csv"),
  dir("a", [
    file("a/one.md"),
    dir("a/b", [file("a/b/two.md"), dir("a/b/c", [file("a/b/c/three.md")])]),
    file("a/zed.md"),
  ]),
  dir(".obsidian", [file(".obsidian/config.md")]),
  dir("_archive", [file("_archive/old.md"), dir("_archive/deep", [file("_archive/deep/older.md")])]),
  file("_draft.md"),
  file(".hidden.md"),
  dir("z", [file("z/_private.md"), file("z/last.md"), dir("z/.cache", [file("z/.cache/x.md")])]),
];

const ALL = [
  "top.md",
  "a/one.md",
  "a/b/two.md",
  "a/b/c/three.md",
  "a/zed.md",
  ".obsidian/config.md",
  "_archive/old.md",
  "_archive/deep/older.md",
  "_draft.md",
  ".hidden.md",
  "z/_private.md",
  "z/last.md",
  "z/.cache/x.md",
];

describe("notesUnder options", () => {
  it("behaves as before without options or with an empty object", () => {
    expect(notesUnder(tree)).toEqual(ALL);
    expect(notesUnder(tree, {})).toEqual(ALL);
    expect(notesUnder(tree, { skipHidden: false })).toEqual(ALL);
    expect(notesUnder(tree, { maxDepth: undefined })).toEqual(ALL);
  });

  it("maxDepth 0 lists only the direct notes", () => {
    expect(notesUnder(tree, { maxDepth: 0 })).toEqual(["top.md", "_draft.md", ".hidden.md"]);
  });

  it("maxDepth 1 and 2 enter that many levels", () => {
    expect(notesUnder(tree, { maxDepth: 1 })).toEqual([
      "top.md",
      "a/one.md",
      "a/zed.md",
      ".obsidian/config.md",
      "_archive/old.md",
      "_draft.md",
      ".hidden.md",
      "z/_private.md",
      "z/last.md",
    ]);
    expect(notesUnder(tree, { maxDepth: 2 })).toEqual(ALL.filter((p) => p !== "a/b/c/three.md"));
    expect(notesUnder(tree, { maxDepth: 3 })).toEqual(ALL);
    expect(notesUnder(tree, { maxDepth: 50 })).toEqual(ALL);
  });

  it("skipHidden drops hidden files and whole hidden directories", () => {
    expect(notesUnder(tree, { skipHidden: true })).toEqual([
      "top.md",
      "a/one.md",
      "a/b/two.md",
      "a/b/c/three.md",
      "a/zed.md",
      "z/last.md",
    ]);
  });

  it("combines both options", () => {
    expect(notesUnder(tree, { maxDepth: 1, skipHidden: true })).toEqual(["top.md", "a/one.md", "a/zed.md", "z/last.md"]);
    expect(notesUnder(tree, { maxDepth: 0, skipHidden: true })).toEqual(["top.md"]);
  });

  it("rejects a maxDepth that is not a non-negative integer, even for an empty list", () => {
    for (const bad of [-1, 1.5, Number.NaN, Number.POSITIVE_INFINITY]) {
      expect(() => notesUnder(tree, { maxDepth: bad })).toThrow(RangeError);
      expect(() => notesUnder([], { maxDepth: bad })).toThrow(RangeError);
    }
  });

  it("handles a directory without children and an empty list", () => {
    expect(notesUnder([{ name: "empty", path: "empty", type: "dir" }], { maxDepth: 3, skipHidden: true })).toEqual([]);
    expect(notesUnder([], { maxDepth: 0 })).toEqual([]);
  });
});
