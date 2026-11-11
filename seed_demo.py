"""seed_demo.py —— 灌入虚拟演示数据（全部为虚构，不含任何真实信息）

用途：给"空壳"版巡课系统灌一套演示数据，让线上 demo 能真实体验
扫码带出课程、填表提交、后台查询的完整流程。

数据特征：
  · 教室：3 栋楼 × 20 间（1-101 ~ 1-120 / 2-201 ~ 2-220 / 3-301 ~ 3-320）
  · 班级：2201~2206、2301~2306 共 12 个虚构班（如 "2301示例机电1班"）
  · 节次：8 节，含周五第五节单独作息（12:40-13:20），与真实学校作息格式一致
  · 课程/教师：通用课程名 + "张老师/李老师"式占位名
  · 巡课记录：20 条示例记录（近两周内日期，含课堂情况和填表人）

⚠️ 本脚本会清空并重建 rooms / sections / schedule / records 四张表的
业务数据（先备份 xunke.db 再跑，如果本地有你想留的记录）。
真实数据请依旧用 import_data.py 从 Excel 导入。

用法：
    python seed_demo.py
"""

import os
import sqlite3
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "xunke.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

WEEKDAY_NAMES = ["星期一", "星期二", "星期三", "星期四", "星期五"]

# ---------------- 虚构班级（代码 → 全名） ----------------
CLASSES = {
    "2201": "2201示例机电1班",
    "2202": "2202示例数控1班",
    "2203": "2203示例电商1班",
    "2204": "2204示例会计1班",
    "2205": "2205示例物流1班",
    "2206": "2206示例护理1班",
    "2301": "2301示例机电2班",
    "2302": "2302示例数控2班",
    "2303": "2303示例计算机1班",
    "2304": "2304示例建筑1班",
    "2305": "2305示例汽修1班",
    "2306": "2306示例设计1班",
}
CLASS_CODES = list(CLASSES.keys())

# ---------------- 节次时间表（分钟制，同 import_data.py 的格式） ----------------
# (seq, name, start_min, end_min, fri_start_min, fri_end_min)
SECTIONS = [
    (1, "一", 480, 525, None, None),   # 08:00-08:45
    (2, "二", 535, 580, None, None),   # 08:55-09:40
    (3, "三", 600, 645, None, None),   # 10:00-10:45
    (4, "四", 655, 700, None, None),   # 10:55-11:40
    (5, "五", 800, 845, 760, 800),     # 普通日 13:20-14:05；周五 12:40-13:20
    (6, "六", 855, 900, None, None),   # 14:15-15:00
    (7, "七", 910, 955, None, None),   # 15:10-15:55
    (8, "八", 965, 1010, None, None),  # 16:05-16:50
]

COURSES = [
    "数学", "语文", "英语", "德育", "体育",
    "计算机基础", "电工技术", "机械制图", "编程入门", "数据库应用",
    "会计基础", "物流管理", "电子商务", "护理基础", "设计制图",
]
TEACHERS = [
    "张老师", "李老师", "王老师", "陈老师", "刘老师", "赵老师",
    "孙老师", "周老师", "吴老师", "郑老师", "冯老师", "褚老师",
]


def make_rooms():
    """教室 ↔ 班级：3 栋楼 × 每栋 20 间，轮转分配到 12 个班。

    1-101 → 2201、1-102 → 2202 ... 与 smoke_test 的 1-101 假设一致。
    """
    rooms = []
    i = 0
    for bld in (1, 2, 3):
        for n in range(1, 21):
            # 生成 1-101..1-120 / 2-201..2-220 / 3-301..3-320
            room_no = f"{bld}-{bld * 100 + n:02d}"
            rooms.append((room_no, CLASS_CODES[i % len(CLASS_CODES)]))
            i += 1
    return rooms


def make_schedule():
    """给 12 个班 × 周一~周五 × 8 节排满虚构课表。

    课程/教师按 (班级,星期,节次) 稳定轮转，保证任意组合都有课可查。
    """
    sched = []
    for ci, code in enumerate(CLASS_CODES):
        full = CLASSES[code]
        for wi, wd in enumerate(WEEKDAY_NAMES):
            for si, (seq, name, *_rest) in enumerate(SECTIONS):
                course = COURSES[(ci * 3 + wi * 2 + si) % len(COURSES)]
                teacher = TEACHERS[(ci * 5 + wi * 3 + si * 2) % len(TEACHERS)]
                sched.append((code, full, wd, name, course, teacher))
    return sched


SITUATIONS = [
    "课堂秩序正常，到课率 100%",
    "整体良好，两名学生在后排睡觉",
    "多媒体设备运行正常，教学进度正常",
    "有学生玩手机，已提醒",
    "课堂气氛活跃，师生互动良好",
    "到课率 95%，两名学生请假",
    "实训课设备使用规范，秩序良好",
    "老师提前下课十分钟",
]
AUTHORS = ["张巡查", "李巡查", "王巡查", "赵巡查"]


def make_records(rooms, sched_map):
    """20 条示例巡课记录：日期取最近的上课日，节次/课程与课表自洽。"""
    records = []
    today = date.today()
    for i in range(20):
        d = today - timedelta(days=i)
        # 周末回退到最近的周五
        while d.weekday() > 4:
            d -= timedelta(days=1)
        wd = WEEKDAY_NAMES[d.weekday()]
        room_no, class_code = rooms[(i * 7) % len(rooms)]
        sec = SECTIONS[i % 8]
        section_name = sec[1]
        course, teacher = sched_map[(class_code, wd, section_name)]
        situation = SITUATIONS[i % len(SITUATIONS)]
        author = AUTHORS[i % len(AUTHORS)]
        records.append((
            room_no, class_code, CLASSES[class_code],
            d.isoformat(), section_name, course, teacher, situation, author,
        ))
    return records


def main():
    if not os.path.exists(DB_PATH):
        print(f"数据库不存在，将新建：{DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    with open(SCHEMA_PATH, encoding="utf-8") as f:
        conn.executescript(f.read())

    for t in ("records", "schedule", "rooms", "sections"):
        conn.execute(f"DELETE FROM {t}")

    conn.executemany(
        "INSERT INTO sections(seq, name, start_min, end_min, fri_start_min, fri_end_min) "
        "VALUES (?, ?, ?, ?, ?, ?)", SECTIONS)

    rooms = make_rooms()
    conn.executemany("INSERT INTO rooms(room_no, class_code) VALUES (?, ?)", rooms)

    sched = make_schedule()
    conn.executemany(
        "INSERT INTO schedule(class_code, class_full, weekday, section, course, teacher) "
        "VALUES (?, ?, ?, ?, ?, ?)", sched)
    sched_map = {(c, w, s): (course, t) for (c, _f, w, s, course, t) in sched}

    recs = make_records(rooms, sched_map)
    conn.executemany(
        "INSERT INTO records(room_no, class_code, class_name, patrol_date, "
        "section, course, teacher, situation, author) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", recs)

    conn.commit()
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ("rooms", "sections", "schedule", "records")}
    conn.close()

    print("演示数据已生成（全部虚构，不含真实信息）：")
    for t, n in counts.items():
        print(f"  {t:<9} {n} 行")
    print()
    print("体验入口：python app.py → http://127.0.0.1:5001/?room=1-101")
    print("教室一览：/rooms    记录查询：/records")


if __name__ == "__main__":
    import sys
    sys.exit(main())
