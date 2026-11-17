**free
// New business & underwriting — issue term life after rule checks
ctl-opt dftactgrp(*no) actgrp('LIFE400');

dcl-f NBUWDSP workstn;
dcl-f CUSTOMER usage(*update:*output) keyed;
dcl-f POLICY   usage(*output) keyed;
dcl-ds pol likerec(POLREC:*output);

dcl-s age packed(3:0);
dcl-s uwCls char(1);
dcl-s rc int(10);

exfmt NBUWFMT;
age = %diff(%date(): DOB: *YEARS);

// BR-NBU-01 issue age by plan
if PLANCD = 'T1001' and (age < 18 or age > 60);
  MSG = 'Issue age 18-60 for 10-year term';
  exfmt NBUWFMT;
  *inlr = *on;
  return;
endif;
if PLANCD = 'T2001' and (age < 18 or age > 55);
  MSG = 'Issue age 18-55 for 20-year term';
  exfmt NBUWFMT;
  *inlr = *on;
  return;
endif;
if PLANCD = 'T6501' and (age < 18 or age > 50);
  MSG = 'Issue age 18-50 for term-to-65';
  exfmt NBUWFMT;
  *inlr = *on;
  return;
endif;

// BR-NBU-07 occupation auto-decline
if OCCCLS = 'XX';
  uwCls = 'X';
  MSG = 'Severe occupation — decline';
  exfmt NBUWFMT;
  *inlr = *on;
  return;
endif;

// BR-NBU-08 UW class Preferred/Standard/Table-B
if SMOKER = 'N' and OCCCLS <= '02' and age <= 40;
  uwCls = 'P';
elseif SMOKER = 'Y' or age > 50;
  uwCls = 'B';
else;
  uwCls = 'S';
endif;

// BR-NBU-14 reinsurance referral > 45B SA
if SUMASS > 45000000000;
  MSG = 'Reinsurance referral required';
endif;

pol.POLNO = %char(%timestamp());
pol.CUSTNO = CUSTNO;
pol.PLANCD = PLANCD;
pol.STATUS = 'A';
pol.ISSDTE = %date();
pol.SUMASS = SUMASS;
pol.PREM = PREM;
pol.MODE = MODE;
pol.UWCLS = uwCls;
write POLREC pol;

*inlr = *on;
