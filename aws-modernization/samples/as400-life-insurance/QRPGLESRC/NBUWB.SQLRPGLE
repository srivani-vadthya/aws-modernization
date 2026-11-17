**free
// Nightly new-business batch — bind proposals that cleared UW
ctl-opt dftactgrp(*no) actgrp('LIFE400');
dcl-f POLICY usage(*update) keyed;

exec sql
  update POLICY
     set STATUS = 'A'
   where STATUS = 'P'
     and UWCLS in ('P','S','B');

*inlr = *on;
