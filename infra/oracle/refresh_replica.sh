#!/usr/bin/env bash
# Refresh the reporting replica from the transactional database.
#
# This is the only direction data moves. Nothing ever flows from the replica
# back into the primary: the agent has no write privilege, no account there,
# and no reason to have either. Analytics reads; the transactional system is
# changed by the business processes that own it.
#
# What DOES flow back is knowledge, not data, and it flows through people:
# a confirmed question and its SQL join the reference set, a metric definition
# an analyst approves joins the semantic layer, a trap someone finds is written
# down as a gotcha. See docs/process.md.
#
# Run from the host:
#   bash infra/oracle/refresh_replica.sh
#
# What it costs: the replica is closed and rebuilt, so anything reading it is
# interrupted for about ten seconds. Proposals that were planned against the
# previous state stop being executable on purpose, see below.

set -euo pipefail

CONTAINER="${CONTAINER:-sap-agent-oracle}"
PRIMARY=FREEPDB1
REPLICA=REPPDB1
DATA=/opt/oracle/oradata/FREE

if [ -f "$(dirname "${BASH_SOURCE[0]}")/../../.env" ]; then
    set -a; . "$(dirname "${BASH_SOURCE[0]}")/../../.env"; set +a
fi

: "${ORACLE_PASSWORD:?ORACLE_PASSWORD must be set}"
: "${ORACLE_APP_USER_PASSWORD:?ORACLE_APP_USER_PASSWORD must be set}"

echo "==> Refreshing ${REPLICA} from ${PRIMARY}"

docker exec "$CONTAINER" bash -c "sqlplus -s / as sysdba <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET FEEDBACK OFF
ALTER PLUGGABLE DATABASE ${REPLICA} CLOSE IMMEDIATE;
DROP PLUGGABLE DATABASE ${REPLICA} INCLUDING DATAFILES;
ALTER PLUGGABLE DATABASE ${PRIMARY} CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE ${PRIMARY} OPEN READ ONLY;
CREATE PLUGGABLE DATABASE ${REPLICA} FROM ${PRIMARY}
  FILE_NAME_CONVERT = ('${DATA}/${PRIMARY}/', '${DATA}/${REPLICA}/');
ALTER PLUGGABLE DATABASE ${PRIMARY} CLOSE IMMEDIATE;
ALTER PLUGGABLE DATABASE ${PRIMARY} OPEN;
ALTER PLUGGABLE DATABASE ${REPLICA} OPEN;
ALTER PLUGGABLE DATABASE ${REPLICA} SAVE STATE;
EXIT
SQL"

# The stamp table lives in the replica, so a fresh clone of the primary does not
# carry it: it has to be created here, not merely updated. Found by running the
# refresh rather than by reading it.
echo "==> Stamping the new moment"
docker exec -e ORACLE_PASSWORD="$ORACLE_PASSWORD" "$CONTAINER" bash -c "sqlplus -s -L sh/\$ORACLE_PASSWORD@localhost/${REPLICA} <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET FEEDBACK OFF
DECLARE
   v_exists NUMBER;
BEGIN
   SELECT COUNT(*) INTO v_exists FROM user_tables WHERE table_name = 'REPLICA_INFO';
   IF v_exists = 0 THEN
      EXECUTE IMMEDIATE 'CREATE TABLE replica_info (
         as_of      TIMESTAMP WITH TIME ZONE NOT NULL,
         source_pdb VARCHAR2(30)  NOT NULL,
         method     VARCHAR2(100) NOT NULL,
         note       VARCHAR2(400))';
   END IF;
END;
/
DELETE FROM replica_info;
INSERT INTO replica_info (as_of, source_pdb, method, note)
VALUES (SYSTIMESTAMP, 'FREEPDB1', 'cold clone of the pluggable database',
        'Обновление реплики. Предложения, подготовленные до этого момента, ' ||
        'больше не выполняются: тот же запрос ответил бы на другой вопрос.');
COMMIT;
EXIT
SQL"

echo "==> Rebuilding the reporting layer and the agent account"
docker cp "$(dirname "${BASH_SOURCE[0]}")/init/03_sap_views.sh" "$CONTAINER:/tmp/03.sh" >/dev/null
docker cp "$(dirname "${BASH_SOURCE[0]}")/init/04_agent_ro.sh" "$CONTAINER:/tmp/04.sh" >/dev/null
docker exec \
    -e ORACLE_PASSWORD="$ORACLE_PASSWORD" \
    -e ORACLE_APP_USER="${ORACLE_APP_USER:-agent_ro}" \
    -e ORACLE_APP_USER_PASSWORD="$ORACLE_APP_USER_PASSWORD" \
    "$CONTAINER" bash -c 'bash /tmp/03.sh && bash /tmp/04.sh'

echo
echo "==> Done. Proposals planned against the previous state will now be refused"
echo "    by execute_query with an explanation, rather than answering a different"
echo "    question with the same SQL."
