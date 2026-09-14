from sqlalchemy import Column, Integer, String, Text, UniqueConstraint
from config.database import Base

class PlayByPlayEvent(Base):
    """
    ORM mapping for the play-by-play events to be stored in the database
    """

    __tablename__ = "play_by_play_events"
    __table_args__ = (
        UniqueConstraint("game_id", "eventnum", name="uq_play_by_play_game_eventnum"),
    )

    event_id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    game_id = Column(String(12), nullable=False, index=True)
    eventnum = Column(Integer, nullable=False) 

    eventmsgtype = Column(Integer, nullable=False, index=True)
    eventmsgactiontype = Column(Integer, nullable=False)
    period = Column(Integer, nullable=False)
    pctimestring = Column(String(10), nullable=False)

    homedescription = Column(Text, nullable=True)
    neutraldescription = Column(Text, nullable=True)
    visitordescription = Column(Text, nullable=True)
    score = Column(String(20), nullable=True)
    scoremargin = Column(String(10), nullable=True)

    player1_id = Column(Integer, nullable=True)
    player2_id = Column(Integer, nullable=True)
    player3_id = Column(Integer, nullable=True)

