import logging
import re
import unicodedata
from typing import Any, Dict, List, Optional
from src.parser.event_type import EVENTMSGTYPE_BY_ACTION

# logging configuration
logging.basicConfig(level= logging.INFO, format= "%(asctime)s - %(levelname)s - %(message)s")

CLOCK_PATTERN = re.compile(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")
SUB_INCOMING_PATTERN = re.compile(r"SUB:\s+(.+?)\s+FOR")

class NBAPlayByPlayParser:
    """
    Transforms PlayByPlayV3 actions into structured events for the relational database schema
    """

    def parse_play_by_play(self, raw_payload: Dict[str, Any], game_id: str) -> List[Dict[str, Any]]:
        """
        Maps play-by-play game actions into structured event dictionaries
        """

        try:
            actions = (raw_payload.get("game") or {}).get("actions", [])  
            if not actions:
                logging.warning(f"No play-by-play events parsed for game {game_id}")
                return []

            # compile the roster matrix
            roster_map = self._compile_roster_matrix(actions)

            # transform chronological events
            parsed_events = [self._structured_event(a, game_id, roster_map) for a in actions]
            parsed_events = self._merge_shared_eventnums(parsed_events)

            logging.info(f"Parsed {len(parsed_events)} events for game {game_id}")
            return parsed_events
        
        except Exception as e:
            logging.error(f"Error parsing play-by-play data for game {game_id}: {e}")
            raise

    # normalize the name
    def normalize_name(self, name: str) -> str:
        if not name:
            return ""
        nfkd_form = unicodedata.normalize("NFKD", name)
        normalized = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
        return normalized.strip().lower()

    # generate lookup matrix from the event stream. 
    def _compile_roster_matrix(self, actions: List[Dict[str, Any]]) -> Dict[str, int]:
        roster_map = {}
        for action in actions:
            pid = action.get("personId")
            name = action.get("playerName")
            if pid and name and int(pid) > 0:
                roster_map[self.normalize_name(name)] = int(pid)
        return roster_map

    # structure the event into a dictionary 
    def _structured_event(self, action: Dict[str, Any], game_id: str, roster_map: Dict[str, int]) -> Dict[str, Any]:
        location = (action.get("location") or "").lower()
        description = action.get("description") or None
        score_home = action.get("scoreHome")
        score_away = action.get("scoreAway")

        eventmsgtype = self._eventmsgtype(action)

        # Node Mapping
        player1_id = self._nullable_player_id(action.get("personId"))
        player2_id = None
        player3_id = None

        # Substitution Event
        if eventmsgtype == 8: 
            player2_id = self._resolve_incoming_node(description, roster_map)
        else:
            player2_id = self._nullable_player_id(action.get("assistPersonId") or action.get("stealPersonId"))
            player3_id = self._nullable_player_id(action.get("blockPersonId") or action.get("foulDrawnPersonId"))

        # Return the structured event
        return {
            "game_id": str(action.get("gameId") or game_id),
            "eventnum": int(action.get("actionNumber") or 0),
            "eventmsgtype": self._eventmsgtype(action),
            "eventmsgactiontype": 0,
            "period": int(action.get("period") or 0),
            "pctimestring": self._clock_to_pctime(action.get("clock")),
            "homedescription": description if location == "h" else None,
            "neutraldescription": description if location not in ("h", "v") else None,
            "visitordescription": description if location == "v" else None,
            "score": self._format_score(score_home, score_away),
            "scoremargin": self._format_margin(score_home, score_away),
            "player1_id": player1_id,
            "player2_id": player2_id,
            "player3_id": player3_id,
        }

    def _merge_shared_eventnums(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """ Used to merge shared event numbers """
        merged: Dict[int, Dict[str, Any]] = {}
        order: List[int] = []

        for event in events:
            key = event["eventnum"]
            existing = merged.get(key)
            if existing is None:
                merged[key] = event
                order.append(key)
                continue

            for field in (
                "homedescription",
                "visitordescription",
                "neutraldescription",
                "score",
                "scoremargin",
            ):
                if not existing.get(field) and event.get(field):
                    existing[field] = event[field]

            if not existing.get("eventmsgtype") and event.get("eventmsgtype"):
                existing["eventmsgtype"] = event["eventmsgtype"]

            if not existing.get("player2_id") and event.get("player1_id"):
                existing["player2_id"] = event["player1_id"]
            elif not existing.get("player3_id") and event.get("player1_id"):
                existing["player3_id"] = event["player1_id"]

        return [merged[key] for key in order]

    # determine the incoming player ID from the description
    def _resolve_incoming_node(self, description: str, roster_map: Dict[str, int]) -> Optional[int]:
        match = SUB_INCOMING_PATTERN.search(description)
        if match:
            raw_name = match.group(1)
            normalized_name = self.normalize_name(raw_name)
            
            # Lookup the player ID from the roster map
            if normalized_name in roster_map:
                return roster_map[normalized_name]
            
            # Fallback iteration for partial matches
            for dict_name, pid in roster_map.items():
                if normalized_name in dict_name or dict_name in normalized_name:
                    return pid
                    
            logging.warning(f"Node Resolution Failure: Could not map incoming target '{raw_name}' to integer ID.")
        return None

    # determine the event message type
    def _eventmsgtype(self, action: Dict[str, Any]) -> int:
        action_type = (action.get("actionType") or "").strip().lower()
        sub_type = (action.get("subType") or "").strip().lower()
        shot_result = (action.get("shotResult") or "").strip().lower()

        if action_type in {"2pt", "3pt"}:
            return 1 if shot_result == "made" else 2
        if action_type == "period":
            return 13 if "end" in sub_type else 12
        return EVENTMSGTYPE_BY_ACTION.get(action_type, 0)

    # convert the clock time to a percentage time string
    def _clock_to_pctime(self, clock: Optional[str]) -> str:
        if not clock:
            return ""
        if ":" in clock and not str(clock).startswith("PT"):
            return str(clock)
        match = CLOCK_PATTERN.fullmatch(str(clock))
        if not match:
            return str(clock)
        minutes = int(match.group(1) or 0)
        seconds = float(match.group(2) or 0)
        return f"{minutes}:{int(seconds):02d}"

    # format the score
    def _format_score(self, score_home: Any, score_away: Any) -> Optional[str]:
        if score_home in (None, "") or score_away in (None, ""):
            return None
        return f"{score_home} - {score_away}"

    # format the margin
    def _format_margin(self, score_home: Any, score_away: Any) -> Optional[str]:
        try:
            margin = int(score_home) - int(score_away)
        except (TypeError, ValueError):
            return None
        return "TIE" if margin == 0 else str(margin)

    # convert the player ID to a nullable integer
    def _nullable_player_id(self, person_id: Any) -> Optional[int]:
        try:
            player_id = int(person_id)
        except (TypeError, ValueError):
            return None
        return player_id or None
