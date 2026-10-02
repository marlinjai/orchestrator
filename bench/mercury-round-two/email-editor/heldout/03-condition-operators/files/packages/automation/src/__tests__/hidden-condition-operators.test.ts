import { describe, it, expect } from 'vitest';
import { evaluateRule, evaluateBranch } from '../condition-evaluator';
import type { EvaluationContext } from '../condition-evaluator';
import type { ConditionRule } from '../types';

function ctx(overrides?: Partial<EvaluationContext>): EvaluationContext {
  return {
    contact: {
      id: 'c-1',
      email: 'test@example.com',
      firstName: 'Alice',
      lastName: 'Smith',
      status: 'active',
      tags: ['vip', 'newsletter'],
      customFields: { plan: 'pro', country: 'US', seats: '12', blank: '' },
      createdAt: '2024-01-01T00:00:00Z',
      updatedAt: '2024-06-01T00:00:00Z',
    },
    ...overrides,
  };
}

const rule = (field: string, operator: string, value = '') =>
  ({ field, operator, value }) as unknown as ConditionRule;

describe('new operators', () => {
  it('starts_with and ends_with are case-sensitive', () => {
    expect(evaluateRule(rule('contact.email', 'starts_with', 'test@'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.email', 'starts_with', 'Test@'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.email', 'ends_with', '.com'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.email', 'ends_with', '.COM'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.firstName', 'ends_with', 'Alice'), ctx())).toBe(true);
  });

  it('is_empty and is_not_empty ignore the rule value', () => {
    expect(evaluateRule(rule('contact.customFields.blank', 'is_empty', 'whatever'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.customFields.missing', 'is_empty'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.customFields.plan', 'is_empty'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.customFields.plan', 'is_not_empty', 'x'), ctx())).toBe(true);
    expect(evaluateRule(rule('engagement.opened', 'is_not_empty'), ctx())).toBe(false);
  });

  it('matches_any compares scalars exactly against trimmed items', () => {
    expect(evaluateRule(rule('contact.customFields.plan', 'matches_any', 'free, pro'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.customFields.plan', 'matches_any', 'free,Pro'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.customFields.plan', 'matches_any', ''), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.customFields.blank', 'matches_any', ' , '), ctx())).toBe(false);
  });

  it('matches_any on contact.tags compares tag by tag', () => {
    expect(evaluateRule(rule('contact.tags', 'matches_any', 'beta, vip'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.tags', 'matches_any', 'beta,VIP'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.tags', 'matches_any', 'vip,newsletter'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.tags', 'matches_any', 'newsletter'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.tags', 'matches_any', 'news'), ctx())).toBe(false);
  });
});

describe('numeric comparisons', () => {
  it('compares numbers', () => {
    expect(evaluateRule(rule('contact.customFields.seats', 'greater_than', '9'), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.customFields.seats', 'less_than', ' 100 '), ctx())).toBe(true);
    expect(evaluateRule(rule('contact.customFields.seats', 'less_than', '12'), ctx())).toBe(false);
  });

  it('is false when a side is empty or not a number', () => {
    expect(evaluateRule(rule('contact.customFields.blank', 'less_than', '5'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.customFields.missing', 'greater_than', '-1'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.customFields.seats', 'greater_than', ''), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.customFields.plan', 'greater_than', '1'), ctx())).toBe(false);
    expect(evaluateRule(rule('contact.customFields.seats', 'less_than', 'many'), ctx())).toBe(false);
  });

  it('still works on engagement counters', () => {
    const c = ctx({ engagement: { openCount: 3 } });
    expect(evaluateRule(rule('engagement.openCount', 'greater_than', '2'), c)).toBe(true);
    expect(evaluateRule(rule('engagement.clickCount', 'less_than', '2'), c)).toBe(false);
  });
});

describe('nested event data', () => {
  const eventData = {
    order: { total: 120, items: ['a', 'b'], shipping: { country: 'DE', express: false }, note: null },
    vip: true,
    codes: [1, 2, 3],
    plain: 'x',
  };

  it('walks nested objects', () => {
    const c = ctx({ eventData });
    expect(evaluateRule(rule('eventData.order.total', 'equals', '120'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.order.total', 'greater_than', '100'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.order.shipping.country', 'equals', 'DE'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.order.shipping.express', 'is_false'), c)).toBe(true);
  });

  it('joins arrays with commas', () => {
    const c = ctx({ eventData });
    expect(evaluateRule(rule('eventData.order.items', 'equals', 'a,b'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.codes', 'equals', '1,2,3'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.codes', 'contains', '2'), c)).toBe(true);
  });

  it('resolves objects, nulls and missing keys to the empty string', () => {
    const c = ctx({ eventData });
    expect(evaluateRule(rule('eventData.order', 'is_empty'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.order.shipping', 'is_empty'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.order.note', 'is_empty'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.order.missing.deep', 'is_empty'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.nothing', 'is_empty'), c)).toBe(true);
  });

  it('does not walk into values that are not plain objects', () => {
    const c = ctx({ eventData });
    expect(evaluateRule(rule('eventData.order.total.cents', 'is_empty'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.plain.length', 'is_empty'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.codes.length', 'is_empty'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.codes.0', 'is_empty'), c)).toBe(true);
  });

  it('keeps the one-level form', () => {
    const c = ctx({ eventData });
    expect(evaluateRule(rule('eventData.vip', 'is_true'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.plain', 'equals', 'x'), c)).toBe(true);
    expect(evaluateRule(rule('eventData.plain', 'equals', 'x'), ctx())).toBe(false);
  });
});

describe('unchanged behavior', () => {
  it('keeps existing operators and branch logic', () => {
    const c = ctx({ engagement: { opened: true } });
    expect(evaluateRule(rule('contact.tags', 'contains', 'vip'), c)).toBe(true);
    expect(evaluateRule(rule('contact.status', 'not_equals', 'bounced'), c)).toBe(true);
    expect(evaluateRule(rule('engagement.clicked', 'is_false'), c)).toBe(true);
    const branch = {
      id: 'b',
      label: 'b',
      rules: [rule('engagement.opened', 'is_true'), rule('contact.tags', 'matches_any', 'vip')],
    };
    expect(evaluateBranch(branch, c)).toBe(true);
  });
});
