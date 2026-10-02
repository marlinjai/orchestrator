import { describe, it, expect } from 'vitest';
import { evaluateRule, evaluateSegmentGroup } from '../segment-evaluator';
import type { Contact, SegmentRule } from '../types';

function contact(overrides?: Partial<Contact>): Contact {
  return {
    id: 'c1',
    email: 'john@example.com',
    firstName: 'John',
    lastName: 'Doe',
    status: 'active',
    tags: ['vip', 'newsletter'],
    customFields: { age: '9', score: '10', fruit: 'banana', padded: ' 7 ' },
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

const rule = (field: string, operator: string, value: string) =>
  ({ field, operator, value }) as unknown as SegmentRule;

describe('ordering operators', () => {
  it('compares numbers numerically', () => {
    expect(evaluateRule(contact(), rule('age', 'greater_than', '10'))).toBe(false);
    expect(evaluateRule(contact(), rule('age', 'less_than', '10'))).toBe(true);
    expect(evaluateRule(contact(), rule('score', 'greater_than', '9'))).toBe(true);
    expect(evaluateRule(contact(), rule('score', 'less_than', '9'))).toBe(false);
  });

  it('treats equal numbers in different spellings as equal', () => {
    expect(evaluateRule(contact(), rule('score', 'greater_or_equal', '10.0'))).toBe(true);
    expect(evaluateRule(contact(), rule('score', 'less_or_equal', '1e1'))).toBe(true);
    expect(evaluateRule(contact(), rule('score', 'greater_than', '10.0'))).toBe(false);
    expect(evaluateRule(contact(), rule('score', 'less_than', '10.0'))).toBe(false);
  });

  it('trims before deciding that both sides are numbers', () => {
    expect(evaluateRule(contact(), rule('padded', 'less_than', '8'))).toBe(true);
    expect(evaluateRule(contact(), rule('padded', 'greater_or_equal', ' 7'))).toBe(true);
    expect(evaluateRule(contact(), rule('padded', 'greater_than', '10'))).toBe(false);
  });

  it('handles negative numbers and decimals', () => {
    const c = contact({ customFields: { balance: '-2.5' } });
    expect(evaluateRule(c, rule('balance', 'less_than', '-2'))).toBe(true);
    expect(evaluateRule(c, rule('balance', 'greater_or_equal', '-2.50'))).toBe(true);
    expect(evaluateRule(c, rule('balance', 'less_or_equal', '-3'))).toBe(false);
  });

  it('falls back to a case-insensitive string comparison', () => {
    expect(evaluateRule(contact(), rule('fruit', 'greater_than', 'Apple'))).toBe(true);
    expect(evaluateRule(contact(), rule('fruit', 'less_than', 'Cherry'))).toBe(true);
    expect(evaluateRule(contact(), rule('fruit', 'greater_or_equal', 'BANANA'))).toBe(true);
    expect(evaluateRule(contact(), rule('fruit', 'less_or_equal', 'BANANA'))).toBe(true);
    expect(evaluateRule(contact(), rule('fruit', 'less_than', 'BANANA'))).toBe(false);
  });

  it('uses the string comparison when one side is empty or not a number', () => {
    expect(evaluateRule(contact(), rule('missing', 'less_than', '5'))).toBe(true);
    expect(evaluateRule(contact(), rule('missing', 'greater_than', '5'))).toBe(false);
    // "9" against "10a": strings, and "9" sorts after "1".
    expect(evaluateRule(contact(), rule('age', 'greater_than', '10a'))).toBe(true);
  });
});

describe('list operators', () => {
  it('in matches a scalar field case-insensitively, items trimmed', () => {
    expect(evaluateRule(contact(), rule('status', 'in', 'Active, bounced'))).toBe(true);
    expect(evaluateRule(contact(), rule('status', 'in', 'bounced,complained'))).toBe(false);
    expect(evaluateRule(contact(), rule('email', 'in', ' JOHN@example.com '))).toBe(true);
    expect(evaluateRule(contact(), rule('fruit', 'in', 'apple,banana,,')) ).toBe(true);
  });

  it('in on tags compares tag by tag, not the joined string', () => {
    expect(evaluateRule(contact(), rule('tags', 'in', 'beta, VIP'))).toBe(true);
    expect(evaluateRule(contact(), rule('tags', 'in', 'beta,gamma'))).toBe(false);
    expect(evaluateRule(contact(), rule('tags', 'in', 'vip,newsletter'))).toBe(true);
    // The joined string "vip,newsletter" must not match as one item elsewhere.
    expect(evaluateRule(contact({ tags: ['vipnewsletter'] }), rule('tags', 'in', 'vip, newsletter'))).toBe(false);
    expect(evaluateRule(contact({ tags: [] }), rule('tags', 'in', 'vip'))).toBe(false);
  });

  it('not_in is the negation', () => {
    expect(evaluateRule(contact(), rule('status', 'not_in', 'Active, bounced'))).toBe(false);
    expect(evaluateRule(contact(), rule('status', 'not_in', 'bounced'))).toBe(true);
    expect(evaluateRule(contact(), rule('tags', 'not_in', 'beta,gamma'))).toBe(true);
    expect(evaluateRule(contact(), rule('tags', 'not_in', 'beta,vip'))).toBe(false);
  });

  it('an empty list matches nothing', () => {
    expect(evaluateRule(contact(), rule('status', 'in', ''))).toBe(false);
    expect(evaluateRule(contact(), rule('status', 'in', ' , '))).toBe(false);
    expect(evaluateRule(contact(), rule('status', 'not_in', ' , '))).toBe(true);
    expect(evaluateRule(contact({ customFields: {} }), rule('missing', 'in', ''))).toBe(false);
  });
});

describe('unchanged behavior', () => {
  it('keeps the existing operators', () => {
    expect(evaluateRule(contact(), rule('email', 'equals', 'JOHN@EXAMPLE.COM'))).toBe(true);
    expect(evaluateRule(contact(), rule('tags', 'contains', 'vip'))).toBe(true);
    expect(evaluateRule(contact(), rule('missing', 'is_empty', ''))).toBe(true);
    expect(evaluateRule(contact(), rule('email', 'ends_with', '.COM'))).toBe(true);
  });

  it('works inside a segment group', () => {
    const group = {
      logic: 'and' as const,
      rules: [rule('age', 'less_or_equal', '9'), rule('tags', 'in', 'vip')],
    };
    expect(evaluateSegmentGroup(contact(), group)).toBe(true);
  });
});
