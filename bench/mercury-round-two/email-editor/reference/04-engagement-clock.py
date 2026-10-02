import sys
root = sys.argv[1]
p = f"{root}/packages/analytics/src/engagement.ts"
s = open(p).read()
a = """  weights: EngagementWeights = DEFAULT_WEIGHTS,
): number {
  if (events.length === 0) return 0;

  const now = Date.now();
"""
assert a in s
s = s.replace(a, """  weights: EngagementWeights = DEFAULT_WEIGHTS,
  nowInput: Date | number = Date.now(),
): number {
  if (events.length === 0) return 0;

  const now = typeof nowInput === 'number' ? nowInput : nowInput.getTime();
""")
a = """    const decayFactor = Math.max(0, 1 - daysSince / weights.recencyDecayDays);
"""
assert a in s
s = s.replace(a, """    if (Number.isNaN(eventTime)) continue;
    const decayFactor = Math.min(1, Math.max(0, 1 - daysSince / weights.recencyDecayDays));
""")
start = s.index("export function buildContactEngagement(")
end = s.index("/**\n * Categorize a contact's engagement level")
s = s[:start] + """export function buildContactEngagement(
  contactId: string,
  events: TrackingEvent[],
  weights?: EngagementWeights,
  now?: Date | number,
): ContactEngagement {
  const opens = events.filter((e) => e.type === 'open');
  const clicks = events.filter((e) => e.type === 'click');

  const latest = (list: TrackingEvent[]): string | undefined => {
    let best: TrackingEvent | undefined;
    let bestTime = -Infinity;
    for (const e of list) {
      const t = new Date(e.timestamp).getTime();
      if (Number.isNaN(t)) continue;
      if (best === undefined || t > bestTime) {
        best = e;
        bestTime = t;
      }
    }
    return best?.timestamp;
  };

  return {
    contactId,
    totalOpens: opens.length,
    totalClicks: clicks.length,
    lastOpenAt: latest(opens),
    lastClickAt: latest(clicks),
    engagementScore: calculateEngagementScore(events, weights, now),
  };
}

""" + s[end:]
open(p, "w").write(s)
