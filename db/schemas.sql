CREATE TABLE IF NOT EXISTS play_by_play_events (
    event_id SERIAL PRIMARY KEY,
    game_id VARCHAR(12) NOT NULL,
    eventnum INTEGER NOT NULL,
    eventmsgtype INTEGER NOT NULL,
    eventmsgactiontype INTEGER NOT NULL,
    period INTEGER NOT NULL,
    pctimestring VARCHAR(10) NOT NULL,
    homedescription TEXT,
    neutraldescription TEXT,
    visitordescription TEXT,
    score VARCHAR(20),
    scoremargin VARCHAR(10),
    player1_id INTEGER,
    player2_id INTEGER,
    player3_id INTEGER
);

CREATE INDEX IF NOT EXISTS ix_play_by_play_events_game_id ON play_by_play_events (game_id);
CREATE INDEX IF NOT EXISTS ix_play_by_play_events_eventmsgtype ON play_by_play_events (eventmsgtype);