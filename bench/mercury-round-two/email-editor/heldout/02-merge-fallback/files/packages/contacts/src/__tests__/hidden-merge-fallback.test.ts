import { describe, it, expect } from 'vitest';
import * as mergeFields from '../merge-fields';
import * as index from '../index';
import type { Contact } from '../types';

const { resolveMergeFields, extractMergeFields } = mergeFields;
const extractMergeFieldFallbacks = (mergeFields as Record<string, unknown>)
  .extractMergeFieldFallbacks as (content: string) => Record<string, string>;

function contact(overrides?: Partial<Contact>): Contact {
  return {
    id: 'c1',
    email: 'jo@example.com',
    status: 'active',
    tags: [],
    customFields: { company: 'Acme', empty: '' },
    createdAt: '2024-01-01T00:00:00Z',
    updatedAt: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('resolveMergeFields with fallbacks', () => {
  it('uses the fallback when the field is empty', () => {
    expect(resolveMergeFields('Hi {{first_name|there}}!', contact())).toBe('Hi there!');
    expect(resolveMergeFields('{{empty|none}}', contact())).toBe('none');
    expect(resolveMergeFields('{{full_name|friend}}', contact())).toBe('friend');
  });

  it('prefers the value when there is one', () => {
    const c = contact({ firstName: 'Jo', lastName: 'Lee' });
    expect(resolveMergeFields('Hi {{first_name|there}}!', c)).toBe('Hi Jo!');
    expect(resolveMergeFields('{{full_name|friend}}', c)).toBe('Jo Lee');
    expect(resolveMergeFields('{{ company | your company }}', c)).toBe('Acme');
    expect(resolveMergeFields('{{email|nobody}}', c)).toBe('jo@example.com');
  });

  it('uses the fallback for an unknown field', () => {
    expect(resolveMergeFields('{{nickname|buddy}}', contact())).toBe('buddy');
    expect(resolveMergeFields('{{ nickname | dear customer }}', contact())).toBe('dear customer');
  });

  it('accepts an empty fallback', () => {
    expect(resolveMergeFields('[{{nickname|}}]', contact())).toBe('[]');
    expect(resolveMergeFields('[{{ first_name | }}]', contact())).toBe('[]');
  });

  it('keeps an unknown field without a fallback exactly as written', () => {
    expect(resolveMergeFields('{{nickname}}', contact())).toBe('{{nickname}}');
    expect(resolveMergeFields('{{ nickname }}', contact())).toBe('{{ nickname }}');
  });

  it('resolves placeholders with inner whitespace', () => {
    expect(resolveMergeFields('{{ email }}', contact())).toBe('jo@example.com');
    expect(resolveMergeFields('{{ first_name }}', contact())).toBe('');
  });

  it('looks in extras before custom fields, and falls back when an extra is empty', () => {
    const c = contact();
    expect(resolveMergeFields('{{company|x}}', c, { company: 'Override' })).toBe('Override');
    expect(resolveMergeFields('{{unsubscribe_url|#}}', c, { unsubscribe_url: '' })).toBe('#');
    expect(resolveMergeFields('{{unsubscribe_url}}', c, { unsubscribe_url: 'https://u.test/1' })).toBe(
      'https://u.test/1',
    );
  });

  it('leaves text that is not a placeholder alone', () => {
    expect(resolveMergeFields('{{first name}} {{}} {{|x}}', contact())).toBe('{{first name}} {{}} {{|x}}');
  });

  it('keeps pipes and punctuation inside the fallback', () => {
    expect(resolveMergeFields('{{nickname|a | b, c!}}', contact())).toBe('a | b, c!');
  });

  it('handles several placeholders in one string', () => {
    const out = resolveMergeFields('{{first_name|there}} from {{company}} ({{status}})', contact());
    expect(out).toBe('there from Acme (active)');
  });
});

describe('extractMergeFields', () => {
  it('returns names only, once each, in order', () => {
    const content = 'Hi {{first_name|there}}, {{ company | us }} {{first_name}} {{email}}';
    expect(extractMergeFields(content)).toEqual(['first_name', 'company', 'email']);
  });

  it('ignores text that is not a placeholder', () => {
    expect(extractMergeFields('{{first name}} {{}} plain')).toEqual([]);
  });
});

describe('extractMergeFieldFallbacks', () => {
  it('maps each field to its first fallback', () => {
    const content = '{{first_name}} {{first_name|there}} {{first_name|friend}} {{ company | us }} {{email}}';
    expect(extractMergeFieldFallbacks(content)).toEqual({ first_name: 'there', company: 'us' });
  });

  it('records an empty fallback and returns an empty object without any', () => {
    expect(extractMergeFieldFallbacks('{{nickname|}}')).toEqual({ nickname: '' });
    expect(extractMergeFieldFallbacks('{{email}} plain')).toEqual({});
  });

  it('is exported from the package index', () => {
    expect((index as Record<string, unknown>).extractMergeFieldFallbacks).toBe(extractMergeFieldFallbacks);
  });
});
