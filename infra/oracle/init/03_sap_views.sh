#!/usr/bin/env bash
# SAP-shaped views over the Sales History tables.
#
# Why they exist: the brief calls the semantic layer the core of the value,
# because in a real SAP landscape a field is called MATNR, not "product". On the
# bare SH tables the semantic layer looks optional, since SALES and CUSTOMERS
# read fine without it. These views put the real problem back on the table
# without inventing a single row of data: same data, SAP names and SAP habits.
#
# Every trap below is real SAP behaviour, and each one is described in the
# semantic layer:
#   MANDT  every table carries the client and every query must filter it
#   MATNR  material numbers are zero-padded to 18 characters, so joining them
#          to a plain number silently returns nothing
#   LVORM  the deletion flag: rows stay, and forgetting the filter inflates totals
#   WAERK  amounts carry their currency, so summing across currencies is wrong
#          even when it runs
#   SPRAS  text tables are per language, so the join needs a language filter

set -euo pipefail

# Reporting replica. The primary has no agent account and no reporting views.
PDB=REPPDB1
SH_PASSWORD="${SH_PASSWORD:-$ORACLE_PASSWORD}"

sqlplus -s -L "sh/${SH_PASSWORD}@localhost/${PDB}" <<'SQL'
WHENEVER SQLERROR EXIT SQL.SQLCODE
SET FEEDBACK OFF

-- ZMARA: general material data, from PRODUCTS.
CREATE OR REPLACE VIEW zmara AS
SELECT '100'                                  AS mandt,
       LPAD(TO_CHAR(p.prod_id), 18, '0')      AS matnr,
       SUBSTR(p.prod_category, 1, 4)          AS mtart,
       SUBSTR(p.prod_subcategory, 1, 9)       AS matkl,
       p.prod_unit_of_measure                 AS meins,
       p.prod_weight_class                    AS ntgew,
       p.prod_eff_from                        AS ersda,
       CASE WHEN p.prod_valid = 'A' THEN ' ' ELSE 'X' END AS lvorm,
       p.prod_name                            AS maktx,
       p.prod_list_price                      AS netpr
FROM products p;

-- ZKNA1: general customer data, from CUSTOMERS.
-- TELF1 and SMTP_ADDR are personal data. They exist in the view on purpose:
-- masking has to hide something real, and a semantic layer that never meets
-- personal data proves nothing.
CREATE OR REPLACE VIEW zkna1 AS
SELECT '100'                                          AS mandt,
       LPAD(TO_CHAR(c.cust_id), 10, '0')              AS kunnr,
       c.cust_first_name || ' ' || c.cust_last_name   AS name1,
       co.country_iso_code                            AS land1,
       c.cust_city                                    AS ort01,
       c.cust_postal_code                             AS pstlz,
       c.cust_state_province                          AS regio,
       c.cust_street_address                          AS stras,
       c.cust_main_phone_number                       AS telf1,
       c.cust_email                                   AS smtp_addr,
       c.cust_eff_from                                AS erdat,
       -- CUST_VALID is 'A' for the 10 621 customers that actually trade and 'I'
       -- for the other 44 879. Mapping it the other way round produces an empty
       -- result with no error, which is exactly the failure this project exists
       -- to catch: verified by counting, not by reading the column name.
       CASE WHEN c.cust_valid = 'A' THEN ' ' ELSE 'X' END AS lvorm
FROM customers c
JOIN countries co ON co.country_id = c.country_id;

-- ZVBRP: billing document items, from SALES.
-- SH.SALES has no document number, and inventing one would be a lie, so the
-- view stays at item granularity: one row is one billed line.
CREATE OR REPLACE VIEW zvbrp AS
SELECT '100'                                     AS mandt,
       LPAD(TO_CHAR(s.prod_id), 18, '0')         AS matnr,
       LPAD(TO_CHAR(s.cust_id), 10, '0')         AS kunnr,
       s.time_id                                 AS fkdat,
       LPAD(TO_CHAR(s.channel_id), 2, '0')       AS vtweg,
       s.quantity_sold                           AS fkimg,
       s.amount_sold                             AS netwr,
       'USD'                                     AS waerk,
       LPAD(TO_CHAR(s.promo_id), 10, '0')        AS aktnr
FROM sales s;

-- ZT005T: country texts, from COUNTRIES.
CREATE OR REPLACE VIEW zt005t AS
SELECT '100'                  AS mandt,
       'E'                    AS spras,
       c.country_iso_code     AS land1,
       c.country_name         AS landx,
       c.country_region       AS regio_text,
       c.country_subregion    AS subregio_text
FROM countries c;

-- ZTVTWT: distribution channel texts, from CHANNELS.
CREATE OR REPLACE VIEW ztvtwt AS
SELECT '100'                                  AS mandt,
       'E'                                    AS spras,
       LPAD(TO_CHAR(ch.channel_id), 2, '0')   AS vtweg,
       ch.channel_desc                        AS vtext,
       ch.channel_class                       AS vclass
FROM channels ch;

-- WAKH: promotion header, from PROMOTIONS.
CREATE OR REPLACE VIEW wakh AS
SELECT '100'                                     AS mandt,
       LPAD(TO_CHAR(p.promo_id), 10, '0')        AS aktnr,
       p.promo_name                              AS aktxt,
       SUBSTR(p.promo_category, 1, 4)            AS akart,
       p.promo_subcategory                       AS aktyp,
       p.promo_cost                              AS aktko,
       p.promo_begin_date                        AS datab,
       p.promo_end_date                          AS datbi
FROM promotions p;

-- ZKEKO: standard cost estimate, from COSTS.
CREATE OR REPLACE VIEW zkeko AS
SELECT '100'                                     AS mandt,
       LPAD(TO_CHAR(c.prod_id), 18, '0')         AS matnr,
       c.time_id                                 AS kadat,
       LPAD(TO_CHAR(c.channel_id), 2, '0')       AS vtweg,
       LPAD(TO_CHAR(c.promo_id), 10, '0')        AS aktnr,
       c.unit_cost                               AS stprs,
       c.unit_price                              AS verpr,
       'USD'                                     AS waers
FROM costs c;

-- ZT009B: fiscal period assignment, from TIMES.
-- SPMON is the SAP period key, year and month glued together with no separator.
CREATE OR REPLACE VIEW zt009b AS
SELECT '100'                                          AS mandt,
       t.time_id                                      AS budat,
       TO_CHAR(t.time_id, 'YYYYMM')                   AS spmon,
       LPAD(TO_CHAR(t.calendar_month_number), 3, '0') AS poper,
       TO_CHAR(t.calendar_year)                       AS bdatj,
       t.calendar_quarter_desc                        AS quartal,
       t.calendar_year                                AS gjahr
FROM times t;
EXIT
SQL

echo "==> SAP-shaped views created: ZMARA, ZKNA1, ZVBRP, ZT005T, ZTVTWT, ZT009B, WAKH, ZKEKO"

sqlplus -s -L "sh/${SH_PASSWORD}@localhost/${PDB}" <<'SQL'
SET HEADING OFF FEEDBACK OFF PAGESIZE 0
SELECT '==> ' || view_name || ': ' || COUNT(*) OVER () || ' views total'
  FROM user_views WHERE view_name LIKE 'Z%' OR view_name = 'WAKH' ORDER BY view_name;
EXIT
SQL
