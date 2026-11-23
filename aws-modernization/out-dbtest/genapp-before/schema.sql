-- =============================================================================
-- Database Migration Engine — Generated DDL
-- Source  : unknown
-- Target  : azure-postgresql
-- Generated: 2026-11-20T10:51:39.414760+00:00
-- Tables  : 17
--
-- Review all HIGH / CRITICAL risk columns before executing.
-- Run inside a transaction and test on a non-production instance first.
-- =============================================================================

-- Table: customer

CREATE TABLE IF NOT EXISTS "customer" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: policy

CREATE TABLE IF NOT EXISTS "policy" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: motor

CREATE TABLE IF NOT EXISTS "motor" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: house

CREATE TABLE IF NOT EXISTS "house" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ksdscust

CREATE TABLE IF NOT EXISTS "ksdscust" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ksdspoly

CREATE TABLE IF NOT EXISTS "ksdspoly" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: lgpolicy

CREATE TABLE IF NOT EXISTS "lgpolicy" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: customer_secure

CREATE TABLE IF NOT EXISTS "customer_secure" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: lgcmarea

CREATE TABLE IF NOT EXISTS "lgcmarea" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: eibcalen

CREATE TABLE IF NOT EXISTS "eibcalen" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: endowment

CREATE TABLE IF NOT EXISTS "endowment" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: commercial

CREATE TABLE IF NOT EXISTS "commercial" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ws

CREATE TABLE IF NOT EXISTS "ws" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ssmap

CREATE TABLE IF NOT EXISTS "ssmap" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: cust

CREATE TABLE IF NOT EXISTS "cust" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: of

CREATE TABLE IF NOT EXISTS "of" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: endow

CREATE TABLE IF NOT EXISTS "endow" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

