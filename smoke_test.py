"""
smoke_test.py —— 冒烟测试

不开浏览器，用代码把所有功能走一遍。

这个测试同时支持两种数据库状态：
  · 空壳（刚 init_empty_db.py，没有数据）—— 验证结构完整、页面不报错
  · 有数据（跑过 import_data.py）—— 额外验证查课正确性
库里到底有没有数据，测试自己会判断，不用手动改。

运行：python smoke_test.py
"""

import base64
import os
import shutil
import sys
import tempfile

os.environ["SECRET_KEY"] = "test-key"

import db as db_module

REAL_DB = db_module.DB_PATH
if not os.path.exists(REAL_DB):
    print("找不到数据库，请先运行：python init_empty_db.py")
    sys.exit(1)

# 用临时副本测试，绝不动真库
TMP_DB = os.path.join(tempfile.gettempdir(), "xunke_test.db")
shutil.copy(REAL_DB, TMP_DB)
db_module.DB_PATH = TMP_DB

import app as app_module
app_module.app.config["TESTING"] = True
app_module.UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "xunke_test_uploads")
os.makedirs(app_module.UPLOAD_DIR, exist_ok=True)

import core
from app import app
from db import get_db

passed = failed = skipped = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [OK]   {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {extra}")


def skip(name, why):
    global skipped
    skipped += 1
    print(f"  [--]   {name}（跳过：{why}）")


with app.app_context():
    db = get_db()
    N_ROOMS = db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    N_SECS = db.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    N_SCHED = db.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]

HAS_DATA = N_ROOMS > 0 and N_SCHED > 0


# ============================================================
print("=" * 58)
print(f"0. 数据库状态：{'有数据' if HAS_DATA else '空壳'}"
      f"（教室 {N_ROOMS} / 节次 {N_SECS} / 课程 {N_SCHED}）")
print("=" * 58)

# ============================================================
print()
print("=" * 58)
print("1. 表结构完整性（空壳也必须通过）")
print("=" * 58)
EXPECTED = {
    "rooms":    ["room_no", "class_code"],
    "sections": ["seq", "name", "start_min", "end_min",
                 "fri_start_min", "fri_end_min"],
    "schedule": ["id", "class_code", "class_full", "weekday", "section",
                 "course", "teacher"],
    "records":  ["id", "room_no", "class_code", "class_name", "patrol_date",
                 "section", "course", "teacher", "situation", "author",
                 "image_path", "created_at"],
}
with app.app_context():
    db = get_db()
    for tbl, cols in EXPECTED.items():
        got = [r[1] for r in db.execute(f"PRAGMA table_info({tbl})")]
        check(f"表 {tbl} 存在且列完整", got == cols, f"实际 {got}")

    idx = {r[1] for r in db.execute(
        "SELECT * FROM sqlite_master WHERE type='index'")}
    check("查课索引 idx_schedule_lookup 存在", "idx_schedule_lookup" in idx)

# ============================================================
print()
print("=" * 58)
print("2. 班级代码提取（纯函数，不依赖数据）")
print("=" * 58)
check("'2301普职融通机械' → '2301'",
      core.class_code_of("2301普职融通机械") == "2301")
check("'2201' → '2201'", core.class_code_of("2201") == "2201")
check("'2205会计' → '2205'", core.class_code_of("2205会计") == "2205")

# ============================================================
print()
print("=" * 58)
print("3. 房间号 → 班级")
print("=" * 58)
with app.app_context():
    db = get_db()
    check("不存在的房间号返回 None（不报错）",
          core.room_to_class(db, "9-999") is None)
    check("空房间号返回 None", core.room_to_class(db, "") is None)
    if HAS_DATA:
        r = core.room_to_class(db, "1-101")
        check("1-101 能查到班级", r is not None, str(r))
    else:
        skip("1-101 能查到班级", "空壳无数据")

# ============================================================
print()
print("=" * 58)
print("4. ⭐ 查课正确性（原项目核心 bug）")
print("=" * 58)
if not HAS_DATA:
    skip("抽查真实课程", "空壳无数据")
    with app.app_context():
        db = get_db()
        check("查不存在的班级返回 None（不会张冠李戴）",
              core.lookup_course(db, "9999", "星期一", "一") is None)
