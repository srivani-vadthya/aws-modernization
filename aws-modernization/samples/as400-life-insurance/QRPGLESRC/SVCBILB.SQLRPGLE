**free
// Nightly billing — advance next cycle, move overdue to grace
ctl-opt dftactgrp(*no) actgrp('LIFE400');

exec sql
  update POLICY
     set STATUS = 'G'
   where STATUS = 'A'
     and NEXTCY < CURRENT_DATE - 30 DAYS;

exec sql
  update POLICY
     set NEXTCY = CASE MODE
                    WHEN 'M' THEN NEXTCY + 1 MONTH
                    WHEN 'Q' THEN NEXTCY + 3 MONTHS
                    WHEN 'S' THEN NEXTCY + 6 MONTHS
                    ELSE NEXTCY + 1 YEAR
                  END
   where STATUS = 'A';

*inlr = *on;
