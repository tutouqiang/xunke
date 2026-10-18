"""
db.py —— 数据库工具

和记账本那个项目一样的套路：一个请求共用一个连接，请求结束自动关。
"""

import os
import sqlite3

from flask import g

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "xunke.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def db_exists():
    """数据库文件在不在。不在说明还没跑 import_data.py。"""
    return os.path.exists(DB_PATH)