import sys
root = sys.argv[1]
p = f"{root}/apps/hud/src/lib/vault-export.ts"
s = open(p).read()
start = s.index("/** Every note beneath a folder, in tree order. */")
end = s.index("export class ExportLimitError")
s = s[:start] + '''/** Every note beneath a folder, in tree order. */
export function notesUnder(
  nodes: readonly VaultTreeNode[],
  options: { maxDepth?: number; skipHidden?: boolean } = {},
): string[] {
  const { maxDepth, skipHidden = false } = options;
  if (maxDepth !== undefined && (!Number.isInteger(maxDepth) || maxDepth < 0)) {
    throw new RangeError("maxDepth must be a non-negative integer");
  }
  const walk = (list: readonly VaultTreeNode[], depth: number): string[] => {
    const out: string[] = [];
    for (const node of list) {
      if (skipHidden && /^[._]/.test(node.name)) continue;
      if (node.type === "dir") {
        if (maxDepth === undefined || depth < maxDepth) out.push(...walk(node.children ?? [], depth + 1));
      } else if (isNoteName(node.name)) out.push(node.path);
    }
    return out;
  };
  return walk(nodes, 0);
}

''' + s[end:]
open(p, "w").write(s)
