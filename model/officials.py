"""Referee crews: does a crew push totals up or down?

Each referee carries a recency-weighted record of how far the games he worked finished above or below the
model's pre-game total, shrunk towards 0 until he has enough games. A crew's value is the average of its
three referees. Measured as a total-points factor like every other, and switched on only if it improves
out-of-sample totals (see ON).
"""
import os
from collections import defaultdict

HL = 120.0   # games
K = 40.0     # games of evidence for half weight
ON = os.environ.get("OFFICIALS_ON", "0") == "1"   # off: walk-forward test (2026) moved total MAE by <0.01, no real signal yet; kept for re-test later


class OfficialsTracker:
    def __init__(self):
        self.s = defaultdict(lambda: [0.0, 0.0, 0])  # name -> [weighted residual sum, weight sum, games]

    @staticmethod
    def names(refs):
        if not refs or not isinstance(refs, (str, list)):
            return []
        lst = refs if isinstance(refs, list) else str(refs).split(";")
        return [x.strip() for x in lst if x and x.strip() and x.strip() != "-"]

    def crew(self, refs):
        vals = []
        for n in self.names(refs):
            a, w, g = self.s[n]
            if w > 0:
                vals.append((a / w) * g / (g + K))
            else:
                vals.append(0.0)
        return sum(vals) / len(vals) if vals else 0.0

    def post_game(self, refs, residual_total):
        d = 0.5 ** (1 / HL)
        for n in self.names(refs):
            a, w, g = self.s[n]
            self.s[n] = [a * d + residual_total, w * d + 1.0, g + 1]
