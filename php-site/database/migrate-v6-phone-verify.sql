-- BenimBazar v6 — telefon dogrulama
SET NAMES utf8mb4;

ALTER TABLE users
  ADD COLUMN phone_verified_at DOUBLE NULL DEFAULT NULL AFTER phone;

CREATE TABLE IF NOT EXISTS phone_verifications (
  id INT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id INT UNSIGNED NOT NULL,
  phone VARCHAR(32) NOT NULL,
  phone_key VARCHAR(16) NOT NULL,
  code_hash VARCHAR(255) NOT NULL,
  channel VARCHAR(16) NOT NULL DEFAULT 'debug',
  attempts TINYINT UNSIGNED NOT NULL DEFAULT 0,
  sent_at DOUBLE NOT NULL,
  expires_at DOUBLE NOT NULL,
  verified_at DOUBLE NULL,
  PRIMARY KEY (id),
  KEY idx_pv_user_sent (user_id, sent_at),
  KEY idx_pv_phone_key (phone_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
