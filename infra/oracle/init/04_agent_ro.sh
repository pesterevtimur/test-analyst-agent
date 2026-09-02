#!/usr/bin/env bash
# Read-only database user for the agent.
#
# The SQL guard rails live in the MCP server, but guard rails are software and
# software has bugs. This user is the layer underneath: even a full bypass of the
# guard rails cannot write, cannot read outside SH, and cannot hold a session
# open forever.

set -euo pipefail

# Reporting replica. The primary has no agent account and no reporting views.
PDB=REPPDB1
AGENT_USER="${ORACLE_APP_USER:-agent_ro}"
AGENT_PASSWORD="${ORACLE_APP_USER_PASSWORD:?ORACLE_APP_USER_PASSWORD must be set}"

sqlplus -s -L "system/${ORACLE_PASSWORD}@localhost/${PDB}" <<SQL
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET FEEDBACK OFF

-- Resource ceiling enforced by the database, not by the caller.
-- CPU_PER_CALL is in centiseconds, CONNECT_TIME and IDLE_TIME in minutes.
DECLARE
   v_exists NUMBER;
BEGIN
   SELECT COUNT(*) INTO v_exists FROM dba_profiles WHERE profile = 'AGENT_RO_PROFILE';
   IF v_exists > 0 THEN EXECUTE IMMEDIATE 'DROP PROFILE agent_ro_profile CASCADE'; END IF;
END;
/

CREATE PROFILE agent_ro_profile LIMIT
   CPU_PER_CALL           3000
   LOGICAL_READS_PER_CALL 5000000
   CONNECT_TIME           60
   IDLE_TIME              15
   SESSIONS_PER_USER      8;

DECLARE
   v_exists NUMBER;
BEGIN
   SELECT COUNT(*) INTO v_exists FROM all_users WHERE username = UPPER('${AGENT_USER}');
   IF v_exists > 0 THEN EXECUTE IMMEDIATE 'DROP USER ${AGENT_USER} CASCADE'; END IF;
END;
/

CREATE USER ${AGENT_USER} IDENTIFIED BY "${AGENT_PASSWORD}"
   DEFAULT TABLESPACE users
   PROFILE agent_ro_profile;

-- CREATE SESSION and nothing else: no CREATE TABLE, no CREATE VIEW,
-- no CREATE PROCEDURE, and no tablespace quota, so nothing can be stored.
GRANT CREATE SESSION TO ${AGENT_USER};

-- SELECT granted table by table rather than through a role, so that the grant
-- list is the allow list and both are answerable with one query against
-- dba_tab_privs.
BEGIN
   FOR o IN (SELECT object_name FROM dba_objects
               WHERE owner = 'SH' AND object_type IN ('TABLE', 'VIEW', 'MATERIALIZED VIEW')) LOOP
      EXECUTE IMMEDIATE 'GRANT SELECT ON sh."' || o.object_name || '" TO ${AGENT_USER}';
   END LOOP;
END;
/
EXIT
SQL

echo "==> ${AGENT_USER} created: SELECT on SH, resource profile, no write privileges"

sqlplus -s -L "system/${ORACLE_PASSWORD}@localhost/${PDB}" <<SQL
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT '==> grants: ' || COUNT(*) || ' SELECT privileges on SH'
  FROM dba_tab_privs WHERE grantee = UPPER('${AGENT_USER}') AND privilege = 'SELECT';
SELECT '==> system privileges: ' || LISTAGG(privilege, ', ')
  FROM dba_sys_privs WHERE grantee = UPPER('${AGENT_USER}');
EXIT
SQL
