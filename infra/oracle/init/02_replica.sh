#!/usr/bin/env bash
# Create the reporting replica the agent works on.
#
# Analytics must not run against the transactional database. That is not a
# preference: a report that scans a fact table competes for the same buffers and
# the same CPU as the transactions that pay for the system, and the first heavy
# question from an analyst becomes an incident for the business.
#
# What this models truthfully:
#   * the boundary. AGENT_RO exists only in the replica. There is no account for
#     the agent on the primary, so there is no path to it, not even a mistaken one.
#   * staleness. The replica is a point-in-time copy, so answers carry an "as of"
#     moment, exactly as they must against a real standby that lags.
#
# What this does NOT model, said plainly rather than implied:
#   * redo apply. A production replica is an Active Data Guard standby kept
#     current by shipping redo. That needs Enterprise Edition, and this is Free.
#     Here the copy is made once, by cloning the pluggable database.
#   * a separate machine. Both pluggable databases live in one instance and share
#     its memory, so this separates access, not load.
# Both gaps are recorded in docs/not-done.md.

set -euo pipefail

PRIMARY=FREEPDB1
REPLICA=REPPDB1
DATA=/opt/oracle/oradata/FREE

echo "==> Cloning ${PRIMARY} into ${REPLICA}"

sqlplus -s / as sysdba <<SQL
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET FEEDBACK OFF

-- A cold clone: close the source, copy it, reopen both. A hot clone would need
-- ARCHIVELOG mode, which costs disk and buys nothing at install time.
ALTER PLUGGABLE DATABASE ${PRIMARY} CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE ${PRIMARY} OPEN READ ONLY;

CREATE PLUGGABLE DATABASE ${REPLICA} FROM ${PRIMARY}
  FILE_NAME_CONVERT = ('${DATA}/${PRIMARY}/', '${DATA}/${REPLICA}/');

ALTER PLUGGABLE DATABASE ${PRIMARY} CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE ${PRIMARY} OPEN;
ALTER PLUGGABLE DATABASE ${REPLICA} OPEN;
-- Remember the open state so a container restart brings the replica back up.
ALTER PLUGGABLE DATABASE ${REPLICA} SAVE STATE;
EXIT
SQL

echo "==> Recording the moment the replica was taken"

sqlplus -s -L "sh/${SH_PASSWORD:-$ORACLE_PASSWORD}@localhost/${REPLICA}" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET FEEDBACK OFF

-- Every answer built on this replica has to say what moment it describes.
-- Without it, "revenue for the quarter" silently means "revenue as known at
-- some unstated time", and two answers taken days apart disagree for reasons
-- nobody can reconstruct.
CREATE TABLE replica_info (
   as_of        TIMESTAMP WITH TIME ZONE NOT NULL,
   source_pdb   VARCHAR2(30)  NOT NULL,
   method       VARCHAR2(100) NOT NULL,
   note         VARCHAR2(400)
);

INSERT INTO replica_info (as_of, source_pdb, method, note)
VALUES (SYSTIMESTAMP, 'FREEPDB1', 'cold clone of the pluggable database',
        'Копия сделана один раз при установке. Это не поток изменений: ' ||
        'в промышленной эксплуатации здесь стоял бы резервный экземпляр, ' ||
        'который догоняет основной по журналу.');
COMMIT;
EXIT
SQL

echo "==> Dropping the reporting views from the primary if the clone inherited any"
sqlplus -s -L "sh/${SH_PASSWORD:-$ORACLE_PASSWORD}@localhost/${PRIMARY}" <<'SQL'
SET FEEDBACK OFF
BEGIN
   FOR v IN (SELECT view_name FROM user_views) LOOP
      EXECUTE IMMEDIATE 'DROP VIEW ' || v.view_name;
   END LOOP;
END;
/
EXIT
SQL

echo "==> Replica ${REPLICA} is open. The agent will be created here only."
