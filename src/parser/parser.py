import logging
import re
from typing import Any, Dict, List, Optional

# logging configuration
logging.basicConfig(level= logging.INFO, format= "%(asctime)s - %(levelname)s - %(message)s")

# mapping of action types to event message types
EVENTMSGTYPE_BY_ACTION = {
    "made shot": 1,
    "missed shot": 2,
    "free throw": 3,
    "freethrow": 3,
    "rebound": 4,
    "turnover": 5,
    "foul": 6,
    "violation": 7,
    "substitution": 8,
    "timeout": 9,
    "jump ball": 10,
    "jumpball": 10,
    "ejection": 11,
    "instant replay": 18,
    "stoppage": 20,
}

CLOCK_PATTERN = re.compile(r"PT(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?")


class NBAPlayByPlayParser:
    """
    Transforms PlayByPlayV3 actions into structured events for the relational database schema
    """

    def parse_play_by_play(self, raw_payload: Dict[str, Any], game_id: str) -> List[Dict[str, Any]]:
        """
        Maps play-by-play game actions into structured event dictionaries
        """

        try:
            actions = self._extract_actions(raw_payload)
            if actions is None:
                logging.warning(
                    f"Payload for game {game_id} missing game actions. Keys present: {list(raw_payload.keys())}"
                )
                return []

            parsed_events = [self._structured_event(action, game_id) for action in actions]

            if not parsed_events:
                logging.warning(f"No play-by-play events parsed for game {game_id}")
                return []

            logging.info(f"Parsed {len(parsed_events)} events for game {game_id}")
            return parsed_events

        except Exception as e:
            logging.error(f"Error parsing play-by-play data for game {game_id}: {e}")
            raise

    # extract the actions from the payload
    def _extract_actions(self, raw_payload: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        game = raw_payload.get("game")
        if isinstance(game, dict) and "actions" in game:
            return game.get("actions") or []
        return None

    # structure the event
    def _structured_event(self, action: Dict[str, Any], game_id: str) -> Dict[str, Any]:
        location = (action.get("location") or "").lower()
        description = action.get("description") or None
        score_home = action.get("scoreHome")
        score_away = action.get("scoreAway")

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
            "player1_id": self._nullable_player_id(action.get("personId")),
            "player2_id": self._nullable_player_id(
                action.get("assistPersonId") or action.get("stealPersonId")
            ),
            "player3_id": self._nullable_player_id(
                action.get("blockPersonId") or action.get("foulDrawnPersonId")
            ),
        }

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
