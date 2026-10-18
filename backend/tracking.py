"""Camera-local motion/box association. Costs are heuristics, not identity probabilities."""
import time
from collections import deque
from dataclasses import dataclass, field
from math import hypot, isfinite, log

TRACKER_VERSION = 'motion-box-assignment-v2'


def _assignment(costs):
    """Minimum-cost rectangular assignment (rows <= columns), O(rows² * columns)."""
    if not costs: return []
    rows, columns = len(costs), len(costs[0])
    if columns < rows or any(len(row) != columns for row in costs):
        raise ValueError('Assignment requires a rectangular matrix with rows <= columns')
    u, v = [0.] * (rows + 1), [0.] * (columns + 1)
    owner, previous = [0] * (columns + 1), [0] * (columns + 1)
    for row in range(1, rows + 1):
        owner[0] = row
        column = 0
        distances, used = [float('inf')] * (columns + 1), [False] * (columns + 1)
        while True:
            used[column] = True
            active = owner[column]
            delta, next_column = float('inf'), 0
            for candidate in range(1, columns + 1):
                if used[candidate]: continue
                reduced = costs[active - 1][candidate - 1] - u[active] - v[candidate]
                if reduced < distances[candidate]:
                    distances[candidate], previous[candidate] = reduced, column
                if distances[candidate] < delta:
                    delta, next_column = distances[candidate], candidate
            for candidate in range(columns + 1):
                if used[candidate]:
                    u[owner[candidate]] += delta
                    v[candidate] -= delta
                else: distances[candidate] -= delta
            column = next_column
            if owner[column] == 0: break
        while column:
            parent = previous[column]
            owner[column] = owner[parent]
            column = parent
    result = [-1] * rows
    for column in range(1, columns + 1):
        if owner[column]: result[owner[column] - 1] = column - 1
    return result


def _center(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _iou(a, b):
    overlap = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = lambda box: max(0, box[2] - box[0]) * max(0, box[3] - box[1])
    union = area(a) + area(b) - overlap
    return overlap / union if union else 0


@dataclass
class _Track:
    track_id: int
    label: str
    center: tuple[float, float]
    bbox: tuple[int, int, int, int]
    last_seen: float
    velocity: tuple[float, float] = (0., 0.)
    missed: int = 0
    history: deque = field(default_factory=lambda: deque(maxlen=12))


class CentroidTracker:
    """Compatibility name for bounded motion-aware global single-camera association.

    Brief gaps can use motion prediction; expired or ambiguous tracks never carry
    their previous identity into a new observation. Replay/session resets are owned
    by the processor. This tracker has no learned appearance or cross-camera ReID.
    """

    def __init__(self, max_distance=140, max_missing=12, max_age_seconds=12., ambiguity_margin=.04):
        if max_distance <= 0 or max_missing < 0 or max_age_seconds <= 0 or ambiguity_margin < 0:
            raise ValueError('Invalid tracker bounds')
        self.max_distance, self.max_missing = max_distance, max_missing
        self.max_age_seconds, self.ambiguity_margin = max_age_seconds, ambiguity_margin
        self._next_id = 1
        self._tracks = []
        self._last_timestamp = None

    @property
    def active_ids(self):
        return {track.track_id for track in self._tracks}

    def _cost(self, track, detection, now):
        if track.label != detection['label']: return 1e6
        box = detection['bbox']
        width, height = box[2] - box[0], box[3] - box[1]
        old_width, old_height = track.bbox[2] - track.bbox[0], track.bbox[3] - track.bbox[1]
        if min(width, height, old_width, old_height) <= 0: return 1e6
        area_ratio = width * height / (old_width * old_height)
        aspect_ratio = width / height / (old_width / old_height)
        if not .25 <= area_ratio <= 4 or not 1/3 <= aspect_ratio <= 3: return 1e6
        elapsed = now - track.last_seen
        dx, dy = track.velocity[0] * elapsed, track.velocity[1] * elapsed
        predicted = [track.bbox[0] + dx, track.bbox[1] + dy, track.bbox[2] + dx, track.bbox[3] + dy]
        center = _center(box)
        distance = hypot(center[0] - track.center[0] - dx, center[1] - track.center[1] - dy)
        limit = max(self.max_distance, width * .75)
        if distance > limit: return 1e6
        return .75 * distance / limit + .2 * (1 - _iou(predicted, box)) + .05 * abs(log(area_ratio)) / log(4)

    def update(self, detections, timestamp=None):
        now = time.monotonic() if timestamp is None else timestamp
        if not isfinite(now) or (self._last_timestamp is not None and now < self._last_timestamp):
            raise ValueError('Tracker timestamps must be finite and ordered within a session')
        self._last_timestamp = now
        self._tracks = [t for t in self._tracks if now - t.last_seen <= self.max_age_seconds and t.missed <= self.max_missing]
        for track in self._tracks: track.missed += 1
        # Dummy columns permit unmatched detections; invalid pairs cannot be forced.
        track_count = len(self._tracks)
        pair_costs = [[self._cost(track, detection, now) for track in self._tracks] for detection in detections]
        selected = _assignment([row + [1.1] * len(detections) for row in pair_costs])
        ambiguous_detections, retired_tracks = set(), set()
        for di, ti in enumerate(selected):
            if ti >= track_count or pair_costs[di][ti] >= 1.1: continue
            cost = pair_costs[di][ti]
            alternative_tracks = {j for j, value in enumerate(pair_costs[di]) if j != ti and abs(value - cost) <= self.ambiguity_margin}
            competing_detections = {j for j, row in enumerate(pair_costs) if j != di and abs(row[ti] - cost) <= self.ambiguity_margin}
            if alternative_tracks or competing_detections:
                ambiguous_detections.update({di} | competing_detections)
                retired_tracks.update({ti} | alternative_tracks)
        retired_tracks.update(selected[di] for di in ambiguous_detections if selected[di] < track_count)
        # Any selected observation whose old track is implicated must also abstain.
        ambiguous_detections.update(di for di, ti in enumerate(selected) if ti in retired_tracks)
        updated = []
        for di, detection in enumerate(detections):
            box, center = tuple(detection['bbox']), _center(detection['bbox'])
            ti = selected[di]
            ambiguous = di in ambiguous_detections
            matched = not ambiguous and ti < track_count and pair_costs[di][ti] < 1.1
            if matched:
                track = self._tracks[ti]
                elapsed = now - track.last_seen
                if elapsed > 0:
                    measured = ((center[0] - track.center[0]) / elapsed, (center[1] - track.center[1]) / elapsed)
                    track.velocity = measured
                track.center, track.bbox, track.last_seen, track.missed = center, box, now, 0
            else:
                track = _Track(self._next_id, detection['label'], center, box, now)
                self._next_id += 1
                self._tracks.append(track)
            observed = (round(center[0]), round(center[1]))
            track.history.append(observed)
            updated.append({**detection, 'track_id': track.track_id, 'track_history': list(track.history),
                            'association_status': 'ambiguous' if ambiguous else 'matched' if matched else 'new',
                            'association_cost': round(pair_costs[di][ti], 4) if matched else None})
        self._tracks = [t for i, t in enumerate(self._tracks) if i not in retired_tracks and t.missed <= self.max_missing]
        return updated
