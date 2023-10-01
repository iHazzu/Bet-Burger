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
    channel_id BIGINT NOT NULL
);

CREATE TABLE orders (
    user_id	BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    event_slug TEXT NOT NULL,
    created TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);