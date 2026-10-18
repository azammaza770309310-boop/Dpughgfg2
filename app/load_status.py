"""Load-status computation for CrowdCloud services.

The pressure on a service is derived from its *active queue length* --
the number of tickets currently in the WAITING state:

    waiting <  BUSY_THRESHOLD                 -> NORMAL
    BUSY_THRESHOLD <= waiting < HIGH_THRESHOLD -> BUSY
    waiting >= HIGH_THRESHOLD                  -> HIGH LOAD

Keeping the rule explicit and configurable (environment variables)
makes the NORMAL -> BUSY -> HIGH LOAD transition observable and
reproducible during the live demo and in the automated tests.
"""

NORMAL = "NORMAL"
BUSY = "BUSY"
HIGH_LOAD = "HIGH LOAD"

LEVELS = (NORMAL, BUSY, HIGH_LOAD)

# Ranking used for the overall (cross-service) status.
_LEVEL_RANK = {NORMAL: 0, BUSY: 1, HIGH_LOAD: 2}


def compute_load(waiting: int, busy_threshold: int, high_threshold: int) -> str:
    """Map a waiting-tickets count to a load level."""
    if high_threshold <= busy_threshold:
        raise ValueError("high_threshold must be greater than busy_threshold")
    if waiting < 0:
        raise ValueError("waiting must be a non-negative integer")
    if waiting >= high_threshold:
        return HIGH_LOAD
    if waiting >= busy_threshold:
        return BUSY
    return NORMAL


def load_percent(waiting: int, high_threshold: int) -> int:
    """0-100 gauge value where 100 means HIGH LOAD has been reached."""
    if high_threshold <= 0:
        return 100
    return max(0, min(100, round(waiting / high_threshold * 100)))


def highest_level(levels) -> str:
    """Return the most severe level among the given ones."""
    worst = NORMAL
    for level in levels:
        if _LEVEL_RANK.get(level, 0) > _LEVEL_RANK[worst]:
            worst = level
    return worst
