"""
core.py —— 巡课系统的核心业务逻辑

这里放的是"和网页无关"的纯计算：
  - 房间号 → 班级
  - 当前时间 → 第几节
  - 班级 + 星期 + 节次 → 课程、任课教师

单独抽出来，一是好测试（不用起网页就能测），二是网页代码能短很多。
"""

import re
from datetime import date, datetime

WEEKDAYS = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


# ============================================================
# 一、班级代码
# ============================================================

def class_code_of(class_full):
    """从班级全名取代码：'2301普职融通机械' → '2301'"""
    m = re.match(r"^([A-Za-z0-9]+)", str(class_full).strip())
    return m.group(1) if m else str(class_full).strip()


# ============================================================
# 二、房间号 → 班级
# ============================================================

def room_to_class(db, room_no):
    """根据房间号查班级。查不到返回 None。"""
    if not room_no:
        return None
    row = db.execute(
        "SELECT room_no, class_code FROM rooms WHERE room_no = ?",
        (str(room_no).strip(),),
    ).fetchone()
    return dict(row) if row else None


def list_rooms(db):
    """列出所有教室，并附上班级今天有几节课（首页用）。"""
    return db.execute("""
        SELECT r.room_no, r.class_code, s.class_full
        FROM rooms r
        LEFT JOIN (
            SELECT class_code, MIN(class_full) AS class_full
            FROM schedule GROUP BY class_code
        ) s ON s.class_code = r.class_code
        ORDER BY r.room_no
    """).fetchall()


# ============================================================
# 三、时间 → 第几节
# ============================================================

def section_at(db, when):
    """判断某个时刻属于第几节。

    周五的作息和其他天不同（第五节开始时间不一样），
    所以周五优先用 fri_start_min / fri_end_min 判断。
    """
    if isinstance(when, datetime):
        t = when.time()
    elif isinstance(when, date):
        t = datetime.min.time()
    else:
        t = when

    minute = t.hour * 60 + t.minute
    is_friday = when.weekday() == 4 if isinstance(when, (date, datetime)) else False

    rows = db.execute("""
        SELECT seq, name, start_min, end_min, fri_start_min, fri_end_min
        FROM sections ORDER BY seq
    """).fetchall()

    for r in rows:
        if is_friday and r["fri_start_min"] is not None:
            if r["fri_start_min"] <= minute <= r["fri_end_min"]:
                return dict(r)
        elif r["start_min"] <= minute <= r["end_min"]:
            return dict(r)
    return None


def section_by_name(db, name):
    """按节次名（一~八）查节次信息。"""
    if not name:
        return None
    row = db.execute(
        "SELECT * FROM sections WHERE name = ?", (str(name).strip(),)
    ).fetchone()
    return dict(row) if row else None


def all_sections(db):
    return db.execute("SELECT * FROM sections ORDER BY seq").fetchall()


# ============================================================
# 四、班级 + 星期 + 节次 → 课程 / 教师
# ============================================================

def lookup_course(db, class_code, weekday, section):
    """查某班某天某节上什么课、谁教。

    原项目的 bug 就在这里：它用第 i 行的班级去比第 i+1 行的星期，
    行号错位，所以查出来经常是错的。这里直接用三个条件一起筛，
    不给错位留机会。

    没排课返回 None。
    """
    if not class_code or not weekday or not section:
        return None
    row = db.execute(
        """SELECT class_full, weekday, section, course, teacher
           FROM schedule
           WHERE class_code = ? AND weekday = ? AND section = ?
           LIMIT 1""",
        (str(class_code).strip(), weekday, str(section).strip()),
    ).fetchone()
    return dict(row) if row else None


def weekday_of(d):
    """日期 → '星期几'"""
    if isinstance(d, str):
        d = date.fromisoformat(d)
    return WEEKDAYS[d.weekday()]


# ============================================================
# 五、组合：一次把巡检员要的信息全查出来
# ============================================================

