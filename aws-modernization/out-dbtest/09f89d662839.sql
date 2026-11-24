-- =============================================================================
-- Database Migration Engine — Generated DDL
-- Source  : db2zos
-- Target  : azure-postgresql
-- Generated: 2026-11-20T10:54:33.193021+00:00
-- Tables  : 18
--
-- Review all HIGH / CRITICAL risk columns before executing.
-- Run inside a transaction and test on a non-production instance first.
-- =============================================================================

-- Table: customer

CREATE TABLE IF NOT EXISTS "customer" (
    "customernumber" INTEGER NOT NULL,
    "firstname" VARCHAR(10),  -- Fixed CHAR -> VARCHAR
    "lastname" VARCHAR(20),  -- Fixed CHAR -> VARCHAR
    "dateofbirth" DATE,
    "housename" VARCHAR(20),  -- Fixed CHAR -> VARCHAR
    "housenumber" VARCHAR(4),  -- Fixed CHAR -> VARCHAR
    "postcode" VARCHAR(8),  -- Fixed CHAR -> VARCHAR
    "phonehome" VARCHAR(20),  -- Fixed CHAR -> VARCHAR
    "phonemobile" VARCHAR(20),  -- Fixed CHAR -> VARCHAR
    "emailaddress" VARCHAR(100),  -- Fixed CHAR -> VARCHAR
    PRIMARY KEY ("customernumber")
);

-- Table: policy

CREATE TABLE IF NOT EXISTS "policy" (
    "policynumber" INTEGER NOT NULL,
    "customernumber" INTEGER NOT NULL,
    "issuedate" DATE,
    "expirydate" DATE,
    "policytype" VARCHAR(1),  -- Fixed CHAR -> VARCHAR
    "lastchanged" TIMESTAMPTZ NOT NULL,  -- Add timezone awareness
    "brokerid" INTEGER,
    "brokersreference" VARCHAR(10),  -- Fixed CHAR -> VARCHAR
    "payment" INTEGER,
    "commission" SMALLINT,
    PRIMARY KEY ("policynumber"),
    FOREIGN KEY ("customernumber") REFERENCES "customer" ("customernumber")
);

-- Table: motor

CREATE TABLE IF NOT EXISTS "motor" (
    "policynumber" INTEGER NOT NULL,
    "make" VARCHAR(15),  -- Fixed CHAR -> VARCHAR
    "model" VARCHAR(15),  -- Fixed CHAR -> VARCHAR
    "value" INTEGER,
    "regnumber" VARCHAR(7),  -- Fixed CHAR -> VARCHAR
    "colour" VARCHAR(8),  -- Fixed CHAR -> VARCHAR
    "cc" SMALLINT,
    "yearofmanufacture" DATE,
    "premium" INTEGER,
    "accidents" INTEGER,
    PRIMARY KEY ("policynumber"),
    FOREIGN KEY ("policynumber") REFERENCES "policy" ("policynumber")
);

-- Table: house

CREATE TABLE IF NOT EXISTS "house" (
    "policynumber" INTEGER NOT NULL,
    "propertytype" VARCHAR(15),  -- Fixed CHAR -> VARCHAR
    "bedrooms" SMALLINT,
    "value" INTEGER,
    "housename" VARCHAR(20),  -- Fixed CHAR -> VARCHAR
    "housenumber" VARCHAR(4),  -- Fixed CHAR -> VARCHAR
    "postcode" VARCHAR(8),  -- Fixed CHAR -> VARCHAR
    PRIMARY KEY ("policynumber"),
    FOREIGN KEY ("policynumber") REFERENCES "policy" ("policynumber")
);

-- Table: ksdscust

CREATE TABLE IF NOT EXISTS "ksdscust" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: ksdspoly

CREATE TABLE IF NOT EXISTS "ksdspoly" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: customer_secure

