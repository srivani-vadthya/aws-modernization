**free
// Claims — death claims, contestability, suicide exclusion, ADB rider
ctl-opt dftactgrp(*no) actgrp('LIFE400');

dcl-f CLMDSP workstn;
dcl-f POLICY usage(*input) keyed;
dcl-f CLAIM  usage(*output) keyed;
dcl-ds pol likerec(POLREC:*input);
dcl-ds clm likerec(CLMREC:*output);

chain POLNO POLICY pol;
if not %found(POLICY);
  MSG = 'Policy not found';
  *inlr = *on;
  return;
endif;

exfmt CLMFMT;

// BR-CLM-01 death-only claim type
if CLMTYP <> 'D';
  MSG = 'Only death claims supported';
  *inlr = *on;
  return;
endif;

// BR-CLM-02 must be Active or Grace
if pol.STATUS <> 'A' and pol.STATUS <> 'G';
  MSG = 'Policy not eligible for claim';
  *inlr = *on;
  return;
endif;

// BR-CLM-03 contestability 2 years
if %diff(DOD: pol.ISSDTE: *YEARS) < 2;
  clm.STATUS = 'I'; // investigate
endif;

// BR-CLM-04 suicide exclusion 2 years
if SUICIDE = 'Y' and %diff(DOD: pol.ISSDTE: *YEARS) < 2;
  MSG = 'Suicide exclusion — deny';
  clm.STATUS = 'R';
endif;

clm.CLMNO = %char(%timestamp());
clm.POLNO = POLNO;
clm.CLMTYP = 'D';
clm.DOD = DOD;
clm.GROSS = pol.SUMASS;
clm.NETPAY = pol.SUMASS - DEDUCT;
write CLMREC clm;
*inlr = *on;
