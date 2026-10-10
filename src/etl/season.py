def game_id_to_season(game_id: str) -> str:
    """
    Derive NBA season label from game_id (e.g. 0022400002 -> 2024-25).
    Digits at index 3:5 are the two-digit start year of the season.
    """
    gid = str(game_id).strip()
    if len(gid) < 5:
        raise ValueError(f"Invalid game_id: {game_id}")
    yy = int(gid[3:5])
    return f"20{yy}-{yy + 1:02d}"
