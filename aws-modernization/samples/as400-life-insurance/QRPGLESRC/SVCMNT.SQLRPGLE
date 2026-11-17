**free
// Policy servicing — lapse, grace, reinstatement, SA change
ctl-opt dftactgrp(*no) actgrp('LIFE400');

dcl-f SVCDSP workstn;
dcl-f POLICY usage(*update) keyed;
dcl-ds pol likerec(POLREC:*update);

chain POLNO POLICY pol;
if not %found(POLICY);
  MSG = 'Policy not found';
  exfmt SVCFMT;
  *inlr = *on;
  return;
endif;

exfmt SVCFMT;

select;
  // BR-SVC-01 grace after 30 days overdue
  when ACTION = 'GRACE';
    if pol.STATUS = 'A';
      pol.STATUS = 'G';
    endif;
  // BR-SVC-02 lapse after grace expires
  when ACTION = 'LAPSE';
    if pol.STATUS = 'A' or pol.STATUS = 'G';
      pol.STATUS = 'L';
    endif;
  // BR-SVC-03 reinstatement within 730 days
  when ACTION = 'REIN';
    if pol.STATUS = 'L';
      pol.STATUS = 'A';
    endif;
  // BR-SVC-05 SA increase >25% requires UW
  when ACTION = 'SAINC';
    if NEWSUM > pol.SUMASS * 1.25;
      MSG = 'Underwriting required for SA increase';
    else;
      pol.SUMASS = NEWSUM;
    endif;
endsl;

update POLREC pol;
*inlr = *on;
