import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Any, Tuple, Dict

# Define event type for rebound classification and primary side hints
_REBOUND_COUNTS = re.compile(r"\(off:\s*(\d+)\s*def:\s*(\d+)\)", re.IGNORECASE)
_PRIMARY_HINTS = {
    1: ("pts", "3pt", "layup", "dunk", "jump shot", "hook", "floater", "fadeaway"),
    2: ("miss",),
    3: ("free throw",),
    4: ("rebound",),
    5: ("turnover",),
    6: ("foul",),
}


# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

@dataclass
class StintAccumulator:
    """Accumulate stints for each player and team"""
    game_id: str
    period: int
    home_lineup: Tuple[int, ...]
    away_lineup: Tuple[int, ...]
    start_clock: str
    start_seconds: float
    end_clock: str = ""
    end_seconds: float = 0.0

    # home team stats
    home_pts: int = 0
    home_fga: int = 0
    home_fgm: int = 0
    home_fg3a: int = 0
    home_fg3m: int = 0
    home_fta: int = 0
    home_ftm: int = 0
    home_oreb: int = 0
    home_dreb: int = 0
    home_tov: int = 0
    home_pf: int = 0

    # away team stats
    away_pts: int = 0
    away_fga: int = 0
    away_fgm: int = 0
    away_fg3a: int = 0
    away_fg3m: int = 0
    away_fta: int = 0
    away_ftm: int = 0
    away_oreb: int = 0
    away_dreb: int = 0
    away_tov: int = 0
    away_pf: int = 0

    events: List[Dict[str, Any]] = field(default_factory=list)

    def generate_stint_id(self) -> str:
        """Generate a unique ID for the stint"""
        unique_id = (
            f"{self.game_id}-{self.period}-{self.start_seconds}-{self.end_seconds}"
            f"{'_'.join(map(str, self.home_lineup))}-{'_'.join(map(str, self.away_lineup))}"
        )
        return hashlib.sha256(unique_id.encode('utf-8')).hexdigest()[:16]

    def to_record(self) -> Dict[str, Any]:
        """ Calculate the final duration, possesions, and other stats"""
        duration = max(0.0, self.start_seconds - self.end_seconds)

        # empirical formula for possessions (FGA + 0.44 * FTA - OREB + TO)
        home_possessions = self.home_fga + (0.44 * self.home_fta) - self.home_oreb + self.home_tov
        away_possessions = self.away_fga + (0.44 * self.away_fta) - self.away_oreb + self.away_tov

        return {
            "stint_id": self.generate_stint_id(),
            "game_id": self.game_id,
            "period": self.period,
            "start_clock": self.start_clock,
            "end_clock": self.end_clock,
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration": round(duration, 2),
            "home_lineup": list(self.home_lineup),
            "away_lineup": list(self.away_lineup),
            "home_possessions": round(home_possessions),
            "away_possessions": round(away_possessions),
            "home_pts": self.home_pts,
            "away_pts": self.away_pts,
            "home_fgm": self.home_fgm,
            "away_fgm": self.away_fgm,
            "home_fga": self.home_fga,
            "away_fga": self.away_fga,
            "home_ftm": self.home_ftm,
            "away_ftm": self.away_ftm,
            "home_fta": self.home_fta,
            "away_fta": self.away_fta,
            "home_fg3m": self.home_fg3m,
            "away_fg3m": self.away_fg3m,
            "home_fg3a": self.home_fg3a,
            "away_fg3a": self.away_fg3a,
            "home_oreb": self.home_oreb,
            "away_oreb": self.away_oreb,
            "home_dreb": self.home_dreb,
            "away_dreb": self.away_dreb,
            "home_tov": self.home_tov,
            "away_tov": self.away_tov,
            "home_pf": self.home_pf,
            "away_pf": self.away_pf,
            "event_count": len(self.events),
        }
