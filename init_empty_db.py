"""建一个空的数据库（只有表结构，没有任何数据）。

用途：得到一个"空壳"巡课系统。表建好、页面能开，但不含任何教室/课程数据，
避免把真实学校课表和教师姓名打包进去。

用法：python init_empty_db.py
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "xunke.db")

TABLES = ["rooms", "sections", "schedule", "records"]

if os.path.exists(DB_PATH):
    print(f"已有数据库，先删除：{DB_PATH}")
    os.remove(DB_PATH)

with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
    schema = f.read()

conn = sqlite3.connect(DB_PATH)
conn.executescript(schema)
conn.commit()

print(f"已建空库：{DB_PATH}")
print()
print("表结构：")
for t in TABLES:
    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
    print(f"  {t:<10} 行数={n}  列={cols}")

idx = [r[1] for r in conn.execute(
    "SELECT * FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")]
print()
print(f"索引：{idx}")

conn.close()
print()
print("空壳就绪，启动：python app.py")