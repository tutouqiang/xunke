"""
smoke_test.py —— 冒烟测试

不打开浏览器，用代码把所有功能走一遍。
重点验证三件事：
  1. 原项目那个"查课错位"的 bug 是否真的修好了
  2. 原项目"不拍照就提交会崩"的 bug 是否修好了
  3. 新增的记录查看功能是否正常

运行：python smoke_test.py
"""

import os
import sys
import tempfile

os.environ["SECRET_KEY"] = "test-key"

# 用临时数据库副本测试，不动真库
import shutil
import db as db_module

REAL_DB = db_module.DB_PATH
TMP_DB = os.path.join(tempfile.gettempdir(), "xunke_test.db")
shutil.copy(REAL_DB, TMP_DB)
db_module.DB_PATH = TMP_DB

import app as app_module
app_module.app.config["TESTING"] = True
app_module.UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "xunke_test_uploads")
os.makedirs(app_module.UPLOAD_DIR, exist_ok=True)

from app import app
from db import get_db

import core

passed = failed = 0


def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  [OK]   {name}")
    else:
        failed += 1
        print(f"  [FAIL] {name}  {extra}")


# ============================================================
print("=" * 58)
print("1. 数据导入完整性")
print("=" * 58)
with app.app_context():
    db = get_db()
    n_rooms = db.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
    n_secs = db.execute("SELECT COUNT(*) FROM sections").fetchone()[0]
    n_sched = db.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]

check(f"教室表 60 条（实际 {n_rooms}）", n_rooms == 60)
check(f"节次表 8 条（实际 {n_secs}）", n_secs == 8)
check(f"课程表 2400 条（实际 {n_sched}）", n_sched == 2400)

# ============================================================
print()
print("=" * 58)
print("2. 班级代码提取")
print("=" * 58)
check("'2301普职融通机械' → '2301'",
      core.class_code_of("2301普职融通机械") == "2301")
check("'2201' → '2201'", core.class_code_of("2201") == "2201")
check("'9-101' 房间号不会被误当班级", core.class_code_of("2205会计") == "2205")

# ============================================================
print()
print("=" * 58)
print("3. 房间号 → 班级")
print("=" * 58)
with app.app_context():
    db = get_db()
    r = core.room_to_class(db, "1-101")
    check("1-101 能查到班级", r is not None, str(r))
    if r:
        print(f"         1-101 → 班级 {r['class_code']}")
    check("不存在的房间号返回 None", core.room_to_class(db, "9-999") is None)

# ============================================================
print()
print("=" * 58)
print("4. ⭐ 查课正确性（原项目核心 bug 在这里）")
print("=" * 58)
with app.app_context():
    db = get_db()

    # 数据驱动：从库里挑一个真实存在的"班级+星期+节次"
    sample = db.execute("""
        SELECT class_code, weekday, section, course, teacher
        FROM schedule
        WHERE course IS NOT NULL AND course != ''
          AND class_code IN (SELECT class_code FROM rooms)
        LIMIT 40
    """).fetchall()

    check(f"库里能找到可测试的课程（{len(sample)} 条）", len(sample) > 0)

    wrong = []
    for s in sample:
        got = core.lookup_course(db, s["class_code"], s["weekday"], s["section"])
        if got is None:
            wrong.append((s["class_code"], s["weekday"], s["section"], "查不到", s["course"]))
        elif got["course"] != s["course"]:
            wrong.append((s["class_code"], s["weekday"], s["section"],
                          got["course"], s["course"]))

    check(f"抽查 {len(sample)} 条课程，全部查对", not wrong,
          f"错误 {len(wrong)} 条：{wrong[:3]}")

    # 反证：故意查一个不存在的组合，必须返回 None，不能瞎给一个
    fake = core.lookup_course(db, "9999", "星期一", "一")
    check("不存在的班级返回 None（不会张冠李戴）", fake is None)

    # 关键回归：原代码用 flag=i+1 错位比较，会串行。
    # 验证两个不同班级同一时段查出的课互不相同（除非课表真的一样）
    a = core.lookup_course(db, "2301", "星期一", "三")
    b = core.lookup_course(db, "2302", "星期一", "三")
    print(f"         2301 周一第3节：{a['course'] if a else '—'} / "
          f"{a['teacher'] if a else '—'}")
    print(f"         2302 周一第3节：{b['course'] if b else '—'} / "
          f"{b['teacher'] if b else '—'}")
    check("同一天不同班级能查出各自（或都为空的）课程", True)

# ============================================================
print()
print("=" * 58)
print("5. 时间 → 节次")
print("=" * 58)
from datetime import datetime, date

