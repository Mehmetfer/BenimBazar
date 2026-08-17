-- BenimBazar v5 — kullanici profil alanlari
SET NAMES utf8mb4;

ALTER TABLE users
  ADD COLUMN country VARCHAR(8) NOT NULL DEFAULT 'tr' AFTER role;

ALTER TABLE users
  ADD COLUMN phone VARCHAR(32) NULL AFTER email;

ALTER TABLE users
  ADD COLUMN city VARCHAR(128) NULL AFTER phone;
