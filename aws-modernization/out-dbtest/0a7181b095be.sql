-- =============================================================================
-- Database Migration Engine — Generated DDL
-- Source  : sqlserver
-- Target  : azure-postgresql
-- Generated: 2026-11-20T10:54:36.567032+00:00
-- Tables  : 26
--
-- Review all HIGH / CRITICAL risk columns before executing.
-- Run inside a transaction and test on a non-production instance first.
-- =============================================================================

-- Table: claim

CREATE TABLE IF NOT EXISTS "claim" (
    "id" INTEGER NOT NULL,
    "claimdate" TIMESTAMPTZ NOT NULL,
    "claimamount" NUMERIC(18,2) NOT NULL,
    "claimnumber" TEXT,
    "remarks" TEXT,
    "policyid" INTEGER NOT NULL,
    "statusid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("policyid") REFERENCES "policy" ("id")
);

-- Table: claimstatus

CREATE TABLE IF NOT EXISTS "claimstatus" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: claimattachment

CREATE TABLE IF NOT EXISTS "claimattachment" (
    "id" INTEGER NOT NULL,
    "posteddate" TIMESTAMPTZ NOT NULL,
    "fileurl" TEXT,
    "remarks" TEXT,
    "claimid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("claimid") REFERENCES "claim" ("id")
);

-- Table: client

CREATE TABLE IF NOT EXISTS "client" (
    "id" INTEGER NOT NULL,
    "accountnumber" TEXT,
    "isorganization" BOOLEAN NOT NULL,
    "organizationname" TEXT,
    "lastname" TEXT,
    "firstname" TEXT,
    "address" TEXT,
    "contactnumber" TEXT,
    "email" TEXT,
    "remarks" TEXT,
    PRIMARY KEY ("id")
);

-- Table: offer

CREATE TABLE IF NOT EXISTS "offer" (
    "id" INTEGER NOT NULL,
    "documentname" TEXT,
    "filename" TEXT,
    "fileurl" TEXT,
    "remarks" TEXT,
    "clientid" INTEGER NOT NULL,
    "statusid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("clientid") REFERENCES "client" ("id")
);

-- Table: offerstatus

CREATE TABLE IF NOT EXISTS "offerstatus" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: directory

CREATE TABLE IF NOT EXISTS "directory" (
    "id" INTEGER NOT NULL,
    "companyname" TEXT,
    "contactnumbers" TEXT,
    "contactperson" TEXT,
    "address" TEXT,
    "emailaddress" TEXT,
    "department" TEXT,
    "remarks" TEXT,
    PRIMARY KEY ("id")
);

-- Table: form

CREATE TABLE IF NOT EXISTS "form" (
    "id" INTEGER NOT NULL,
    "remarks" TEXT,
    "filename" TEXT,
    "fileurl" TEXT,
    "insuranceproviderid" INTEGER NOT NULL,
    "documenttypeid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("insuranceproviderid") REFERENCES "insuranceprovider" ("id"),
    FOREIGN KEY ("documenttypeid") REFERENCES "documenttype" ("id")
);

-- Table: documenttype

CREATE TABLE IF NOT EXISTS "documenttype" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: invoice

CREATE TABLE IF NOT EXISTS "invoice" (
    "id" INTEGER NOT NULL,
    "issuedate" TIMESTAMPTZ NOT NULL,
    "paiddate" TIMESTAMPTZ NOT NULL,
    "invoicenumber" TEXT,
    "totalamountdue" NUMERIC(18,2) NOT NULL,
    "endorsementnumber" TEXT,
    "rebate" DOUBLE PRECISION NOT NULL,  -- Verify float precision
    "remarks" TEXT,
    "ornumber" TEXT,
    "hasewt" BOOLEAN NOT NULL,
    "amountpaid" NUMERIC(18,2) NOT NULL,
    "duedate" TIMESTAMPTZ NOT NULL,
    "policyid" INTEGER NOT NULL,
    "statusid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("policyid") REFERENCES "policy" ("id")
);

-- Table: invoicestatus

CREATE TABLE IF NOT EXISTS "invoicestatus" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: particular

CREATE TABLE IF NOT EXISTS "particular" (
    "id" INTEGER NOT NULL,
    "particularamount" NUMERIC(18,2) NOT NULL,
    "remarks" TEXT,
    "invoiceid" INTEGER NOT NULL,
    "particulartypeid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("invoiceid") REFERENCES "invoice" ("id"),
    FOREIGN KEY ("particulartypeid") REFERENCES "particulartype" ("id")
);