class StintAggregator:
    """Collects and aggregates countinous states-annotated eventes into discrete stints"""

    def __init__(self) -> None:
        self._last_miss_team: Optional[str] = None
        self._reb_counts: Dict[int, Tuple[int, int]] = {}

    @staticmethod
    def clock_to_seconds(clock: str) -> float:
        """Convert clock time (MM:SS) to seconds"""
        if not clock or ":" not in clock:
            return 0.0
        try:
            parts = clock.strip().split(":")
            minutes = int(parts[0])
            seconds = int(parts[1])
            return minutes * 60 + seconds
        except ValueError:
            return 0.0
        
    def aggregate_stints(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Travereses reconstructed events and construc internal stings on lineup changes"""

        if not events:
            return []

        self._last_miss_team = None
        self._reb_counts = {}
        stints: List[Dict[str, Any]] = []
        current_stint: Optional[StintAccumulator] = None

        for event in events:
            game_id = int(event.get("game_id"))
            period = int(event.get("period", 0))
            clock = str(event.get("pctimestring") or event.get("pctime_string") or "")
            seconds = self.clock_to_seconds(clock)
            
            home_lineup = tuple(sorted(event.get("home_lineup") or []))
            away_lineup = tuple(sorted(event.get("away_lineup") or []))

            if len(home_lineup) != 5 or len(away_lineup) != 5:
                logging.warning(f"Invalid lineup in event {event.get('event_id')}: Home={home_lineup}, Away={away_lineup}")
                continue

            # check if this is a boundary event (new stint or lineup change)
            is_boundry_event = (
                current_stint is None 
                or current_stint.period != period
                or current_stint.home_lineup != home_lineup
                or current_stint.away_lineup != away_lineup
            )

            # finalize the current stint and start a new one if boundary event
            if is_boundry_event:
                if current_stint is not None:
                    if current_stint.period != period:
                        current_stint.end_clock = "0:00"
                        current_stint.end_seconds = 0.0
                    else:
                        current_stint.end_clock = clock
                        current_stint.end_seconds = seconds
                    stints.append(current_stint.to_record())

                current_stint = StintAccumulator(
                    game_id=game_id,
                    period=period,
                    home_lineup=home_lineup,
                    away_lineup=away_lineup,
                    start_clock=clock,
                    start_seconds=seconds,
                )

            # record the event in the current stint
            self._accumulate_event(current_stint, event)

        if current_stint is not None:
            current_stint.end_clock = "0:00"
            current_stint.end_seconds = 0.0
            stints.append(current_stint.to_record())


        logging.info(f"Aggregated {len(stints)} stints for game {game_id}")
        return stints

    def _accumulate_event(self, acc: StintAccumulator, event: Dict[str, Any]):
        """Categorizes and accumulates stats based on event type"""

        acc.events.append(event)
        msg_type = int(event.get("eventmsgtype") or event.get("event_type") or 0)
        player_id = event.get("player1_id") or event.get("player_id")
        side, desc = self._action_side(event, acc)
        is_home_event = side == "home"

        # made field goal
        if msg_type == 1:  
            self._last_miss_team = None
            is_there_three = "3pt" in desc or "3-pt" in desc
            pts = 3 if is_there_three else 2

            if is_home_event:
                acc.home_pts += pts
                acc.home_fga += 1
                acc.home_fgm += 1 
                if is_there_three: 
                    acc.home_fg3a += 1
                    acc.home_fg3m += 1
            else:
                acc.away_pts += pts
                acc.away_fga += 1
                acc.away_fgm += 1 
                if is_there_three: 
                    acc.away_fg3a += 1
                    acc.away_fg3m += 1

        # missed field goal
        elif msg_type == 2:
            self._last_miss_team = "home" if is_home_event else "away"
            is_there_three = "3pt" in desc or "3-pt" in desc
            if is_home_event: 
                acc.home_fga += 1
                if is_there_three:
                    acc.home_fg3a += 1
            else:
                acc.away_fga += 1
                if is_there_three:
                    acc.away_fg3a += 1

        # free throw
        elif msg_type == 3:
            is_made = "miss" not in desc
            if is_made:
                self._last_miss_team = None
            else:
                self._last_miss_team = "home" if is_home_event else "away"
            if is_home_event:
                acc.home_fta += 1
                if is_made:
                    acc.home_ftm += 1
                    acc.home_pts += 1
            else:
                acc.away_fta += 1
                if is_made:
                    acc.away_ftm += 1
                    acc.away_pts += 1

        # rebound
        elif msg_type == 4:
            is_offensive = self._is_offensive_rebound(desc, is_home_event, player_id)
            if is_home_event:
                if is_offensive:
                    acc.home_oreb += 1
                else:
                    acc.home_dreb += 1
            else:
                if is_offensive:
                    acc.away_oreb += 1
                else:
                    acc.away_dreb += 1
            
        # turnover
        elif msg_type == 5:
            if is_home_event:
                acc.home_tov += 1
            else:
                acc.away_tov += 1

        # foul
        elif msg_type == 6:
            if is_home_event:
                acc.home_pf += 1
            else:
                acc.away_pf += 1

    def _action_side(
        self, event: Dict[str, Any], acc: StintAccumulator
    ) -> Tuple[Optional[str], str]:
        """Determine the team that owns the primary action"""

        home_desc = event.get("homedescription") or event.get("home_description") or ""
        away_desc = event.get("visitordescription") or event.get("away_description") or ""
        player_id = event.get("player1_id") or event.get("player_id")
        msg_type = int(event.get("eventmsgtype") or event.get("event_type") or 0)
        home_l = home_desc.lower()
        away_l = away_desc.lower()

        if home_l and away_l:
            side = self._primary_side(msg_type, home_l, away_l)
            if side == "home":
                return "home", home_l
            if side == "away":
                return "away", away_l

        if home_l and not away_l:
            return "home", home_l
        if away_l and not home_l:
            return "away", away_l

        if player_id:
            in_home = player_id in acc.home_lineup
            in_away = player_id in acc.away_lineup
            if in_home and not in_away:
                return "home", home_l or away_l
            if in_away and not in_home:
                return "away", home_l or away_l
        return None, home_l or away_l

    @staticmethod
    def _primary_side(msg_type: int, home_l: str, away_l: str) -> Optional[str]:
        hints = _PRIMARY_HINTS.get(msg_type, ())
        home_match = any(hint in home_l for hint in hints)
        away_match = any(hint in away_l for hint in hints)
        if home_match and not away_match:
            return "home"
        if away_match and not home_match:
            return "away"
        return None

    def _off_def_delta(self, desc: str, player_id: Any) -> Optional[bool]:
        """Use running Off/Def totals to classify rebounds"""
        match = _REBOUND_COUNTS.search(desc)
        if not match or not player_id:
            return None
        try:
            pid = int(player_id)
        except (TypeError, ValueError):
            return None
        off_n, def_n = int(match.group(1)), int(match.group(2))
        prev_off, prev_def = self._reb_counts.get(pid, (0, 0))
        self._reb_counts[pid] = (off_n, def_n)
        if off_n > prev_off:
            return True
        if def_n > prev_def:
            return False
        return None

    def _is_offensive_rebound(self, desc: str, is_home_event: bool, player_id: Any) -> bool:
        """Classify OREB vs DREB (Off:0 Def:1)"""
        count_signal = self._off_def_delta(desc, player_id)

        if self._last_miss_team is not None:
            rebound_team = "home" if is_home_event else "away"
            is_offensive = rebound_team == self._last_miss_team
            self._last_miss_team = None
            return is_offensive

        if "offensive rebound" in desc:
            return True
        if "defensive rebound" in desc:
            return False
        if count_signal is not None:
            return count_signal
        return False