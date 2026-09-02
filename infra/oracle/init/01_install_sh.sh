#!/usr/bin/env bash
# Install the Sales History sample schema.
#
# The upstream installer (sh_install.sql) cannot be used as is: its data load
# uses SQLcl's `LOAD` command, and this image ships sqlplus and sqlldr but not
# SQLcl. So the DDL runs through sqlplus and the six CSV files go through
# SQL*Loader, which is faster anyway.
#
# Runs once, on first container start, from /container-entrypoint-initdb.d.

set -euo pipefail

SRC=/opt/sh
PDB=FREEPDB1
SH_PASSWORD="${SH_PASSWORD:-$ORACLE_PASSWORD}"
WORK=/tmp/sh_install

if [ ! -f "$SRC/sh_create.sql" ]; then
    echo "ERROR: $SRC/sh_create.sql missing. Run infra/oracle/prepare.sh first." >&2
    exit 1
fi

# sqlldr writes control, log and bad files next to the data, and $SRC is
# mounted read-only, so work on a copy.
rm -rf "$WORK"; mkdir -p "$WORK"
cp "$SRC"/*.csv "$SRC"/*.sql "$WORK"/
cd "$WORK"

CONN="system/${ORACLE_PASSWORD}@localhost/${PDB}"

echo "==> Creating SH user"
sqlplus -s -L "$CONN" <<SQL
WHENEVER SQLERROR EXIT SQL.SQLCODE
DECLARE
   v_exists NUMBER;
BEGIN
   SELECT COUNT(*) INTO v_exists FROM all_users WHERE username = 'SH';
   IF v_exists > 0 THEN EXECUTE IMMEDIATE 'DROP USER SH CASCADE'; END IF;
END;
/
CREATE USER sh IDENTIFIED BY "${SH_PASSWORD}"
  DEFAULT TABLESPACE users
  QUOTA UNLIMITED ON users;
-- Exactly the privileges the upstream scripts need, no more. The list was
-- derived by enumerating every CREATE and ALTER in sh_create.sql and
-- sh_populate.sql: 9 tables, 1 view, 2 materialized views, 5 dimensions,
-- 18 indexes (covered by CREATE TABLE on the own schema) and one ALTER SESSION.
GRANT CREATE SESSION, ALTER SESSION, CREATE TABLE, CREATE VIEW,
      CREATE MATERIALIZED VIEW, CREATE DIMENSION TO sh;
EXIT
SQL

echo "==> Creating SH tables"
sqlplus -s -L "sh/${SH_PASSWORD}@localhost/${PDB}" <<SQL
WHENEVER SQLERROR EXIT SQL.SQLCODE
@sh_create.sql
EXIT
SQL

# sh_populate.sql needs two edits before sqlplus can run it.
#
# 1. It mixes plain INSERT blocks (channels, countries, products) with SQLcl
#    LOAD directives. Strip the LOAD lines and the SQLcl-only SET LOAD line;
#    the constraint enable/disable statements around them must stay.
# 2. It builds a full-text index on SUPPLEMENTARY_DEMOGRAPHICS.COMMENTS with
#    INDEXTYPE ctxsys.context. The slim image ships without Oracle Text, so that
#    statement fails with ORA-29833. The index is dropped rather than switching
#    to the larger image: nothing in this project does full-text search, and the
#    table is not one of the ten the agent works with. Deviation recorded in
#    docs/not-done.md.
sed -e '/^LOAD /d' \
    -e '/^SET LOAD /d' \
    -e '/^CREATE INDEX sup_text_idx/,/;[[:space:]]*$/d' \
    sh_populate.sql > sh_populate_no_load.sql

echo "==> Loading reference tables and toggling constraints"
sqlplus -s -L "sh/${SH_PASSWORD}@localhost/${PDB}" <<SQL
WHENEVER SQLERROR EXIT SQL.SQLCODE
@sh_populate_no_load.sql
EXIT
SQL

# One control file per CSV, columns taken from the header row. Every field is
# read as a character string and converted by Oracle using NLS_DATE_FORMAT,
# which keeps this generic instead of hard-coding each table's column types.
#
# COLUMNARRAYROWS is lowered from the default 5000 on purpose. Direct path
# allocates columns * width * rows up front, and TIMES has 38 columns: at
# CHAR(4000) and 5000 rows that is 760 MB, which the container's memory limit
# kills. At 200 rows it is about 30 MB, and the load is no slower in practice.
export NLS_DATE_FORMAT=YYYY-MM-DD
export NLS_LANG=AMERICAN_AMERICA.AL32UTF8

load_csv() {
    local table="$1" csv="$2"
    local cols
    cols="$(head -1 "$csv" | tr -d '"\r' | tr ',' '\n' \
             | sed 's/^[[:space:]]*/  /; s/[[:space:]]*$/ CHAR(4000)/' \
             | sed '$!s/$/,/')"
    cat > "${table}.ctl" <<CTL
OPTIONS (SKIP=1, ERRORS=0, DIRECT=TRUE, COLUMNARRAYROWS=200, SILENT=(HEADER,FEEDBACK))
LOAD DATA
INFILE '${csv}'
APPEND
INTO TABLE ${table}
FIELDS TERMINATED BY ',' OPTIONALLY ENCLOSED BY '"'
TRAILING NULLCOLS
(
${cols}
)
CTL
    echo "==> Loading ${table}"
    if ! sqlldr "sh/${SH_PASSWORD}@localhost/${PDB}" \
            control="${table}.ctl" log="${table}.log" bad="${table}.bad"; then
        echo "==> ERROR: sqlldr failed for ${table}, tail of ${table}.log:" >&2
        tail -30 "${table}.log" >&2 || true
        return 1
    fi
}

load_csv costs costs.csv
load_csv customers customers.csv
load_csv promotions promotions.csv
load_csv times times.csv
load_csv supplementary_demographics supplementary_demographics.csv
load_csv sales sales.csv

echo "==> Row counts"
sqlplus -s -L "sh/${SH_PASSWORD}@localhost/${PDB}" <<'SQL'
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT 'channels    ' || COUNT(*) FROM channels
UNION ALL SELECT 'countries   ' || COUNT(*) FROM countries
UNION ALL SELECT 'products    ' || COUNT(*) FROM products
UNION ALL SELECT 'promotions  ' || COUNT(*) FROM promotions
UNION ALL SELECT 'times       ' || COUNT(*) FROM times
UNION ALL SELECT 'customers   ' || COUNT(*) FROM customers
UNION ALL SELECT 'costs       ' || COUNT(*) FROM costs
UNION ALL SELECT 'sales       ' || COUNT(*) FROM sales
UNION ALL SELECT 'suppl_demog ' || COUNT(*) FROM supplementary_demographics;
EXIT
SQL

echo "==> Sales History installed"
