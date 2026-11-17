**free
// Nightly claims adjudication — pay approved claims
ctl-opt dftactgrp(*no) actgrp('LIFE400');

exec sql
  update CLAIM
     set STATUS = 'P',
         NETPAY = GROSS - DEDUCT
   where STATUS = 'O'
     and GROSS - DEDUCT >= 0;

*inlr = *on;
