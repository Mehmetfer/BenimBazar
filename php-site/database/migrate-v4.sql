-- CHANGE X v4 — goruntulenme, satildi, sureli ilan, bildirimler
SET NAMES utf8mb4;

ALTER TABLE trade_listings
  ADD COLUMN view_count INT UNSIGNED NOT NULL DEFAULT 0 AFTER updated_at,
  ADD COLUMN published_at DOUBLE NULL AFTER view_count,
  ADD COLUMN expires_at DOUBLE NULL AFTER published_at,
  ADD COLUMN sold_at DOUBLE NULL AFTER expires_at;

CREATE TABLE IF NOT EXISTS listing_views (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  listing_id INT UNSIGNED NOT NULL,
  ip_hash VARCHAR(64) NOT NULL,
  session_id VARCHAR(128) NOT NULL DEFAULT '',
  user_agent_hash VARCHAR(64) NOT NULL DEFAULT '',
  viewed_at DOUBLE NOT NULL,
  PRIMARY KEY (id),
  KEY idx_lv_listing_time (listing_id, viewed_at),
  KEY idx_lv_dedup (listing_id, ip_hash, session_id, viewed_at),
  CONSTRAINT fk_lv_listing FOREIGN KEY (listing_id) REFERENCES trade_listings(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_notifications (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id INT UNSIGNED NOT NULL,
  type VARCHAR(64) NOT NULL,
  title VARCHAR(255) NOT NULL,
  body TEXT NOT NULL,
  entity_type VARCHAR(64) NOT NULL DEFAULT '',
  entity_id INT UNSIGNED NOT NULL DEFAULT 0,
  read_at DOUBLE NULL,
  created_at DOUBLE NOT NULL,
  PRIMARY KEY (id),
  KEY idx_un_user_read (user_id, read_at),
  KEY idx_un_user_created (user_id, created_at),
  CONSTRAINT fk_un_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
