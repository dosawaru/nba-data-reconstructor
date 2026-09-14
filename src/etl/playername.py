from typing import Dict, List
from nba_api.stats.static import players

class PlayerNameResolver:

    def __init__(self):
        # Load all static player profiles from local package dataset
        all_players = players.get_players()
        self._id_to_name: Dict[int, str] = {p["id"]: p["full_name"] for p in all_players}

    def resolve_lineup(self, player_ids: List[int]) -> List[str]:
        """Maps a list of integer IDs to 'Full Name (id)' strings."""
        return [
            f"{self._id_to_name.get(pid, 'Unknown')} ({pid})"
            for pid in player_ids
        ]