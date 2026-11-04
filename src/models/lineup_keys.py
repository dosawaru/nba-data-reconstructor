"""Canonical lineup identity shared by priors, backtest, and API."""


def canonical_lineup_key(ids) -> str:
    """Normalize player-id lists/strings to a sorted comma-separated key."""
    if isinstance(ids, str):
        cleaned = ids.strip().strip("[]")
        if not cleaned:
            return ""
        parts = [int(x.strip().strip("'\"")) for x in cleaned.split(",") if x.strip()]
        return ",".join(str(x) for x in sorted(parts))
    try:
        return ",".join(str(int(x)) for x in sorted(ids))
    except TypeError:
        return str(ids)