-- Table: particulartype

CREATE TABLE IF NOT EXISTS "particulartype" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: activitylog

CREATE TABLE IF NOT EXISTS "activitylog" (
    "id" INTEGER NOT NULL,
    "userid" TEXT,
    "activitylogtype" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "posteddate" TIMESTAMPTZ NOT NULL,
    "message" TEXT,
    "agentid" INTEGER,
    "claimattachmentid" INTEGER,
    "claimid" INTEGER,
    "claimstatusid" INTEGER,
    "clientid" INTEGER,
    "documenttypeid" INTEGER,
    "formid" INTEGER,
    "insuranceproviderid" INTEGER,
    "invoiceid" INTEGER,
    "invoicestatusid" INTEGER,
    "particularid" INTEGER,
    "particulartypeid" INTEGER,
    "policyid" INTEGER,
    "policyattachmentid" INTEGER,
    "policystatusid" INTEGER,
    "policytypeid" INTEGER,
    "riskid" INTEGER,
    "endorsementid" INTEGER,
    "soaid" INTEGER,
    "soastatusid" INTEGER,
    "offerid" INTEGER,
    "offerstatusid" INTEGER,
    "agent" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "claimattachment" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "claim" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "claimstatus" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "client" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "documenttype" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "form" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "insuranceprovider" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "invoice" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "invoicestatus" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "particular" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "particulartype" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "policy" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "policyattachment" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "policystatus" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "policytype" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "risk" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "endorsement" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "soa" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "soastatus" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "offer" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    "offerstatus" TEXT,  -- Unknown source type; defaulted to TEXT — review manually | WARNING HIGH RISK
    PRIMARY KEY ("id"),
    FOREIGN KEY ("agentid") REFERENCES "agent" ("id"),
    FOREIGN KEY ("claimattachmentid") REFERENCES "claimattachment" ("id"),
    FOREIGN KEY ("claimid") REFERENCES "claim" ("id"),
    FOREIGN KEY ("claimstatusid") REFERENCES "claimstatus" ("id"),
    FOREIGN KEY ("clientid") REFERENCES "client" ("id"),
    FOREIGN KEY ("documenttypeid") REFERENCES "documenttype" ("id"),
    FOREIGN KEY ("formid") REFERENCES "form" ("id"),
    FOREIGN KEY ("insuranceproviderid") REFERENCES "insuranceprovider" ("id"),
    FOREIGN KEY ("invoiceid") REFERENCES "invoice" ("id"),
    FOREIGN KEY ("invoicestatusid") REFERENCES "invoicestatus" ("id"),
    FOREIGN KEY ("particularid") REFERENCES "particular" ("id"),
    FOREIGN KEY ("particulartypeid") REFERENCES "particulartype" ("id"),
    FOREIGN KEY ("policyid") REFERENCES "policy" ("id"),
    FOREIGN KEY ("policyattachmentid") REFERENCES "policyattachment" ("id"),
    FOREIGN KEY ("policystatusid") REFERENCES "policystatus" ("id"),
    FOREIGN KEY ("policytypeid") REFERENCES "policytype" ("id"),
    FOREIGN KEY ("riskid") REFERENCES "risk" ("id"),
    FOREIGN KEY ("endorsementid") REFERENCES "endorsement" ("id"),
    FOREIGN KEY ("soaid") REFERENCES "soa" ("id"),
    FOREIGN KEY ("soastatusid") REFERENCES "soastatus" ("id"),
    FOREIGN KEY ("offerid") REFERENCES "offer" ("id"),
    FOREIGN KEY ("offerstatusid") REFERENCES "offerstatus" ("id")
);

-- Table: policy

