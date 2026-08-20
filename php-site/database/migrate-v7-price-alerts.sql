-- Fiyat dusus alarmlari (v7)
ALTER TABLE listing_favorites
  ADD COLUMN alert_enabled TINYINT(1) NOT NULL DEFAULT 1,
  ADD COLUMN price_currency VARCHAR(8) NULL,
  ADD COLUMN price_amount DECIMAL(14,2) NULL;

CREATE TABLE IF NOT EXISTS listing_price_drop_pending (
  listing_id INT UNSIGNED NOT NULL,
  old_currency VARCHAR(8) NOT NULL,
  old_amount DECIMAL(14,2) NOT NULL,
  new_currency VARCHAR(8) NOT NULL,
  new_amount DECIMAL(14,2) NOT NULL,
  created_at DOUBLE NOT NULL,
  PRIMARY KEY (listing_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
