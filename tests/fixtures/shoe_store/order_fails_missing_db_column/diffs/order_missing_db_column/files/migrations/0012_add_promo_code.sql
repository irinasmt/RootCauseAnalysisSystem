-- Migration 0012: add promo_code column to orders table
-- Run with: psql $DATABASE_URL -f migrations/0012_add_promo_code.sql

ALTER TABLE orders ADD COLUMN promo_code VARCHAR(50);
