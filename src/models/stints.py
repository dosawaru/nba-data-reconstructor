from sqlalchemy import Boolean, Column, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB

from config.database import Base


class PbpStint(Base):
    """Team-centric stint rows derived from play-by-play (two rows per game stint)."""

    __tablename__ = "pbp_stints"

    stint_id = Column(String(40), primary_key=True)
    game_id = Column(String(12), nullable=False, index=True)
    season = Column(String(10), nullable=False, index=True)
    team_id = Column(Integer, nullable=False, index=True)
    opp_team_id = Column(Integer, nullable=False)
    lineup_player_ids = Column(JSONB, nullable=False)
    opp_lineup_player_ids = Column(JSONB, nullable=False)
    duration_seconds = Column(Float, nullable=False)
    possessions = Column(Float, nullable=False)
    points_scored = Column(Integer, nullable=False)
    points_allowed = Column(Integer, nullable=False)
    garbage_time_flag = Column(Boolean, nullable=False, default=False)