else:
    with app.app_context():
        db = get_db()
        sample = db.execute("""
            SELECT class_code, weekday, section, course
            FROM schedule
            WHERE course IS NOT NULL AND course != ''
              AND class_code IN (SELECT class_code FROM rooms)
            LIMIT 40
        """).fetchall()
        check(f"库里能找到可测试的课程（{len(sample)} 条）", len(sample) > 0)

        wrong = []
        for s in sample:
            got = core.lookup_course(db, s["class_code"], s["weekday"], s["section"])
            if got is None or got["course"] != s["course"]:
                wrong.append((s["class_code"], s["weekday"], s["section"]))
        check(f"抽查 {len(sample)} 条课程全部查对", not wrong,
              f"错 {len(wrong)} 条：{wrong[:3]}")

        check("查不存在的班级返回 None",
              core.lookup_course(db, "9999", "星期一", "一") is None)

        a = core.lookup_course(db, "2301", "星期一", "三")
        b = core.lookup_course(db, "2302", "星期一", "三")
        print(f"         2301 周一第3节：{a['course'] if a else '—'}")
        print(f"         2302 周一第3节：{b['course'] if b else '—'}")

# ============================================================
print()
print("=" * 58)
print("5. 时间 → 节次")
print("=" * 58)
from datetime import datetime

if not HAS_DATA:
    skip("时间转节次", "空壳无节次数据")
    with app.app_context():
        check("节次表为空时返回 None（不报错）",
              core.section_at(get_db(), datetime(2026, 10, 20, 8, 10)) is None)
else:
    with app.app_context():
        db = get_db()
        s = core.section_at(db, datetime(2026, 10, 20, 8, 10))   # 周二
        check("周二 08:10 → 第一节", s is not None and s["name"] == "一", str(s))
        s2 = core.section_at(db, datetime(2026, 10, 20, 13, 30))
        check("周二 13:30 → 第五节", s2 is not None and s2["name"] == "五", str(s2))
        s3 = core.section_at(db, datetime(2026, 10, 23, 12, 50))  # 周五
        check("周五 12:50 → 第五节（周五作息）",
              s3 is not None and s3["name"] == "五", str(s3))
        check("周日中午不属于任何节次",
              core.section_at(db, datetime(2026, 10, 18, 12, 0)) is None)

# ============================================================
print()
print("=" * 58)
print("6. resolve() 组合查询")
print("=" * 58)
with app.app_context():
    db = get_db()
    bad = core.resolve(db, "9-999")
    check("不存在的房间号给出明确说明",
          bad["class_code"] is None and len(bad["notes"]) > 0, str(bad["notes"]))
    if HAS_DATA:
        info = core.resolve(db, "1-101", on_date="2026-10-19", section_name="一")
        print(f"         1-101 / 2026-10-19 / 第一节 → {info['class_full']} | "
              f"{info['weekday']} | {info['course']} | {info['teacher']}")
        check("房间号能解析出班级", info["class_code"] is not None)
        check("星期计算正确（2026-10-19 星期一）", info["weekday"] == "星期一")
        check("节次正确", info["section"] == "一")
    else:
        skip("resolve 完整解析", "空壳无数据")
    # 无论有没有数据，日期/星期计算都应该对
    info2 = core.resolve(db, "9-999", on_date="2026-10-19")
    check("即使房间号不存在，星期也计算正确",
          info2["weekday"] == "星期一", str(info2["weekday"]))

# ============================================================
print()
print("=" * 58)
print("7. 网页路由（空壳下也必须 200）")
print("=" * 58)
client = app.test_client()

r = client.get("/")
check("首页能打开", r.status_code == 200)

r = client.get("/?room=9-999")
check("不存在的房间号给出提示", "不存在" in r.get_data(as_text=True))

r = client.get("/rooms")
check("教室一览能打开", r.status_code == 200)
if not HAS_DATA:
    check("空壳时教室一览显示空状态",
          "没有教室数据" in r.get_data(as_text=True))
    check("空壳时首页给出“系统还是空的”警告",
          "系统还是空的" in client.get("/").get_data(as_text=True))
else:
    check("有数据时首页不显示空壳警告",
          "系统还是空的" not in client.get("/").get_data(as_text=True))

r = client.get("/records")
check("记录页能打开", r.status_code == 200)
check("空时显示空状态", "还没有巡课记录" in r.get_data(as_text=True))

