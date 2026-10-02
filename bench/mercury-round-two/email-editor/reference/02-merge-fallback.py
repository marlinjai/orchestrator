import sys
root = sys.argv[1]
p = f"{root}/packages/contacts/src/merge-fields.ts"
s = open(p).read()
start = s.index("const MERGE_FIELD_REGEX")
end = s.index("/**\n * List of built-in merge fields")
s = s[:start] + r'''const MERGE_FIELD_REGEX = /\{\{\s*(\w+)\s*(?:\|([^}]*))?\}\}/g;

function lookup(field: string, contact: Contact, extras?: Record<string, string>): string | undefined {
  switch (field) {
    case 'email':
      return contact.email;
    case 'first_name':
      return contact.firstName ?? '';
    case 'last_name':
      return contact.lastName ?? '';
    case 'full_name':
      return [contact.firstName, contact.lastName].filter(Boolean).join(' ');
    case 'status':
      return contact.status;
    default:
      break;
  }
  if (extras && field in extras) return extras[field]!;
  if (field in contact.customFields) return contact.customFields[field]!;
  return undefined;
}

export function resolveMergeFields(
  content: string,
  contact: Contact,
  extras?: Record<string, string>,
): string {
  return content.replace(MERGE_FIELD_REGEX, (match, field: string, fallback: string | undefined) => {
    const value = lookup(field, contact, extras);
    if (value !== undefined && value !== '') return value;
    if (fallback !== undefined) return fallback.trim();
    return value === undefined ? match : '';
  });
}

export function extractMergeFields(content: string): string[] {
  const fields: string[] = [];
  for (const match of content.matchAll(new RegExp(MERGE_FIELD_REGEX.source, 'g'))) {
    if (!fields.includes(match[1]!)) fields.push(match[1]!);
  }
  return fields;
}

export function extractMergeFieldFallbacks(content: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const match of content.matchAll(new RegExp(MERGE_FIELD_REGEX.source, 'g'))) {
    const field = match[1]!;
    if (match[2] !== undefined && !(field in out)) out[field] = match[2].trim();
  }
  return out;
}

''' + s[end:]
open(p, "w").write(s)
p = f"{root}/packages/contacts/src/index.ts"
s = open(p).read()
assert "extractMergeFields" in s
s = s.replace("extractMergeFields", "extractMergeFields, extractMergeFieldFallbacks", 1)
open(p, "w").write(s)