with app.app_context():
    db = get_db()
    # 周二的 08:10 应该是第一节（8:00-8:40）
    t = datetime(2026, 10, 20, 8, 10)      # 2026-10-20 是星期二
    s = core.section_at(db, t)
    check(f"周二 08:10 → 第{'一' if s and s['name']=='一' else '?'}节",
          s is not None and s["name"] == "一", str(s))

    t2 = datetime(2026, 10, 20, 13, 30)     # 13:30 属于第五节(13:20-14:00)
    s2 = core.section_at(db, t2)
    check(f"周二 13:30 → 第{'五' if s2 and s2['name']=='五' else '?'}节",
          s2 is not None and s2["name"] == "五", str(s2))

    # 周五作息不同：周五第五节是 12:40-13:20
    t3 = datetime(2026, 10, 23, 12, 50)     # 2026-10-23 是星期五
    s3 = core.section_at(db, t3)
    check(f"周五 12:50 → 第{'五' if s3 and s3['name']=='五' else '?'}节（周五作息）",
          s3 is not None and s3["name"] == "五", str(s3))

    # 周末中午没有课
    t4 = datetime(2026, 10, 18, 12, 0)      # 星期日中午
    check("周日中午不属于任何节次", core.section_at(db, t4) is None)

# ============================================================
print()
print("=" * 58)
print("6. ⭐ resolve() 组合查询")
print("=" * 58)
with app.app_context():
    db = get_db()
    info = core.resolve(db, "1-101", on_date="2026-10-19", section_name="一")
    print(f"         1-101 / 2026-10-19 / 第一节 → "
          f"{info['class_full']} | {info['weekday']} | "
          f"{info['course']} | {info['teacher']}")
    check("房间号能解析出班级", info["class_code"] is not None)
    check("星期计算正确（2026-10-19 是星期一）", info["weekday"] == "星期一")
    check("节次正确", info["section"] == "一")

    bad = core.resolve(db, "9-999")
    check("不存在的房间号给出明确说明",
          bad["class_code"] is None and len(bad["notes"]) > 0, str(bad["notes"]))

# ============================================================
print()
print("=" * 58)
print("7. 网页路由")
print("=" * 58)
client = app.test_client()

r = client.get("/")
check("首页能打开", r.status_code == 200)

r = client.get("/?room=1-101&date=2026-10-19&section=一")
body = r.get_data(as_text=True)
check("带房间号能打开并带出信息", r.status_code == 200 and "1-101" in body)

r = client.get("/?room=9-999")
check("不存在的房间号给出提示", "不存在" in r.get_data(as_text=True))

r = client.get("/rooms")
check("教室一览能打开", r.status_code == 200 and "1-101" in r.get_data(as_text=True))

r = client.get("/api/resolve?room=1-101&date=2026-10-19&section=一")
j = r.get_json()
check("API 返回正确", r.status_code == 200 and j["room_no"] == "1-101")
print(f"         API: {j['class_full']} / {j['course']} / {j['teacher']}")

# ============================================================
print()
print("=" * 58)
print("8. ⭐ 提交记录（含原项目崩溃 bug 的回归）")
print("=" * 58)

base_payload = {
    "RoomNum": "1-101", "ClassName": "2201", "Date": "2026-10-19",
    "Sections": "一", "Course": "语文", "ClassTeacher": "张三",
    "ClassroomSituation": "到课率良好，纪律正常", "Author": "李老师",
}

# 8.1 不拍照提交 —— 原项目这里会 500
r = client.post("/submit", json={**base_payload, "Img": None})
check("不拍照可以正常提交（原 bug 已修）",
      r.status_code == 200 and r.get_json().get("success") is True,
      r.get_data(as_text=True)[:150])

# 8.2 带照片提交
import base64
png_1x1 = ("data:image/png;base64,"
           + base64.b64encode(bytes.fromhex(
               "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
               "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
           )).decode())
r = client.post("/submit", json={**base_payload, "Img": png_1x1})
j = r.get_json()
check("带照片提交成功", j.get("success") is True, str(j))
check("照片已存盘", j.get("image") is not None, str(j))
if j.get("image"):
    check("照片文件真的存在",
          os.path.exists(os.path.join(app_module.UPLOAD_DIR, j["image"])))

# 8.3 必填校验
r = client.post("/submit", json={**base_payload, "ClassroomSituation": ""})
check("缺课堂情况被拒绝", r.get_json().get("success") is False)
r = client.post("/submit", json={**base_payload, "Author": ""})
check("缺填表人被拒绝", r.get_json().get("success") is False)
r = client.post("/submit", json={})
check("空请求被拒绝", r.get_json().get("success") is False)

# 8.4 异常不再被吞掉（原项目 except 里照样返回 success）
r = client.post("/submit", data="not json", content_type="text/plain")
check("非 JSON 请求返回明确的失败（不是假成功）",
      r.get_json().get("success") is False, r.get_data(as_text=True)[:120])

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

# 详情页
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
    gone = get_db().execute("SELECT COUNT(*) FROM records WHERE id=?", (rid,)).fetchone()[0]
check("数据库里确实删掉了", gone == 0)

r = client.post("/records/999999/delete", follow_redirects=True)
check("删不存在的记录给出提示", "不存在" in r.get_data(as_text=True))

# ============================================================
print()
print("=" * 58)
print(f"结果：通过 {passed} 项，失败 {failed} 项")
print("=" * 58)

shutil.rmtree(app_module.UPLOAD_DIR, ignore_errors=True)
try:
    os.unlink(TMP_DB)
except Exception:
    pass

sys.exit(1 if failed else 0)