# Game Metadata
GAME_ID = "0022400002"



import logging
from typing import Any, Dict, List, Optional, Set, Tuple

# logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def _is_player_id(player_id: Optional[int]) -> bool:
    """Check if the player ID is valid, set threshold to 1610600000 to avoid NBA team IDs"""
    return player_id is not None and 0 < player_id < 1610600000

class DeterministicStateReconstructor:
    """
    Reconstruct the state of the game from the play-by-play events with exact on-court 5-man lineup
    Monitors substitution node removals (EVENTMSGTYPE == 8) to maintain deterministic state.
    """

    def __init__(self, home_starters: List[int], away_starters: List[int]):
        self.home_lineup_set: Set[int] = set(home_starters)
        self.away_lineup_set: Set[int] = set(away_starters)
        self._home_successor: Dict[int, int] = {}
        self._away_successor: Dict[int, int] = {}
        self._period_warmup = False
        self._home_seen: Set[int] = set()
        self._away_seen: Set[int] = set()
        self._warmup_buffer: List[Dict[str, Any]] = []
        self._valid_lineup_invariant()

    def _valid_lineup_invariant(self) -> None:
        """Validate that the home and away lineup sets have exactly 5 players."""
        if len(self.home_lineup_set) != 5:
            raise ValueError(f"Home lineup set has {len(self.home_lineup_set)} players. Expected 5.")
        if len(self.away_lineup_set) != 5:
            raise ValueError(f"Away lineup set has {len(self.away_lineup_set)} players. Expected 5.")

    def _snapshot(self, event: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = dict(event)
        snapshot["home_lineup"] = sorted(self.home_lineup_set)
        snapshot["away_lineup"] = sorted(self.away_lineup_set)
        return snapshot

    def _begin_period_warmup(self) -> None:
        """Find the first five distinct players in a new period."""
        self._period_warmup = True
        self._home_seen = set()
        self._away_seen = set()
        self._warmup_buffer = []
        self._home_successor = {}
        self._away_successor = {}

    def _observe_players(self, event: Dict[str, Any]) -> None:
        """Record the first five distinct players in a new period."""
        player_id = event.get("player1_id")
        if not _is_player_id(player_id):
            return
        if event.get("homedescription") and len(self._home_seen) < 5:
            self._home_seen.add(player_id)
        elif event.get("visitordescription") and len(self._away_seen) < 5:
            self._away_seen.add(player_id)

    def _sub_team(self, event: Dict[str, Any], out_id: int, in_id: int) -> Optional[str]:
        if event.get("homedescription"):
            return "home"
        if event.get("visitordescription"):
            return "away"
        if out_id in self.home_lineup_set or in_id in self.home_lineup_set:
            return "home"
        if out_id in self.away_lineup_set or in_id in self.away_lineup_set:
            return "away"
        return None

    @staticmethod
    def _resolve_out(out_id: int, lineup: Set[int], successor: Dict[int, int]) -> Optional[int]:
        """Map a possibly-stale OUT id to whoever currently occupies that slot."""
        if out_id in lineup:
            return out_id
        seen: Set[int] = set()
        current = out_id
        while current in successor and current not in seen:
            seen.add(current)
            current = successor[current]
            if current in lineup:
                return current
        return None

    def _apply_team_pairs(
        self,
        lineup: Set[int],
        successor: Dict[int, int],
        pairs: List[Tuple[int, int]],
        team_label: str,
    ) -> Set[int]:
        if not pairs:
            return lineup

        unresolved_outs: Set[int] = set()
        resolved_outs: Set[int] = set()
        ins: Set[int] = set()
        for out_id, in_id in pairs:
            logging.info(f"({team_label}) Sub Out {out_id} -> Sub In {in_id}")
            resolved = self._resolve_out(out_id, lineup, successor)
            if resolved is not None:
                resolved_outs.add(resolved)
            else:
                unresolved_outs.add(out_id)
                logging.warning(
                    f"({team_label}) Could not resolve OUT {out_id} onto the current lineup"
                )
            ins.add(in_id)

        candidate = (lineup - resolved_outs) | ins
        if len(candidate) == 5:
            for out_id, in_id in pairs:
                successor[out_id] = in_id
            return candidate

        on_court_outs = resolved_outs & lineup
        off_court_ins = ins - lineup
        filtered = (lineup - on_court_outs) | off_court_ins
        if len(filtered) == 5:
            logging.info(
                f"({team_label}) Applied filtered sub batch "
                f"outs={sorted(on_court_outs)} ins={sorted(off_court_ins)}"
            )
            for out_id, in_id in pairs:
                successor[out_id] = in_id
            return filtered

        working = set(lineup)
        for out_id, in_id in pairs:
            resolved = self._resolve_out(out_id, working, successor)
            successor[out_id] = in_id
            if resolved is None:
                continue
            if resolved != in_id:
                successor[resolved] = in_id
            if resolved in working and in_id not in working:
                working.remove(resolved)
                working.add(in_id)
            elif resolved in working and in_id in working and resolved != in_id:
                logging.warning(
                    f"({team_label}) Skipping conflicted sub {out_id}->{in_id}; "
                    "both players already in lineup reconstruction"
                )

        if len(working) != 5:
            raise ValueError(
                f"{team_label} lineup would have {len(working)} players after subs "
                f"(outs={sorted(resolved_outs)}, ins={sorted(ins)}, "
                f"before={sorted(lineup)}). Expected 5."
            )
        return working

    def _apply_sub_batch(self, batch: List[Dict[str, Any]]) -> None:
        home_pairs: List[Tuple[int, int]] = []
        away_pairs: List[Tuple[int, int]] = []

        for event in batch:
            out_id = event.get("player1_id")
            in_id = event.get("player2_id")
            if not _is_player_id(out_id) or not _is_player_id(in_id):
                logging.warning(
                    f"Skipping incomplete substitution eventnum={event.get('eventnum')} "
                    f"out={out_id} in={in_id}"
                )
                continue

            team = self._sub_team(event, out_id, in_id)
            if team == "home":
                home_pairs.append((out_id, in_id))
            elif team == "away":
                away_pairs.append((out_id, in_id))
            else:
                logging.warning(
                    f"Unknown team for substitution eventnum={event.get('eventnum')} "
                    f"out={out_id} in={in_id}. Skipping."
                )

        self.home_lineup_set = self._apply_team_pairs(
            self.home_lineup_set, self._home_successor, home_pairs, "HOME"
        )
        self.away_lineup_set = self._apply_team_pairs(
            self.away_lineup_set, self._away_successor, away_pairs, "AWAY"
        )

    def _flush_warmup_buffer(self) -> List[Dict[str, Any]]:
        """Lock period-start lineups from pre-sub appearances and annotate the buffer."""
        self.home_lineup_set = set(self._home_seen)
        self.away_lineup_set = set(self._away_seen)
        self._home_successor = {}
        self._away_successor = {}
        self._valid_lineup_invariant()
        logging.info(
            f"Period lineups locked: home={sorted(self.home_lineup_set)} "
            f"away={sorted(self.away_lineup_set)}"
        )

        annotated = [self._snapshot(event) for event in self._warmup_buffer]
        self._warmup_buffer = []
        self._period_warmup = False
        return annotated

    def _abandon_period_warmup(self) -> List[Dict[str, Any]]:
        """Keep the previous period's ending lineups when rediscovery is incomplete."""
        logging.warning(
            f"Period rediscovery incomplete "
            f"(home_seen={len(self._home_seen)}, away_seen={len(self._away_seen)}); "
            "retaining prior lineups"
        )
        annotated = [self._snapshot(event) for event in self._warmup_buffer]
        self._warmup_buffer = []
        self._period_warmup = False
        self._home_seen = set()
        self._away_seen = set()
        return annotated

    def process_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        annotated_events: List[Dict[str, Any]] = []
        i = 0
        n = len(events)

        while i < n:
            event = events[i]

            # Period start → rediscover who actually opens the period
            if event.get("eventmsgtype") == 12:
                if self._period_warmup and self._warmup_buffer:
                    if len(self._home_seen) == 5 and len(self._away_seen) == 5:
                        annotated_events.extend(self._flush_warmup_buffer())
                    else:
                        annotated_events.extend(self._abandon_period_warmup())
                self._begin_period_warmup()
                self._warmup_buffer.append(event)
                i += 1
                continue

            if self._period_warmup:
                # Substitutions before both fives are known mean appearance-based
                # discovery would mix pre/post-sub players. Keep prior lineups.
                if event.get("eventmsgtype") == 8:
                    if len(self._home_seen) == 5 and len(self._away_seen) == 5:
                        annotated_events.extend(self._flush_warmup_buffer())
                    else:
                        annotated_events.extend(self._abandon_period_warmup())
                    # Re-process this substitution in normal mode.
                    continue

                self._observe_players(event)
                self._warmup_buffer.append(event)
                if len(self._home_seen) == 5 and len(self._away_seen) == 5:
                    annotated_events.extend(self._flush_warmup_buffer())
                i += 1
                continue

            if event.get("eventmsgtype") == 8:
                period = event.get("period")
                clock = event.get("pctimestring")
                batch = [event]
                j = i + 1
                while (
                    j < n
                    and events[j].get("eventmsgtype") == 8
                    and events[j].get("period") == period
                    and events[j].get("pctimestring") == clock
                ):
                    batch.append(events[j])
                    j += 1

                self._apply_sub_batch(batch)
                self._valid_lineup_invariant()
                for sub_event in batch:
                    annotated_events.append(self._snapshot(sub_event))
                i = j
                continue

            annotated_events.append(self._snapshot(event))
            i += 1

        if self._period_warmup and self._warmup_buffer:
            if len(self._home_seen) == 5 and len(self._away_seen) == 5:
                annotated_events.extend(self._flush_warmup_buffer())
            else:
                annotated_events.extend(self._abandon_period_warmup())

        return annotated_events


if __name__ == "__main__":
    pass