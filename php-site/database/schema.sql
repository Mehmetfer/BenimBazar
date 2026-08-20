-- CHANGE X — MySQL schema (cPanel, Soyağacı ile aynı hosting modeli)
-- phpMyAdmin veya install.php ile bir kez çalıştırın.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

CREATE TABLE IF NOT EXISTS users (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  username VARCHAR(64) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  role VARCHAR(32) NOT NULL DEFAULT 'user',
  change_score DOUBLE NOT NULL DEFAULT 50,
  user_risk_score DOUBLE NOT NULL DEFAULT 0,
  suspended TINYINT(1) NOT NULL DEFAULT 0,
  email VARCHAR(255) NULL,
  created_at DOUBLE NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_users_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sessions (
  token VARCHAR(128) NOT NULL,
  user_id INT UNSIGNED NOT NULL,
  created_at DOUBLE NOT NULL,
  expires_at DOUBLE NOT NULL,
  PRIMARY KEY (token),
  KEY idx_sessions_user (user_id),
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS trade_listings (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  owner_id INT UNSIGNED NOT NULL,
  title VARCHAR(255) NOT NULL,
  description TEXT NOT NULL,
  category VARCHAR(64) NOT NULL,
  subcategory VARCHAR(64) NOT NULL DEFAULT '',
  `condition` VARCHAR(32) NOT NULL DEFAULT 'good',
  location VARCHAR(128) NOT NULL DEFAULT '',
  mandal_units INT NOT NULL DEFAULT 0,
  accept_categories TEXT NOT NULL,
  wanted_items TEXT NOT NULL,
  min_mandal_units INT NOT NULL DEFAULT 0,
  max_mandal_units INT NOT NULL DEFAULT 0,
  photo_urls TEXT NOT NULL,
  attrs_json TEXT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'PENDING_MODERATION',
  listing_mode VARCHAR(16) NOT NULL DEFAULT 'TRADE',
  price_tl DECIMAL(12,2) NULL,
  price_negotiable TINYINT(1) NOT NULL DEFAULT 0,
  version INT NOT NULL DEFAULT 1,
  moderation_version INT NOT NULL DEFAULT 1,
  moderation_reason VARCHAR(512) NOT NULL DEFAULT '',
  risk_level VARCHAR(16) NULL,
  created_at DOUBLE NOT NULL,
  updated_at DOUBLE NOT NULL,
  view_count INT UNSIGNED NOT NULL DEFAULT 0,
  published_at DOUBLE NULL,
  expires_at DOUBLE NULL,
  sold_at DOUBLE NULL,
  PRIMARY KEY (id),
  KEY idx_listings_owner (owner_id),
  KEY idx_listings_status (status),
  CONSTRAINT fk_listings_owner FOREIGN KEY (owner_id) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS listing_favorites (
  user_id INT UNSIGNED NOT NULL,
  listing_id INT UNSIGNED NOT NULL,
  created_at DOUBLE NOT NULL,
  PRIMARY KEY (user_id, listing_id),
  KEY idx_fav_listing (listing_id),
  CONSTRAINT fk_fav_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_fav_listing FOREIGN KEY (listing_id) REFERENCES trade_listings(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS user_follows (
  follower_id INT UNSIGNED NOT NULL,
  following_id INT UNSIGNED NOT NULL,
  created_at DOUBLE NOT NULL,
  PRIMARY KEY (follower_id, following_id),
  CONSTRAINT fk_follow_follower FOREIGN KEY (follower_id) REFERENCES users(id) ON DELETE CASCADE,
  CONSTRAINT fk_follow_following FOREIGN KEY (following_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS audit_logs (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  actor_id INT UNSIGNED NULL,
  action VARCHAR(64) NOT NULL,
  entity VARCHAR(32) NULL,
  entity_id INT UNSIGNED NULL,
  detail TEXT NOT NULL,
  created_at DOUBLE NOT NULL,
  PRIMARY KEY (id),
  KEY idx_audit_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;
