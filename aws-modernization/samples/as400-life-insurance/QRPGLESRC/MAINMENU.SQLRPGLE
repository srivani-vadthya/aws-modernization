**free
// LIFE400 main menu — routes to NBUW / servicing / claims
ctl-opt dftactgrp(*no) actgrp('LIFE400');

dcl-f MAINMENU workstn;

dcl-s option char(2);

dow option <> '90';
  exfmt MENU;
  select;
    when option = '1';
      callp nbuwMnt();
    when option = '2';
      callp svcMnt();
    when option = '3';
      callp clmMnt();
  endsl;
enddo;

*inlr = *on;

dcl-proc nbuwMnt;
  dcl-pr pgm extpgm('NBUWMNT') end-pr;
  pgm();
end-proc;

dcl-proc svcMnt;
  dcl-pr pgm extpgm('SVCMNT') end-pr;
  pgm();
end-proc;

dcl-proc clmMnt;
  dcl-pr pgm extpgm('CLMMNT') end-pr;
  pgm();
end-proc;