CREATE TABLE IF NOT EXISTS "customer_secure" (
    "customernumber" INTEGER NOT NULL,
    "customerpass" VARCHAR(32),  -- Fixed CHAR -> VARCHAR
    "state_indicator" VARCHAR(1),  -- Fixed CHAR -> VARCHAR
    "pass_changes" INTEGER,
    PRIMARY KEY ("customernumber"),
    FOREIGN KEY ("customernumber") REFERENCES "customer" ("customernumber")
);

-- Table: endowment

CREATE TABLE IF NOT EXISTS "endowment" (
    "policynumber" INTEGER NOT NULL,
    "equities" VARCHAR(1),  -- Fixed CHAR -> VARCHAR
    "withprofits" VARCHAR(1),  -- Fixed CHAR -> VARCHAR
    "managedfund" VARCHAR(1),  -- Fixed CHAR -> VARCHAR
    "fundname" VARCHAR(10),  -- Fixed CHAR -> VARCHAR
    "term" SMALLINT,
    "sumassured" INTEGER,
    "lifeassured" VARCHAR(31),  -- Fixed CHAR -> VARCHAR
    "paddingdata" VARCHAR(32606),
    PRIMARY KEY ("policynumber"),
    FOREIGN KEY ("policynumber") REFERENCES "policy" ("policynumber")
);

-- Table: commercial

CREATE TABLE IF NOT EXISTS "commercial" (
    "policynumber" INTEGER NOT NULL,
    "requestdate" TIMESTAMPTZ,  -- Add timezone awareness
    "startdate" DATE,
    "renewaldate" DATE,
    "address" VARCHAR(255),  -- Fixed CHAR -> VARCHAR
    "zipcode" VARCHAR(8),  -- Fixed CHAR -> VARCHAR
    "latituden" VARCHAR(11),  -- Fixed CHAR -> VARCHAR
    "longitudew" VARCHAR(11),  -- Fixed CHAR -> VARCHAR
    "customer" VARCHAR(255),  -- Fixed CHAR -> VARCHAR
    "propertytype" VARCHAR(255),  -- Fixed CHAR -> VARCHAR
    "fireperil" SMALLINT,
    "firepremium" INTEGER,
    "crimeperil" SMALLINT,
    "crimepremium" INTEGER,
    "floodperil" SMALLINT,
    "floodpremium" INTEGER,
    "weatherperil" SMALLINT,
    "weatherpremium" INTEGER,
    "status" SMALLINT,
    "rejectionreason" VARCHAR(255),  -- Fixed CHAR -> VARCHAR
    PRIMARY KEY ("policynumber"),
    FOREIGN KEY ("policynumber") REFERENCES "policy" ("policynumber")
);

-- Table: claim

CREATE TABLE IF NOT EXISTS "claim" (
    "claimnumber" INTEGER NOT NULL,
    "policynumber" INTEGER NOT NULL,
    "claimdate" DATE,
    "paid" INTEGER,
    "value" INTEGER,
    "cause" VARCHAR(255),  -- Fixed CHAR -> VARCHAR
    "observations" VARCHAR(255),  -- Fixed CHAR -> VARCHAR
    PRIMARY KEY ("claimnumber"),
    FOREIGN KEY ("policynumber") REFERENCES "policy" ("policynumber")
);

-- Table: lgpolicy

CREATE TABLE IF NOT EXISTS "lgpolicy" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: lgcmarea

CREATE TABLE IF NOT EXISTS "lgcmarea" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: eibcalen

CREATE TABLE IF NOT EXISTS "eibcalen" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: ws

CREATE TABLE IF NOT EXISTS "ws" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: ssmap

CREATE TABLE IF NOT EXISTS "ssmap" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: cust

CREATE TABLE IF NOT EXISTS "cust" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: of

CREATE TABLE IF NOT EXISTS "of" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

-- Table: endow

CREATE TABLE IF NOT EXISTS "endow" (
    "id" TEXT NOT NULL,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id")
);

