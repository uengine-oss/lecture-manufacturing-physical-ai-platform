# 시연 4 · SQL 로 PostgreSQL 에 묻기 (읽기만 한다)
from hydops.b3_tsdb import store

with store.connect() as c:
    tables = c.execute("SELECT count(*) AS n FROM observation").fetchone()
    print("observation 행 수:", tables["n"])
    rows = c.execute(
        "SELECT sensor_id, unit, count(*) AS n FROM observation WHERE asset_id = %s GROUP BY sensor_id, unit ORDER BY sensor_id",
        ("HYD-01",),                             # %s 자리에 값을 따로 넘긴다
    ).fetchall()
    for r in rows:
        print(r["sensor_id"], r["unit"], r["n"])
    src = c.execute("SELECT source, count(*) AS n FROM run GROUP BY source ORDER BY source").fetchall()
    print("run.source 종류:", [(x["source"], x["n"]) for x in src])
