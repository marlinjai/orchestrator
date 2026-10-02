import sys
root = sys.argv[1]
p = f"{root}/packages/contacts/src/csv-importer.ts"
s = open(p).read()
start = s.index("/**\n * Parse CSV content into rows of string values.")
end = s.index("/**\n * Detect CSV columns from parsed header row.")
s = s[:start] + r'''/**
 * Parse CSV content into rows of string values.
 */
export function parseCSV(content: string, delimiter = ','): string[][] {
  if (content.charCodeAt(0) === 0xfeff) content = content.slice(1);
  const rows: string[][] = [];
  let currentRow: string[] = [];
  // The field as parts: unquoted text is trimmed at the field's outer edges only.
  let parts: { text: string; quoted: boolean }[] = [];
  let inQuotes = false;
  let i = 0;

  const append = (ch: string, quoted: boolean) => {
    const last = parts[parts.length - 1];
    if (last && last.quoted === quoted) last.text += ch;
    else parts.push({ text: ch, quoted });
  };
  const endField = () => {
    if (parts.length > 0) {
      const first = parts[0]!;
      if (!first.quoted) first.text = first.text.replace(/^\s+/, '');
      const last = parts[parts.length - 1]!;
      if (!last.quoted) last.text = last.text.replace(/\s+$/, '');
    }
    currentRow.push(parts.map((p) => p.text).join(''));
    parts = [];
  };
  const endRow = () => {
    endField();
    if (currentRow.some((f) => f !== '')) rows.push(currentRow);
    currentRow = [];
  };

  while (i < content.length) {
    const char = content[i]!;
    if (inQuotes) {
      if (char === '"') {
        if (content[i + 1] === '"') {
          append('"', true);
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      append(char, true);
      i++;
      continue;
    }
    if (char === '"') {
      inQuotes = true;
      parts.push({ text: '', quoted: true });
      i++;
      continue;
    }
    if (char === delimiter) {
      endField();
      i++;
      continue;
    }
    if (char === '\n' || char === '\r') {
      endRow();
      i += char === '\r' && content[i + 1] === '\n' ? 2 : 1;
      continue;
    }
    append(char, false);
    i++;
  }
  if (parts.length > 0 || currentRow.length > 0) endRow();
  return rows;
}

/**
 * Detect the delimiter used in CSV content.
 */
export function detectDelimiter(content: string): string {
  if (content.charCodeAt(0) === 0xfeff) content = content.slice(1);
  const delimiters = [',', ';', '\t', '|'];
  const counts = new Map<string, number>(delimiters.map((d) => [d, 0]));
  let inQuotes = false;
  for (const char of content) {
    if (char === '"') {
      inQuotes = !inQuotes;
      continue;
    }
    if (inQuotes) continue;
    if (char === '\n' || char === '\r') break;
    if (counts.has(char)) counts.set(char, counts.get(char)! + 1);
  }
  let best = ',';
  let max = 0;
  for (const d of delimiters) {
    if (counts.get(d)! > max) {
      max = counts.get(d)!;
      best = d;
    }
  }
  return best;
}

''' + s[end:]
open(p, "w").write(s)
