-- CHANGE X v3 — ilan ek ozellikleri (arac / detay JSON)
SET NAMES utf8mb4;

ALTER TABLE trade_listings
  ADD COLUMN attrs_json TEXT NULL AFTER photo_urls;
