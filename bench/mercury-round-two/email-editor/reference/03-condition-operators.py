import sys
root = sys.argv[1]
p = f"{root}/packages/automation/src/types.ts"
s = open(p).read()
a = "| 'is_true' | 'is_false';"
assert a in s
s = s.replace(a, "| 'is_true' | 'is_false' | 'starts_with' | 'ends_with' | 'is_empty' | 'is_not_empty' | 'matches_any';")
open(p, "w").write(s)

p = f"{root}/packages/automation/src/condition-evaluator.ts"
s = open(p).read()
a = """  if (root === 'eventData' && ctx.eventData) {
    const prop = parts[1];
    if (!prop) return '';
    const val = ctx.eventData[prop];
    return val != null ? String(val) : '';
  }
"""
assert a in s
s = s.replace(a, """  if (root === 'eventData' && ctx.eventData) {
    if (parts.length < 2 || !parts[1]) return '';
    let val: unknown = ctx.eventData;
    for (const key of parts.slice(1)) {
      if (val === null || typeof val !== 'object' || Array.isArray(val)) return '';
      val = (val as Record<string, unknown>)[key];
    }
    if (val == null) return '';
    if (Array.isArray(val)) return val.map((v) => String(v)).join(',');
    if (typeof val === 'object') return '';
    return String(val);
  }
""")
a = """    case 'greater_than':
      return Number(fieldValue) > Number(rule.value);
    case 'less_than':
      return Number(fieldValue) < Number(rule.value);
"""
assert a in s
s = s.replace(a, """    case 'greater_than':
    case 'less_than': {
      const a = fieldValue.trim();
      const b = rule.value.trim();
      if (a === '' || b === '' || !Number.isFinite(Number(a)) || !Number.isFinite(Number(b))) return false;
      return rule.operator === 'greater_than' ? Number(a) > Number(b) : Number(a) < Number(b);
    }
    case 'starts_with':
      return fieldValue.startsWith(rule.value);
    case 'ends_with':
      return fieldValue.endsWith(rule.value);
    case 'is_empty':
      return fieldValue === '';
    case 'is_not_empty':
      return fieldValue !== '';
    case 'matches_any': {
      const items = rule.value.split(',').map((i) => i.trim()).filter((i) => i !== '');
      const candidates = rule.field === 'contact.tags' ? ctx.contact.tags : [fieldValue];
      return candidates.some((c) => items.includes(c));
    }
""")
open(p, "w").write(s)
