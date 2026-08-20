-- CHANGE X v2 — Google OAuth + mesajlar (mevcut DB uzerine)
SET NAMES utf8mb4;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS google_id VARCHAR(128) NULL AFTER email,
  ADD COLUMN IF NOT EXISTS avatar_url VARCHAR(512) NULL AFTER google_id;

-- MySQL 8.0.12 alti IF NOT EXISTS desteklemezse kurulum.php tek tek dener
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_google_id ON users (google_id);

CREATE TABLE IF NOT EXISTS message_conversations (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  listing_id INT UNSIGNED NULL,
  created_at DOUBLE NOT NULL,
  updated_at DOUBLE NOT NULL,
  PRIMARY KEY (id),
  KEY idx_conv_listing (listing_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS message_participants (
  conversation_id INT UNSIGNED NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  joined_at DOUBLE NOT NULL,
  PRIMARY KEY (conversation_id, user_id),
  CONSTRAINT fk_mp_conv FOREIGN KEY (conversation_id) REFERENCES message_conversations(id) ON DELETE CASCADE,
  CONSTRAINT fk_mp_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS messages (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  conversation_id INT UNSIGNED NOT NULL,
  sender_id INT UNSIGNED NOT NULL,
  body TEXT NOT NULL,
  created_at DOUBLE NOT NULL,
  read_at DOUBLE NULL,
  PRIMARY KEY (id),
  KEY idx_msg_conv (conversation_id),
  CONSTRAINT fk_msg_conv FOREIGN KEY (conversation_id) REFERENCES message_conversations(id) ON DELETE CASCADE,
  CONSTRAINT fk_msg_sender FOREIGN KEY (sender_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
