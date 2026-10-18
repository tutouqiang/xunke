"""
import_data.py —— 把 Excel 数据一次性导入 SQLite

只跑一次就行。之后程序运行完全不需要 Excel。
数据源：桌面 xunke1.2 文件夹里的三个表格。

用法：python import_data.py [Excel所在目录]
"""

import os
import re
import sqlite3
import sys

from openpyxl import load_workbook

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "xunke.db")

# Excel 默认在桌面那个文件夹，命令行可以覆盖
DEFAULT_SRC = os.path.join(os.path.expanduser("~"), "Desktop", "xunke1.2")


def t2min(t):
    """把 Excel 里的时间值转成"从 0 点开始的分钟数"。

    Excel 读出来可能是 datetime.time(8, 0)，也可能是字符串 '08:00:00'，
    两种都要能处理。
    """
    if t is None or t == "":
        return None
    if hasattr(t, "hour"):                       # datetime.time
        return t.hour * 60 + t.minute
    s = str(t).strip()                           # 字符串形式
    m = re.match(r"^(\d{1,2}):(\d{2})", s)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def read_rows(path):
    """读一个 Excel 的第一个工作表，返回 (表头, 数据行列表)。"""
    wb = load_workbook(path, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    return rows[0], [r for r in rows[1:] if any(v is not None for v in r)]


def code_of(class_full):
    """从班级全名里取出班级代码。

    '2301普职融通机械' → '2301'
    规则：取开头连续的字母/数字（通常是 4 位数字）。
    """
    m = re.match(r"^([A-Za-z0-9]+)", str(class_full).strip())
    return m.group(1) if m else str(class_full).strip()


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    if not os.path.isdir(src):
        print(f"[错误] 找不到 Excel 目录：{src}")
        return 1

    # 每次都重建，保证数据干净（Excel 是唯一事实来源）
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
        schema = f.read()

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema)

    # ---------- 1. 教室 ↔ 班级 ----------
    header, rows = read_rows(os.path.join(src, "ClassDistribution.xlsx"))
    rooms = []
    for r in rows:
        room_no = str(r[0]).strip() if r[0] is not None else ""
        code = str(r[1]).strip() if r[1] is not None else ""
        if room_no and code:
            rooms.append((room_no, code))
    conn.executemany("INSERT OR REPLACE INTO rooms (room_no, class_code) VALUES (?, ?)", rooms)
    print(f"[1/3] 教室对应表：导入 {len(rooms)} 条")

    # ---------- 2. 节次时间 ----------
    header, rows = read_rows(os.path.join(src, "ClassSections.xlsx"))
    secs = []
    for r in rows:
        name = str(r[0]).strip()
        seq = "一二三四五六七八".index(name) + 1 if name in "一二三四五六七八" else len(secs) + 1
        secs.append((
            seq, name,
            t2min(r[1]), t2min(r[2]),
            t2min(r[3]) if len(r) > 3 else None,
            t2min(r[4]) if len(r) > 4 else None,
        ))
    conn.executemany(
        """INSERT OR REPLACE INTO sections
           (seq, name, start_min, end_min, fri_start_min, fri_end_min)
           VALUES (?, ?, ?, ?, ?, ?)""", secs)
    print(f"[2/3] 节次时间表：导入 {len(secs)} 条")

    # ---------- 3. 课程表 ----------
    header, rows = read_rows(os.path.join(src, "ClassTable.xlsx"))
    sched = []
    for r in rows:
        full = r[0]
        if full is None:
            continue
        sched.append((
            code_of(full), str(full).strip(),
            str(r[1]).strip() if r[1] is not None else "",
            str(r[2]).strip() if r[2] is not None else "",
            str(r[3]).strip() if len(r) > 3 and r[3] is not None else "",
            str(r[4]).strip() if len(r) > 4 and r[4] is not None else "",
        ))
    conn.executemany(
        """INSERT INTO schedule (class_code, class_full, weekday, section, course, teacher)
           VALUES (?, ?, ?, ?, ?, ?)""", sched)
    print(f"[3/3] 课程表：导入 {len(sched)} 条")

    conn.commit()

    # ---------- 数据体检：报告问题，别默默放过 ----------
    print()
    print("=" * 56)
    print("数据体检")
    print("=" * 56)

    n_room_no_sched = conn.execute("""
        SELECT COUNT(*) FROM rooms r
        WHERE NOT EXISTS (SELECT 1 FROM schedule s WHERE s.class_code = r.class_code)
    """).fetchone()[0]
    print(f"  教室对应表里，有 {n_room_no_sched} 个班级在课程表里查无此班")

    n_sched_no_room = conn.execute("""
        SELECT COUNT(DISTINCT class_code) FROM schedule
        WHERE class_code NOT IN (SELECT class_code FROM rooms)
    """).fetchone()[0]
    print(f"  课程表里，有 {n_sched_no_room} 个班级没有分配教室（不影响查询）")

    print(f"  唯一班级数（课程表）：{conn.execute('SELECT COUNT(DISTINCT class_code) FROM schedule').fetchone()[0]}")
    print(f"  唯一班级数（教室表）：{conn.execute('SELECT COUNT(DISTINCT class_code) FROM rooms').fetchone()[0]}")

    today = conn.execute("SELECT date('now','localtime')").fetchone()[0]
    print(f"  今天 {today} 是星期{['一','二','三','四','五','六','日'][__import__('datetime').date.today().weekday()]}")
    wk = "星期" + "一二三四五六日"[__import__("datetime").date.today().weekday()]
    print(f"  今天课程表里 {wk} 的课：{conn.execute('SELECT COUNT(*) FROM schedule WHERE weekday = ?', (wk,)).fetchone()[0]} 条")

    conn.close()
    print()
    print(f"数据库已生成：{DB_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())