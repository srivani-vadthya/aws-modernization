-- =============================================================================
-- Database Migration Engine — Generated DDL
-- Source  : unknown
-- Target  : azure-postgresql
-- Generated: 2026-11-20T10:49:36.318456+00:00
-- Tables  : 26
--
-- Review all HIGH / CRITICAL risk columns before executing.
-- Run inside a transaction and test on a non-production instance first.
-- =============================================================================

-- Table: ims.entities.claim

CREATE TABLE IF NOT EXISTS "ims.entities.claim" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.claimstatus

CREATE TABLE IF NOT EXISTS "ims.entities.claimstatus" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.claimattachment

CREATE TABLE IF NOT EXISTS "ims.entities.claimattachment" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.client

CREATE TABLE IF NOT EXISTS "ims.entities.client" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.offer

CREATE TABLE IF NOT EXISTS "ims.entities.offer" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.offerstatus

CREATE TABLE IF NOT EXISTS "ims.entities.offerstatus" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.directory

CREATE TABLE IF NOT EXISTS "ims.entities.directory" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.form

CREATE TABLE IF NOT EXISTS "ims.entities.form" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.documenttype

CREATE TABLE IF NOT EXISTS "ims.entities.documenttype" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.invoice

CREATE TABLE IF NOT EXISTS "ims.entities.invoice" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.invoicestatus

CREATE TABLE IF NOT EXISTS "ims.entities.invoicestatus" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.particular

CREATE TABLE IF NOT EXISTS "ims.entities.particular" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.particulartype

CREATE TABLE IF NOT EXISTS "ims.entities.particulartype" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.activitylog

CREATE TABLE IF NOT EXISTS "ims.entities.activitylog" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.policy

CREATE TABLE IF NOT EXISTS "ims.entities.policy" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.insuranceprovider

CREATE TABLE IF NOT EXISTS "ims.entities.insuranceprovider" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.policytype

CREATE TABLE IF NOT EXISTS "ims.entities.policytype" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.agent

CREATE TABLE IF NOT EXISTS "ims.entities.agent" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.policystatus

CREATE TABLE IF NOT EXISTS "ims.entities.policystatus" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.policyattachment

CREATE TABLE IF NOT EXISTS "ims.entities.policyattachment" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.risk

CREATE TABLE IF NOT EXISTS "ims.entities.risk" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.endorsement

CREATE TABLE IF NOT EXISTS "ims.entities.endorsement" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.defaultrebate

CREATE TABLE IF NOT EXISTS "ims.entities.defaultrebate" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.soa

CREATE TABLE IF NOT EXISTS "ims.entities.soa" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.entities.soastatus

CREATE TABLE IF NOT EXISTS "ims.entities.soastatus" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

-- Table: ims.webmvc.models.applicationuser

CREATE TABLE IF NOT EXISTS "ims.webmvc.models.applicationuser" (
    "id" TEXT NOT NULL  -- Unknown source type; defaulted to TEXT — review manually  -- ⚠ HIGH RISK,
    PRIMARY KEY ("id")
);