def resolve(db, room_no, on_date=None, section_name=None):
    """扫码后自动带出全部信息。

    参数：
      room_no      —— 房间号（必填，来自二维码）
      on_date      —— 日期，默认今天
      section_name —— 节次，默认按当前时间自动判断

    返回一个 dict，包含班级、节次、课程、教师；查不到的项给 None 并附说明。
    """
    result = {
        "room_no": room_no,
        "class_code": None,
        "class_full": None,
        "date": None,
        "weekday": None,
        "section": None,
        "section_seq": None,
        "course": None,
        "teacher": None,
        "notes": [],
    }

    # --- 房间号 → 班级 ---
    room = room_to_class(db, room_no)
    if room is None:
        result["notes"].append(f"房间号 {room_no} 在教室对应表中不存在")
        return result
    result["class_code"] = room["class_code"]

    sched = db.execute(
        "SELECT MIN(class_full) AS f FROM schedule WHERE class_code = ?",
        (room["class_code"],),
    ).fetchone()
    result["class_full"] = sched["f"] if sched and sched["f"] else room["class_code"]

    # --- 日期 / 星期 ---
    if on_date:
        d = date.fromisoformat(on_date) if isinstance(on_date, str) else on_date
    else:
        d = date.today()
    result["date"] = d.isoformat()
    result["weekday"] = weekday_of(d)

    # --- 节次 ---
    if section_name:
        sec = section_by_name(db, section_name)
        if sec is None:
            result["notes"].append(f"节次「{section_name}」不存在")
            return result
        result["section"] = sec["name"]
        result["section_seq"] = sec["seq"]
    else:
        sec = section_at(db, datetime.now())
        if sec is None:
            result["notes"].append("当前时间不在任何节次内（可能在上课时间之外）")
            return result
        result["section"] = sec["name"]
        result["section_seq"] = sec["seq"]

    # --- 课程 / 教师 ---
    info = lookup_course(db, result["class_code"], result["weekday"], result["section"])
    if info is None:
        result["notes"].append(
            f"{result['weekday']}第{result['section']}节 该班没有排课"
        )
    else:
        result["course"] = info["course"]
        result["teacher"] = info["teacher"]

    return result


# ============================================================
# 六、巡课记录
# ============================================================

RECORD_FIELDS = ("room_no", "class_code", "class_name", "patrol_date",
                 "section", "course", "teacher", "situation", "author")


def insert_record(db, data, image_path=None):
    """写入一条巡课记录。返回新记录的 id。"""
    cur = db.execute(
        """INSERT INTO records
           (room_no, class_code, class_name, patrol_date, section,
            course, teacher, situation, author, image_path)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            data.get("room_no", ""), data.get("class_code", ""),
            data.get("class_name", ""), data.get("patrol_date", ""),
            data.get("section", ""), data.get("course", ""),
            data.get("teacher", ""), data.get("situation", ""),
            data.get("author", ""), image_path,
        ),
    )
    db.commit()
    return cur.lastrowid


def query_records(db, room_no=None, on_date=None, author=None, limit=200):
    """查巡课记录，支持按房间号 / 日期 / 填表人筛选。"""
    where, params = [], []
    if room_no:
        where.append("room_no = ?")
        params.append(room_no)
    if on_date:
        where.append("patrol_date = ?")
        params.append(on_date)
    if author:
        where.append("author LIKE ?")
        params.append(f"%{author}%")
    sql = "SELECT * FROM records"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY patrol_date DESC, id DESC LIMIT ?"
    params.append(limit)
    return db.execute(sql, params).fetchall()


def record_stats(db):
    """记录总览：总条数、涉及教室数、最近一次巡课时间。"""
    row = db.execute("""
        SELECT COUNT(*) AS total,
               COUNT(DISTINCT room_no) AS rooms,
               COUNT(DISTINCT author) AS authors,
               MAX(created_at) AS latest
        FROM records
    """).fetchone()
    return dict(row) if row else {"total": 0, "rooms": 0, "authors": 0, "latest": None}