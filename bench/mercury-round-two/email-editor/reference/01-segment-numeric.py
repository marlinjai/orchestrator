import sys
root = sys.argv[1]
p = f"{root}/packages/contacts/src/types.ts"
s = open(p).read()
a = "  | 'greater_than'\n  | 'less_than';"
assert a in s
s = s.replace(a, "  | 'greater_than'\n  | 'less_than'\n  | 'greater_or_equal'\n  | 'less_or_equal'\n  | 'in'\n  | 'not_in';")
open(p, "w").write(s)

p = f"{root}/packages/contacts/src/segment-evaluator.ts"
s = open(p).read()
a = """export function evaluateRule(contact: Contact, rule: SegmentRule): boolean {
  const fieldValue = getFieldValue(contact, rule.field);
"""
assert a in s
s = s.replace(a, """export function evaluateRule(contact: Contact, rule: SegmentRule): boolean {
  if (rule.operator === 'in' || rule.operator === 'not_in') {
    const items = rule.value
      .split(',')
      .map((item) => item.trim().toLowerCase())
      .filter((item) => item !== '');
    const candidates =
      rule.field === 'tags' ? contact.tags : [getFieldValue(contact, rule.field)];
    const found = candidates.some((c) => items.includes(c.trim().toLowerCase()));
    return rule.operator === 'in' ? found : !found;
  }
  const fieldValue = getFieldValue(contact, rule.field);
""")
a = """    case 'greater_than':
      return fieldValue > ruleValue;
    case 'less_than':
      return fieldValue < ruleValue;
"""
assert a in s
s = s.replace(a, """    case 'greater_than':
      return compare(fieldValue, ruleValue) > 0;
    case 'less_than':
      return compare(fieldValue, ruleValue) < 0;
    case 'greater_or_equal':
      return compare(fieldValue, ruleValue) >= 0;
    case 'less_or_equal':
      return compare(fieldValue, ruleValue) <= 0;
""")
s += """
function compare(a: string, b: string): number {
  const ta = a.trim();
  const tb = b.trim();
  if (ta !== '' && tb !== '' && Number.isFinite(Number(ta)) && Number.isFinite(Number(tb))) {
    return Number(ta) - Number(tb);
  }
  const la = a.toLowerCase();
  const lb = b.toLowerCase();
  return la < lb ? -1 : la > lb ? 1 : 0;
}
"""
open(p, "w").write(s)