CREATE TABLE IF NOT EXISTS "policy" (
    "id" INTEGER NOT NULL,
    "suminsured" NUMERIC(18,2) NOT NULL,
    "remarks" TEXT,
    "inceptiondate" TIMESTAMPTZ NOT NULL,
    "dateissued" TIMESTAMPTZ NOT NULL,
    "expirydate" TIMESTAMPTZ NOT NULL,
    "premium" NUMERIC(18,2) NOT NULL,
    "rate" DOUBLE PRECISION NOT NULL,  -- Verify float precision
    "policynumber" TEXT,
    "renewalpolicynumber" TEXT,
    "rebate" DOUBLE PRECISION NOT NULL,  -- Verify float precision
    "commission" NUMERIC(18,2) NOT NULL,
    "address" TEXT,
    "clientid" INTEGER NOT NULL,
    "agentid" INTEGER NOT NULL,
    "insuranceproviderid" INTEGER NOT NULL,
    "policytypeid" INTEGER NOT NULL,
    "statusid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("clientid") REFERENCES "client" ("id"),
    FOREIGN KEY ("agentid") REFERENCES "agent" ("id"),
    FOREIGN KEY ("insuranceproviderid") REFERENCES "insuranceprovider" ("id"),
    FOREIGN KEY ("policytypeid") REFERENCES "policytype" ("id")
);

-- Table: insuranceprovider

CREATE TABLE IF NOT EXISTS "insuranceprovider" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: policytype

CREATE TABLE IF NOT EXISTS "policytype" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: agent

CREATE TABLE IF NOT EXISTS "agent" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: policystatus

CREATE TABLE IF NOT EXISTS "policystatus" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: policyattachment

CREATE TABLE IF NOT EXISTS "policyattachment" (
    "id" INTEGER NOT NULL,
    "posteddate" TIMESTAMPTZ NOT NULL,
    "filename" TEXT,
    "fileurl" TEXT,
    "remarks" TEXT,
    "policyid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("policyid") REFERENCES "policy" ("id")
);

-- Table: risk

CREATE TABLE IF NOT EXISTS "risk" (
    "id" INTEGER NOT NULL,
    "amountinsured" NUMERIC(18,2) NOT NULL,
    "rate" DOUBLE PRECISION NOT NULL,  -- Verify float precision
    "remarks" TEXT,
    "premium" NUMERIC(18,2) NOT NULL,
    "address" TEXT,
    "policyid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("policyid") REFERENCES "policy" ("id")
);

-- Table: endorsement

CREATE TABLE IF NOT EXISTS "endorsement" (
    "id" INTEGER NOT NULL,
    "issuedate" TIMESTAMPTZ NOT NULL,
    "effectivedate" TIMESTAMPTZ NOT NULL,
    "endorsementnumber" TEXT,
    "endorsementamount" NUMERIC(18,2) NOT NULL,
    "totalendorsementamount" NUMERIC(18,2) NOT NULL,
    "remarks" TEXT,
    "mortgagee" TEXT,
    "mt" NUMERIC(18,2) NOT NULL,
    "pt" NUMERIC(18,2) NOT NULL,
    "dst" NUMERIC(18,2) NOT NULL,
    "fst" NUMERIC(18,2) NOT NULL,
    "vat" NUMERIC(18,2) NOT NULL,
    "policyid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("policyid") REFERENCES "policy" ("id")
);

-- Table: defaultrebate

CREATE TABLE IF NOT EXISTS "defaultrebate" (
    "id" INTEGER NOT NULL,
    "rate" DOUBLE PRECISION NOT NULL,  -- Verify float precision
    "insuranceproviderid" INTEGER NOT NULL,
    "policytypeid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("insuranceproviderid") REFERENCES "insuranceprovider" ("id"),
    FOREIGN KEY ("policytypeid") REFERENCES "policytype" ("id")
);

-- Table: soa

CREATE TABLE IF NOT EXISTS "soa" (
    "id" INTEGER NOT NULL,
    "issuedate" TIMESTAMPTZ NOT NULL,
    "startdate" TIMESTAMPTZ NOT NULL,
    "duedate" TIMESTAMPTZ NOT NULL,
    "remarks" TEXT,
    "totalamountdue" NUMERIC(18,2) NOT NULL,
    "clientid" INTEGER NOT NULL,
    "statusid" INTEGER NOT NULL,
    "insuranceproviderid" INTEGER NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("clientid") REFERENCES "client" ("id"),
    FOREIGN KEY ("insuranceproviderid") REFERENCES "insuranceprovider" ("id")
);

-- Table: soastatus

CREATE TABLE IF NOT EXISTS "soastatus" (
    "id" INTEGER NOT NULL,
    "name" TEXT,
    PRIMARY KEY ("id")
);

-- Table: applicationuser

CREATE TABLE IF NOT EXISTS "applicationuser" (
    "firstname" TEXT,
    "lastname" TEXT
);