r = client.get("/api/resolve?room=9-999")
check("API 正常返回 JSON", r.status_code == 200 and r.get_json()["ok"] is False)

# ============================================================
print()
print("=" * 58)
print("8. ⭐ 提交记录（原项目崩溃 bug 的回归）")
print("=" * 58)

payload = {
    "RoomNum": "1-101", "ClassName": "2201", "Date": "2026-10-19",
    "Sections": "一", "Course": "语文", "ClassTeacher": "张三",
    "ClassroomSituation": "到课率良好，纪律正常", "Author": "李老师",
}

# 8.1 不拍照提交 —— 原项目这里会 500
r = client.post("/submit", json={**payload, "Img": None})
j = r.get_json()
check("不拍照可以正常提交（原 bug 已修）", j.get("success") is True, str(j))

# 8.2 带照片提交
png = ("data:image/png;base64,"
       + base64.b64encode(bytes.fromhex(
           "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
           "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
       )).decode())
r = client.post("/submit", json={**payload, "Img": png})
j = r.get_json()
check("带照片提交成功", j.get("success") is True, str(j))
if j.get("image"):
    check("照片文件真的存在",
          os.path.exists(os.path.join(app_module.UPLOAD_DIR, j["image"])))

# 8.3 必填校验（这里是曾经把字段名写错的地方）
r = client.post("/submit", json={**payload, "ClassroomSituation": ""})
check("缺课堂情况被拒绝（字段名 ClassroomSituation）",
      r.get_json().get("success") is False)
r = client.post("/submit", json={**payload, "Author": ""})
check("缺填表人被拒绝", r.get_json().get("success") is False)
r = client.post("/submit", json={})
check("空请求被拒绝", r.get_json().get("success") is False)

# 8.4 异常不被吞掉
r = client.post("/submit", data="not json", content_type="text/plain")
check("非 JSON 请求返回明确的失败（不是假成功）",
      r.get_json().get("success") is False)

# ============================================================
print()
print("=" * 58)
print("9. 巡课记录查看（原项目完全缺失的功能）")
print("=" * 58)
r = client.get("/records")
body = r.get_data(as_text=True)
check("记录页能打开", r.status_code == 200)
check("能看到刚提交的记录", "李老师" in body and "1-101" in body)
check("统计数字显示出来了", "巡课总条数" in body)

r = client.get("/records?room=1-101")
check("按房间筛选可用", "1-101" in r.get_data(as_text=True))
r = client.get("/records?room=8-888")
check("筛选不存在的房间显示空状态", "还没有巡课记录" in r.get_data(as_text=True))
r = client.get("/records?author=李")
check("按填表人筛选可用", "李老师" in r.get_data(as_text=True))

with app.app_context():
    rid = get_db().execute("SELECT MAX(id) AS m FROM records").fetchone()["m"]
r = client.get(f"/records/{rid}")
body = r.get_data(as_text=True)
check("详情页能打开", r.status_code == 200)
check("详情页显示课堂情况", "到课率良好" in body)
check("详情页显示照片", "现场照片" in body)

r = client.get("/records/999999")
check("不存在的记录详情会跳回列表",
      r.status_code == 302 or "不存在" in r.get_data(as_text=True))

# ============================================================
print()
print("=" * 58)
print("10. 删除记录")
print("=" * 58)
r = client.post(f"/records/{rid}/delete", follow_redirects=True)
check("删除成功", "已删除" in r.get_data(as_text=True))
with app.app_context():
    gone = get_db().execute("SELECT COUNT(*) FROM records WHERE id=?",
                            (rid,)).fetchone()[0]
check("数据库里确实删掉了", gone == 0)
r = client.post("/records/999999/delete", follow_redirects=True)
check("删不存在的记录给出提示", "不存在" in r.get_data(as_text=True))

# ============================================================
print()
print("=" * 58)
print(f"结果：通过 {passed} 项，失败 {failed} 项"
      + (f"，跳过 {skipped} 项（空壳）" if skipped else ""))
print("=" * 58)

shutil.rmtree(app_module.UPLOAD_DIR, ignore_errors=True)
try:
    os.unlink(TMP_DB)
except Exception:
    pass

sys.exit(1 if failed else 0)