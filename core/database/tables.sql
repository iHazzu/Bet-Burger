CREATE TABLE messages (
    event_slug	TEXT NOT NULL,
    channel_id	BIGINT NOT NULL,
    message_id	BIGINT NOT NULL
);

CREATE TABLE users (
    user_id	BIGINT NOT NULL PRIMARY KEY,
    username	TEXT NOT NULL,
    active	BOOLEAN DEFAULT True,
    bookies	TEXT,
    channel_id BIGINT NOT NULL,
    last_stake_amount DECIMAL(10, 2) DEFAULT 100
);

CREATE TABLE orders (
    user_id	BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    bet_id TEXT NOT NULL,
    oposition_bet_id TEXT NOT NULL,
    bookmaker_id SMALLINT NOT NULL,
    match_time TIMESTAMP NOT NULL
);