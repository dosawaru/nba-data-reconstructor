# Game Metadata
GAME_ID = "0022400002"

# Los Angeles Lakers (Home) 
LAL_STARTERS = [
    1626156,  
    1630559,  
    1629060,  
    2544,     
    203076    
]

# Minnesota Timberwolves (Away) 
MIN_STARTERS = [
    201144,  
    1630162,  
    1630183,  
    203944,   
    203497    
]

import logging
from typing import Any, List, Dict, Tuple, Set

# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

class DeterministicStateReconstructor:
    """
    Reconstruct the state of the game from the play-by-play events with exact on-court 5-man lineup
    Monitors substitution node removals (EVENTMSGTYPE == 8) to maintain deterministic state.
    """

    def __init__(self, home_starters: List[int], visitor_starters: List[int]):
        self.home_lineup_set: Set[int] = set(home_starters)
        self.visitor_lineup_set: Set[int] = set(visitor_starters)
        self._valid_lineup_invariant()

    def _valid_lineup_invariant(self) -> None:
        """Ensure the lineup sets are valid and consistent with 5 nodes existing on the court at any given time."""

        if len(self.home_lineup_set) != 5:
            raise ValueError(f"Home lineup set has {len(self.home_lineup_set)} players. Expected 5.")
        if len(self.visitor_lineup_set) != 5:
            raise ValueError(f"Visitor lineup set has {len(self.visitor_lineup_set)} players. Expected 5.")

    def process_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Track substitution node removals (EVENTMSGTYPE == 8) to maintain a 10-node l
        lineup invariant at any given time.
        """

        annotated_events: List[Dict[str, Any]] = []

        for event in events:
            event_msg_type = event.get("eventmsgtype")
            p1_id = event.get("player1_id")
            p2_id = event.get("player2_id")

            # Substitution node removal
            if event_msg_type == 8 and p1_id and p2_id:
                if p1_id in self.home_lineup_set:
                    self.home_lineup_set.remove(p1_id)
                    self.home_lineup_set.add(p2_id)
                    logging.info(f"(HOME) Sub Out {p1_id} -> Sub In {p2_id}")
                elif p1_id in self.visitor_lineup_set:
                    self.visitor_lineup_set.remove(p1_id)
                    self.visitor_lineup_set.add(p2_id)
                    logging.info(f"(VISITOR) Sub Out {p1_id} -> Sub In {p2_id}")
                else:
                    logging.warning(f"Unknown player {p1_id} in substitution event. Skipping.")

            # assert that the lineup sets are valid and consistent with 5 nodes existing 
            self._valid_lineup_invariant()
    
            event_snapshot = dict(event)
            event_snapshot["home_lineup"] = sorted(list(self.home_lineup_set))
            event_snapshot["visitor_lineup"] = sorted(list(self.visitor_lineup_set))
            annotated_events.append(event_snapshot)

        return annotated_events

if __name__ == "__main__":
    logging.info(f"Processing game {GAME_ID}")
    reconstructor = DeterministicStateReconstructor(
        home_starters=LAL_STARTERS,
        visitor_starters=MIN_STARTERS
    )
    print(f"Initial State Validated: LAL={reconstructor.home_lineup_set}, MIN={reconstructor.visitor_lineup_set}")