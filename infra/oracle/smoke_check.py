"""Smoke check for the Sales History install.

Verifies what the environment must prove:
  1. the read-only user can connect to the reporting replica,
  2. a join across four tables returns data,
  3. the read-only user really is read-only,
  4. the same user has no way into the transactional database at all.

Run:
    docker run --rm --network host -v "$PWD/infra/oracle:/w:ro" \
        -e ORACLE_APP_USER -e ORACLE_APP_USER_PASSWORD -e ORACLE_DSN \
        python:3.12-slim sh -c "pip install -q oracledb && python /w/smoke_check.py"
"""

import os
import sys

import oracledb


def main() -> int:
    user = os.environ.get("ORACLE_APP_USER", "agent_ro")
    password = os.environ["ORACLE_APP_USER_PASSWORD"]
    dsn = os.environ.get("ORACLE_DSN", "127.0.0.1:1521/REPPDB1")

    print(f"connecting as {user} to {dsn} (thin mode, python-oracledb {oracledb.__version__})")
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        cur = conn.cursor()

        print("\n1. version")
        cur.execute("SELECT banner_full FROM v$version")
        print("  ", cur.fetchone()[0].splitlines()[0])

        print("\n2. row counts")
        for table in ("channels", "countries", "products", "promotions",
                      "times", "customers", "costs", "sales"):
            cur.execute(f"SELECT COUNT(*) FROM sh.{table}")
            print(f"   {table:<12}{cur.fetchone()[0]:>9,}")

        print("\n3. sales by region, joined across four tables")
        cur.execute("""
            SELECT co.country_region,
                   COUNT(*)              AS lines,
                   ROUND(SUM(s.amount_sold)) AS amount
            FROM sh.sales s
            JOIN sh.times t      ON s.time_id = t.time_id
            JOIN sh.customers cu ON s.cust_id = cu.cust_id
            JOIN sh.countries co ON cu.country_id = co.country_id
            WHERE t.calendar_quarter_desc = :quarter
            GROUP BY co.country_region
            ORDER BY amount DESC
        """, quarter="2021-02")
        rows = cur.fetchall()
        if not rows:
            print("   NO ROWS: check the quarter format in TIMES.calendar_quarter_desc")
            return 1
        for region, lines, amount in rows:
            print(f"   {region:<16}{lines:>8,} lines{amount:>14,.0f}")

        print("\n4. data range actually present")
        cur.execute("SELECT MIN(calendar_year), MAX(calendar_year) FROM sh.times")
        print("   calendar years: %s to %s" % cur.fetchone())

        print("\n5. read-only enforcement")
        for statement, label in (
            ("CREATE TABLE agent_scratch (x NUMBER)", "create a table"),
            ("INSERT INTO sh.sales SELECT * FROM sh.sales WHERE 1 = 0", "insert into SH"),
            ("SELECT COUNT(*) FROM hr.employees", "read outside SH"),
        ):
            try:
                cur.execute(statement)
            except oracledb.DatabaseError as exc:
                print(f"   {label:<20}refused: {str(exc.args[0].message).splitlines()[0]}")
            else:
                print(f"   {label:<20}ALLOWED. This is a hole, fix it before going further.")
                return 1

    print("\n6. the agent has no path to the transactional database")
    primary = dsn.rsplit("/", 1)[0] + "/FREEPDB1"
    try:
        oracledb.connect(user=user, password=password, dsn=primary)
    except oracledb.DatabaseError as exc:
        print(f"   {primary}: refused, {str(exc.args[0].message).splitlines()[0]}")
    else:
        print(f"   {primary}: CONNECTED. The agent can reach the primary, fix this first.")
        return 1

    print("\n7. the replica states what moment it describes")
    with oracledb.connect(user=user, password=password, dsn=dsn) as conn:
        cur = conn.cursor()
        cur.execute("SELECT as_of, source_pdb, method FROM sh.replica_info")
        row = cur.fetchone()
        if row is None:
            print("   replica_info is empty: answers could not state their as-of moment")
            return 1
        print(f"   as of {row[0]:%Y-%m-%d %H:%M:%S%z}, from {row[1]}, by {row[2]}")

    print("\nall checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
