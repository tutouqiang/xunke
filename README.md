# 巡课系统

教室巡课记录 Web 应用。扫码 → 自动带出课堂信息 → 填写情况 + 拍照 → 提交 → 后台可查。

## 功能

| 页面 | 说明 |
|------|------|
| **巡课** `/` | 输入/扫码带出房间号，自动显示班级、节次、课程、任课教师；填课堂情况、拍照、提交 |
| **巡课记录** `/records` | 查看/筛选所有巡课记录（按房间号、日期、填表人），可查看详情、删除 |
| **教室一览** `/rooms` | 60 间教室与班级的对应关系，可一键发起巡课 |
| **接口** `/api/resolve` | 按房间号+日期+节次返回 JSON，供二维码/其他系统调用 |

## 快速开始

```bash
# 1. 装依赖（只有两个）
pip install -r requirements.txt

# 2. 从 Excel 导入数据（只需跑一次）
python import_data.py

# 3. 启动
python app.py
#    浏览器打开 http://127.0.0.1:5001
```

## 运行测试

```bash
python smoke_test.py     # 46 项断言
```

## 技术栈

- **后端**：Python 3 + Flask
- **数据库**：SQLite（无需安装、无需配置、无需密码）
- **前端**：原生 HTML/CSS/JavaScript，移动端优先（巡检员用手机）

## 项目结构

```
xunke/
├── app.py               # 主程序：所有网页路由
├── core.py              # 核心业务逻辑（查课、排节次、组合解析）
├── db.py                # 数据库连接
├── import_data.py       # Excel → SQLite 一次性导入
├── schema.sql           # 数据库表结构
├── smoke_test.py        # 冒烟测试
├── requirements.txt
├── templates/
│   ├── base.html        #   公共骨架
│   ├── index.html       #   巡课填表页（含摄像头拍照）
│   ├── records.html     #   记录列表
│   ├── record_detail.html #  记录详情
│   ├── rooms.html       #   教室一览
│   └── no_db.html       #   未初始化提示
├── static/style.css
└── uploads/             # 现场照片存放处（自动创建）
```

## 数据库设计

四张表：

```
rooms     教室号 → 班级           (60 条)
sections  节次 → 起止时间          (8 条，含周五单独作息)
schedule  班级 + 星期 + 节次 → 课程/教师  (2400 条)
records   巡课记录（业务核心表）
```

关键索引：`schedule(class_code, weekday, section)` —— 查课永远是这三个条件的组合。

## 本地开发提示

**二维码怎么生成**：教室门口贴的二维码，内容就是

```
http://<服务器地址>:5001/?room=1-101
```

把 `1-101` 换成对应房间号即可。巡检员扫码后打开页面，房间号自动带出。

**拍照说明**：手机浏览器访问时才能用摄像头（需要 HTTPS 或 localhost）。
用电脑测试时没有摄像头，可跳过拍照直接提交。

## 数据来源

本系统的教室、节次、课程表来自 `xunke1.2` 文件夹里的三个 Excel：

- `ClassDistribution.xlsx` → 教室对应表（60 条）
- `ClassSections.xlsx` → 节次时间表（8 条）
- `ClassTable.xlsx` → 课程表（2400 条）

一次性导入后，程序运行**不再需要这几个 Excel**。
每学年课表更新时，替换 Excel 重新跑一次 `python import_data.py` 即可。

⚠️ `import_data.py` 会**重建数据库**，已有的巡课记录会被清空。
正式使用后要更新课表，请先备份 `xunke.db` 里的 `records` 表。