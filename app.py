"""
app.py —— 巡课系统主程序（网页路由）

流程串联：
  扫码/访问 /?room=1-101  →  自动带出班级、节次、课程、教师
                          →  巡检员填课堂情况、拍照
                          →  POST /submit 存库
                          →  /records 查看所有记录
"""

import base64
import os
import uuid
from datetime import date, datetime

from flask import (Flask, flash, g, jsonify, redirect, render_template,
                   request, url_for)

import core
from db import close_db, db_exists, get_db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "xunke-dev-key")

# 上传的照片存这里
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp"}


@app.teardown_appcontext
def _close_db(e=None):
    close_db(e)


@app.context_processor
def inject_globals():
    """给所有模板塞一些公共变量"""
    return {
        "today": date.today().isoformat(),
        "now": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


@app.before_request
def check_db():
    """数据库不存在时，明确告诉用户先导入数据，而不是抛一堆看不懂的错。"""
    if not db_exists() and request.endpoint not in ("static",):
        return render_template("no_db.html"), 503


# ============================================================
# 一、首页：扫码进来的巡课填表页
# ============================================================

@app.route("/")
def home():
    db = get_db()
    room_no = (request.args.get("room") or request.args.get("id") or "").strip()
    on_date = (request.args.get("date") or "").strip() or None
    section = (request.args.get("section") or "").strip() or None

    ctx = {
        "room_no": room_no,
        "class_code": "", "class_full": "", "weekday": "",
        "section": "", "section_seq": None,
        "course": "", "teacher": "",
        "patrol_date": on_date or date.today().isoformat(),
        "notes": [],
        "sections": core.all_sections(db),
        "error": None,
    }

    if room_no:
        info = core.resolve(db, room_no, on_date=on_date, section_name=section)
        ctx.update({
            "class_code": info["class_code"] or "",
            "class_full": info["class_full"] or "",
            "weekday": info["weekday"] or "",
            "section": info["section"] or "",
            "section_seq": info["section_seq"],
            "course": info["course"] or "",
            "teacher": info["teacher"] or "",
            "patrol_date": info["date"] or ctx["patrol_date"],
            "notes": info["notes"],
        })
        if info["class_code"] is None:
            ctx["error"] = f"房间号「{room_no}」不存在，请检查二维码是否正确"

    return render_template("index.html", **ctx)


# ============================================================
# 二、提交巡课记录
# ============================================================

def save_image(data_url):
    """把前端传来的 base64 图片存成文件，返回文件名。

    原项目在这里有个崩溃 bug：Img 为空/None 时直接 .split()，
    所以没拍照就提交会 500。这里先判空。
    """
    if not data_url or not isinstance(data_url, str):
        return None
    if "," not in data_url:
        return None
    head, b64 = data_url.split(",", 1)
    if "base64" not in head:
        return None
    try:
        raw = base64.b64decode(b64)
    except Exception:
        return None
    if not raw:
        return None
    ext = ".png"
    for e in ALLOWED_EXT:
        if e.strip(".") in head.lower():
            ext = e
            break
    name = f"{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(raw)
    return name


@app.route("/submit", methods=["POST"])
def submit():
    """接收前端 JSON，写入数据库。"""
    try:
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "error": "没有收到数据"}), 400

        # --- 必填校验：缺什么就明确告诉前端缺什么 ---
        # 注意：字段名必须和前端 index.html 里 payload 的键完全一致
        required = {
            "RoomNum": "房间号",
            "ClassroomSituation": "课堂情况",
            "Author": "填表人",
        }
        missing = [label for key, label in required.items()
                   if not str(data.get(key, "")).strip()]
        if missing:
            return jsonify({"success": False,
                            "error": "请填写：" + "、".join(missing)}), 400

        img_name = save_image(data.get("Img"))

        rid = core.insert_record(get_db(), {
            "room_no": str(data.get("RoomNum", "")).strip(),
            "class_code": str(data.get("ClassName", "")).strip(),
            "class_name": str(data.get("ClassName", "")).strip(),
            "patrol_date": str(data.get("Date", "")).strip(),
            "section": str(data.get("Sections", "")).strip(),
            "course": str(data.get("Course", "")).strip(),
            "teacher": str(data.get("ClassTeacher", "")).strip(),
            "situation": str(data.get("ClassroomSituation", "")).strip(),
            "author": str(data.get("Author", "")).strip(),
        }, image_path=img_name)

        return jsonify({"success": True, "id": rid, "image": img_name})

    except Exception as e:
        # 不要把异常吞掉还报 success —— 原项目就是这么干的，出了问题根本查不到
        return jsonify({"success": False, "error": f"服务器错误：{e}"}), 500


# ============================================================
# 三、巡课记录查看页（原项目完全缺失的功能）
# ============================================================

@app.route("/records")
def records():
    db = get_db()
    room_no = (request.args.get("room") or "").strip()
    on_date = (request.args.get("date") or "").strip()
    author = (request.args.get("author") or "").strip()

    rows = core.query_records(db, room_no=room_no or None,
                              on_date=on_date or None,
                              author=author or None,
                              limit=300)
    return render_template("records.html", records=rows,
                           stats=core.record_stats(db),
                           f_room=room_no, f_date=on_date, f_author=author)


@app.route("/records/<int:rid>")
def record_detail(rid):
    row = get_db().execute("SELECT * FROM records WHERE id = ?", (rid,)).fetchone()
    if row is None:
        flash("记录不存在", "error")
        return redirect(url_for("records"))
    return render_template("record_detail.html", r=row)


@app.route("/records/<int:rid>/delete", methods=["POST"])
def record_delete(rid):
    db = get_db()
    cur = db.execute("DELETE FROM records WHERE id = ?", (rid,))
    db.commit()
    flash("已删除" if cur.rowcount else "记录不存在",
          "success" if cur.rowcount else "error")
    return redirect(url_for("records"))


# ============================================================
# 四、教室一览（管理员看哪个教室对着哪个班）
# ============================================================

@app.route("/rooms")
def rooms():
    return render_template("rooms.html", rooms=core.list_rooms(get_db()))


# ============================================================
# 五、接口：给二维码 / 前端用
# ============================================================

@app.route("/api/resolve")
def api_resolve():
    """按房间号+日期+节次查信息，返回 JSON。"""
    db = get_db()
    room_no = (request.args.get("room") or "").strip()
    if not room_no:
        return jsonify({"ok": False, "error": "缺少 room 参数"}), 400
    info = core.resolve(db, room_no,
                        on_date=(request.args.get("date") or "").strip() or None,
                        section_name=(request.args.get("section") or "").strip() or None)
    info["ok"] = info["class_code"] is not None
    return jsonify(info)


@app.route("/uploads/<path:name>")
def uploaded(name):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_DIR, name)


if __name__ == "__main__":
    if not db_exists():
        print("！数据库不存在，请先运行：python import_data.py")
    else:
        print("巡课系统已启动：http://127.0.0.1:5001")
    app.run(debug=True, port=5001)