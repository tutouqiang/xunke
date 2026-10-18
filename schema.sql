-- 巡课系统数据库结构（SQLite）
-- 数据来源：桌面 xunke1.2 文件夹里的三个 Excel，由 import_data.py 一次性导入

-- 表1：教室 ↔ 班级 对应表（原 ClassDistribution.xlsx）
CREATE TABLE IF NOT EXISTS rooms (
    room_no    TEXT PRIMARY KEY,   -- 房间号，如 1-101
    class_code TEXT NOT NULL       -- 班级代码，如 2201
);

-- 表2：节次时间表（原 ClassSections.xlsx）
-- 时间统一存成"从 0 点开始的分钟数"，比如 08:00 → 480，比较大小最方便
CREATE TABLE IF NOT EXISTS sections (
    seq           INTEGER PRIMARY KEY,  -- 1~8，第几节
    name          TEXT NOT NULL,        -- 一 二 三 ... 八
    start_min     INTEGER NOT NULL,     -- 普通日 开始时间（分钟）
    end_min       INTEGER NOT NULL,     -- 普通日 结束时间（分钟）
    fri_start_min INTEGER,              -- 周五 开始时间（分钟），可能为 NULL
    fri_end_min   INTEGER               -- 周五 结束时间（分钟），可能为 NULL
);

-- 表3：课程表（原 ClassTable.xlsx）
-- 2400 行，记录了"哪个班 + 星期几 + 第几节 → 上什么课、谁教"
CREATE TABLE IF NOT EXISTS schedule (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    class_code TEXT NOT NULL,      -- 班级代码，如 2301
    class_full TEXT,               -- 班级全名，如 2301普职融通机械
    weekday    TEXT NOT NULL,      -- 星期一 ... 星期日
    section    TEXT NOT NULL,      -- 一 ... 八
    course     TEXT,               -- 课程名
    teacher    TEXT                -- 任课教师
);

-- 这条索引是性能关键：查课永远是这个三件套组合
CREATE INDEX IF NOT EXISTS idx_schedule_lookup
    ON schedule (class_code, weekday, section);

-- 表4：巡课记录（原 MySQL 的 xunke_table，这是业务核心表）
CREATE TABLE IF NOT EXISTS records (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    room_no     TEXT NOT NULL,      -- 房间号
    class_code  TEXT,               -- 班级代码
    class_name  TEXT,               -- 班级显示名
    patrol_date TEXT NOT NULL,      -- 巡课日期 2026-10-18
    section     TEXT,               -- 节次
    course      TEXT,               -- 课程
    teacher     TEXT,               -- 任课教师
    situation   TEXT,               -- 课堂情况（巡检员填写）
    author      TEXT,               -- 填表人
    image_path  TEXT,               -- 现场照片文件名
    created_at  TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE INDEX IF NOT EXISTS idx_records_date ON records (patrol_date DESC);
CREATE INDEX IF NOT EXISTS idx_records_room ON records (room_no);