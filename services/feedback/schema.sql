CREATE TABLE IF NOT EXISTS feedback (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 submission_id TEXT NOT NULL UNIQUE,
 description TEXT NOT NULL,
 version TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','in_progress','fixed')),
 fixed_version TEXT NOT NULL DEFAULT '',
 hidden INTEGER NOT NULL DEFAULT 0,
 created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS feedback_public ON feedback(hidden, id DESC);
CREATE INDEX IF NOT EXISTS feedback_status ON feedback(hidden,status,id DESC);
CREATE TABLE IF NOT EXISTS images (
 id TEXT PRIMARY KEY,
 feedback_id INTEGER NOT NULL REFERENCES feedback(id) ON DELETE CASCADE,
 mime TEXT NOT NULL,
 data BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS image_feedback ON images(feedback_id);
CREATE TABLE IF NOT EXISTS storage (id INTEGER PRIMARY KEY CHECK(id=1), bytes INTEGER NOT NULL DEFAULT 0);
INSERT OR IGNORE INTO storage(id,bytes) VALUES(1,0);
CREATE TABLE IF NOT EXISTS rate_limit (key TEXT PRIMARY KEY, bucket INTEGER NOT NULL, count INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS rate_bucket ON rate_limit(bucket);
