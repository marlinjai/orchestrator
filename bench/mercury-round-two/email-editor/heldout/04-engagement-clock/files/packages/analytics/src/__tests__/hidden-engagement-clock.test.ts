import { describe, it, expect } from 'vitest';
import { calculateEngagementScore, buildContactEngagement } from '../engagement';
import type { EngagementWeights } from '../engagement';
import type { TrackingEvent } from '../types';

const NOW = Date.parse('2024-06-30T00:00:00Z');
const DAY = 24 * 60 * 60 * 1000;

const weights: EngagementWeights = {
  open: 1,
  click: 3,
  bounce: -5,
  unsubscribe: -10,
  complaint: -10,
  delivered: 0,
  recencyDecayDays: 30,
};

let n = 0;
function event(type: TrackingEvent['type'], timestamp: string): TrackingEvent {
  return { id: `e${++n}`, campaignId: 'camp1', contactId: 'c1', type, timestamp };
}
const at = (ms: number) => new Date(ms).toISOString();

type Score = (events: TrackingEvent[], w?: EngagementWeights, now?: Date | number) => number;
type Build = (
  contactId: string,
  events: TrackingEvent[],
  w?: EngagementWeights,
  now?: Date | number,
) => ReturnType<typeof buildContactEngagement>;
const score = calculateEngagementScore as unknown as Score;
const build = buildContactEngagement as unknown as Build;

describe('calculateEngagementScore with a fixed clock', () => {
  it('decays against the given now, as a number', () => {
    // One open exactly 15 days before now: factor 0.5, score round(0.5 * 10) = 5.
    expect(score([event('open', at(NOW - 15 * DAY))], weights, NOW)).toBe(5);
    // One click 6 days before: 3 * 0.8 = 2.4 -> 24.
    expect(score([event('click', at(NOW - 6 * DAY))], weights, NOW)).toBe(24);
  });

  it('accepts a Date', () => {
    expect(score([event('open', at(NOW - 15 * DAY))], weights, new Date(NOW))).toBe(5);
  });

  it('gives nothing for events older than the decay window', () => {
    expect(score([event('click', at(NOW - 45 * DAY))], weights, NOW)).toBe(0);
  });

  it('counts a future event with a factor of exactly 1', () => {
    expect(score([event('open', at(NOW + 300 * DAY))], weights, NOW)).toBe(10);
    expect(score([event('click', at(NOW + 1))], weights, NOW)).toBe(30);
  });

  it('skips events whose timestamp cannot be parsed', () => {
    const events = [event('click', 'not a date'), event('open', ''), event('open', at(NOW))];
    expect(score(events, weights, NOW)).toBe(10);
    expect(score([event('click', 'garbage')], weights, NOW)).toBe(0);
  });

  it('still clamps and rounds', () => {
    const many = Array.from({ length: 10 }, () => event('click', at(NOW)));
    expect(score(many, weights, NOW)).toBe(100);
    expect(score([event('unsubscribe', at(NOW))], weights, NOW)).toBe(0);
    expect(score([], weights, NOW)).toBe(0);
  });

  it('defaults to the current time when now is omitted', () => {
    expect(calculateEngagementScore([event('open', new Date().toISOString())])).toBe(10);
  });
});

describe('buildContactEngagement', () => {
  it('passes now through to the score', () => {
    const e = build('c1', [event('open', at(NOW - 15 * DAY))], weights, NOW);
    expect(e.engagementScore).toBe(5);
    expect(e.contactId).toBe('c1');
  });

  it('picks the latest event by parsed time, across time zone offsets', () => {
    // 10:00+02:00 is 08:00Z, earlier than 09:00Z, although it sorts later as a string.
    const early = '2024-06-01T10:00:00+02:00';
    const late = '2024-06-01T09:00:00Z';
    const e = build('c1', [event('open', early), event('open', late), event('click', late), event('click', early)], weights, NOW);
    expect(e.lastOpenAt).toBe(late);
    expect(e.lastClickAt).toBe(late);
  });

  it('ignores unparseable timestamps for the last-event fields but still counts them', () => {
    const good = '2024-05-01T00:00:00Z';
    const e = build('c1', [event('open', 'zzz'), event('open', good), event('click', 'nope')], weights, NOW);
    expect(e.lastOpenAt).toBe(good);
    expect(e.lastClickAt).toBeUndefined();
    expect(e.totalOpens).toBe(2);
    expect(e.totalClicks).toBe(1);
  });

  it('keeps the first of two events with the same time', () => {
    const a = '2024-06-01T12:00:00Z';
    const b = '2024-06-01T14:00:00+02:00';
    const e = build('c1', [event('open', a), event('open', b)], weights, NOW);
    expect(e.lastOpenAt).toBe(a);
  });

  it('leaves both fields undefined without events', () => {
    const e = build('c1', [], weights, NOW);
    expect(e.lastOpenAt).toBeUndefined();
    expect(e.lastClickAt).toBeUndefined();
    expect(e.engagementScore).toBe(0);
  });
});
