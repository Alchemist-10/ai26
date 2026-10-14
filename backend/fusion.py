"""Conservative per-track consensus; review suggestions never override raw conflicts."""
from collections import defaultdict, deque
from collections import Counter


def _character_candidate(history):
    """Suggest a per-character vote only when every position has a strong winner."""
    reads = list(history)
    if len(reads) < 3 or len({item["plate"] for item in reads}) < 2:
        return None
    lengths = {len(item["plate"]) for item in reads}
    if len(lengths) != 1:
        return None
    candidate = []
    for index in range(next(iter(lengths))):
        votes = Counter()
        for item in reads:
            votes[item["plate"][index]] += item["confidence"]
        ranked = votes.most_common(2)
        winner, weight = ranked[0]
        total = sum(votes.values())
        runner_up = ranked[1][1] if len(ranked) > 1 else 0
        if weight / total < 0.75 or (weight - runner_up) / total < 0.25:
            return None
        candidate.append(winner)
    return "".join(candidate)

class PlateConsensus:
    def __init__(self, minimum_reads=3, window=8):
        self.minimum_reads = minimum_reads
        self.window = window
        self.history = defaultdict(lambda: deque(maxlen=window))

    def read(self, camera, track, plate, association_status='matched', confidence=1.0):
        if association_status == 'ambiguous':
            self.history.pop((camera, track), None)
            return {'identity_status': 'tracking_ambiguous', 'fused_plate': None, 'supporting_reads': 0}
        history = self.history[(camera, track)]
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.0
        if not 0 <= confidence <= 1:
            confidence = 0.0
        history.append({'plate': str(plate), 'confidence': max(confidence, 0.01)})
        if len({item['plate'] for item in history}) > 1:
            return {'identity_status': 'conflicting', 'fused_plate': None,
                    'supporting_reads': len(history),
                    'character_consensus_candidate': _character_candidate(history)}
        supported = len(history) >= self.minimum_reads
        return {'identity_status': 'supported' if supported else 'tentative',
                'fused_plate': plate if supported else None, 'supporting_reads': len(history),
                'character_consensus_candidate': None}

    def reset(self, camera):
        for key in list(self.history):
            if key[0] == camera: del self.history[key]

    def retain(self, camera, active_tracks):
        for key in list(self.history):
            if key[0] == camera and key[1] not in active_tracks: del self.history[key]
