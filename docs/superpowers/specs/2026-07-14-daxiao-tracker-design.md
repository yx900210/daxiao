# 李大霄视频追踪系统 — 设计文档

> 日期: 2026-07-14 | 状态: 设计中

## 概述

每日低频抓取抖音大V李大霄主页，增量获取新视频，通过间隔截图 → OCR字幕 → VL盆景识别 → LLM观点总结，归档到 SQLite 数据库，并提供 Web 面板浏览。

**运行环境**: Debian 13 服务器 + 1panel 运维面板  
**架构模式**: 单体 Python 应用（FastAPI + APScheduler）

---

## 一、数据获取

### 1.1 抓取方式

Playwright 模拟移动端浏览器自动化抓取抖音主页。

**流程:**
1. 启动 Chromium，iPhone UA 伪装
2. 进入李大霄主页，等待视频列表渲染，滚动加载更多
3. 解析 DOM 提取视频元信息（douyin_video_id, title, cover_url, publish_time, statistics）
4. 与数据库 `videos` 表比对，筛出新增视频
5. 逐个访问视频详情页，触发播放，拦截 `.mp4` 流地址下载至 `data/videos/`
6. 写入 `videos` 表（fetch_status='pending'），记录 `scrape_logs`

**反爬策略:**
- 请求间隔 2-5 秒随机延迟
- Cookie/Session 持久化复用
- 失败自动重试 3 次，指数退避
- 支持可配置代理

### 1.2 抓取触发方式

- 定时: APScheduler，默认每日 09:00
- 手动: Web 面板 API `POST /api/scrape/trigger`

---

## 二、视频处理管线

### 2.1 截图抽帧

用 OpenCV 读取下载的视频文件，按配置间隔（默认 2 秒）抽帧。

每帧产出三份截图:

| 区域 | 裁剪定义 | 用途 |
|---|---|---|
| 完整画面 | 原图 | 存档 `frames` 表 |
| 底部 20% | `(0, h*0.80, w, h)` | OCR 字幕识别 |
| 右侧中上部 | 仅截第 10 秒一帧, 可配置裁剪区 | 盆景识别 + 录制时间提取 |

截图存储路径: `data/screenshots/{video_id}/{type}/frame_{n}.jpg`

### 2.2 字幕 OCR

- 引擎: PaddleOCR（本地离线, 中文识别最优）
- 输入: 底部裁剪截图序列
- 输出: 逐帧 OCR 文本 + 置信度 → `subtitles` 表
- 去重: 相邻帧编辑距离/相似度 > 0.8 视为重复，合并
- 拼接: 去重后按时间序拼接为完整字幕文本

### 2.3 盆景识别（修正设计）

仅截取视频第 10 秒一帧，对右侧中上部区域做两次处理:

**第一轮 — 通义千问 VL（多模态）:**
- 输入: 盆景区域截图
- 输出: 盆景品种、状态、整体场景描述、录制时间文本（形如 "2026年7月14日 12:06"）

**第二轮 — DeepSeek / 通义千问（纯文本）:**
- 输入: 第一轮输出的品种 + 场景描述
- 输出: 寓意解读

结果写入 `bonsai_screenshots` 表。

### 2.4 股市观点总结

- 输入: 完整字幕文本 + 盆景识别结果汇总
- 模型: DeepSeek API（纯文本, 推理能力强）
- 提示词要求输出: 股市核心观点、关键标签（JSON 数组）、多空情绪
- 结果写入 `video_results` 表

### 模型分工总览

| 任务 | 模型 | 部署方式 |
|---|---|---|
| 字幕 OCR | PaddleOCR | 本地离线 |
| 盆景识别 + 时间提取 | 通义千问 VL API | 云端 API |
| 寓意解读 | DeepSeek API | 云端 API |
| 股市观点总结 | DeepSeek API | 云端 API |

---

## 三、数据库设计

### 3.1 表结构

**videos（视频主表）**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增 |
| douyin_video_id | VARCHAR(64) UNIQUE | 抖音视频唯一ID |
| title | TEXT | 视频标题 |
| cover_url | TEXT | 封面图URL |
| publish_time | DATETIME | 抖音发布时间 |
| duration | REAL | 视频时长(秒) |
| like_count | INTEGER | 点赞数 |
| comment_count | INTEGER | 评论数 |
| share_count | INTEGER | 分享数 |
| local_video_path | TEXT | 本地视频路径 |
| fetch_status | VARCHAR(16) | pending/screenshotted/processed/done/failed |
| error_msg | TEXT | 失败原因 |
| created_at | DATETIME | 记录创建时间 |

**frames（全帧截图表）**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| video_id | INTEGER FK→videos | |
| frame_index | INTEGER | 帧序号 |
| frame_timestamp | REAL | 视频内时间点(秒) |
| full_screenshot | TEXT | 完整截图路径 |
| created_at | DATETIME | |
| UNIQUE(video_id, frame_index) | | |

**subtitles（字幕OCR表）**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| video_id | INTEGER FK→videos | |
| frame_index | INTEGER | 帧序号 |
| frame_timestamp | REAL | 视频内时间点(秒) |
| screenshot_path | TEXT | 字幕区域截图路径 |
| raw_text | TEXT | OCR原始识别文本 |
| confidence | REAL | OCR平均置信度 |
| created_at | DATETIME | |
| UNIQUE(video_id, frame_index) | | |

**bonsai_screenshots（盆景识别表）**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| video_id | INTEGER FK→videos | |
| frame_index | INTEGER | 固定为第10秒对应帧 |
| frame_timestamp | REAL | 视频内时间点(秒) |
| screenshot_path | TEXT | 盆景区域截图路径 |
| record_time | TEXT | 识别出的录制时间 |
| species | TEXT | 盆景品种 |
| description | TEXT | 通义千问VL场景描述 |
| meaning | TEXT | DeepSeek寓意解读 |
| created_at | DATETIME | |
| UNIQUE(video_id, frame_index) | | |

**video_results（视频总结表）**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| video_id | INTEGER UNIQUE FK→videos | |
| full_subtitle | TEXT | 完整拼接字幕 |
| subtitle_word_count | INTEGER | 字幕总字数 |
| stock_summary | TEXT | 股市核心观点总结 |
| stock_keywords | TEXT | 关键标签(JSON数组) |
| stock_sentiment | VARCHAR(8) | 多/空/中性 |
| bonsai_summary | TEXT | 盆景寓意汇总 |
| llm_model | VARCHAR(32) | 使用的总结模型 |
| vl_model | VARCHAR(32) | 使用的视觉模型 |
| processed_at | DATETIME | 处理完成时间 |
| created_at | DATETIME | |

**scrape_logs（抓取日志表）**
| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| started_at | DATETIME | 开始时间 |
| finished_at | DATETIME | 结束时间 |
| total_videos | INTEGER | 主页总视频数 |
| new_videos | INTEGER | 本次新增 |
| status | VARCHAR(16) | running/success/failed |
| error_msg | TEXT | 错误信息 |
| created_at | DATETIME | |

---

## 四、Web 面板

### 4.1 技术栈

- 前端: Vue 3 + Vite
- 后端: FastAPI（同时托管前端构建产物）
- 构建产物由 Vite 输出至 `frontend/dist/`，FastAPI 挂载为静态文件

### 4.2 页面

**Dashboard (`/`)**
- 统计卡片: 总视频、已处理、本周新增、最新情绪
- 视频时间线列表（分页）: 封面、标题、时间、状态标签
- 手动触发按钮 + 上次抓取时间
- 状态标签: pending(灰) / processing(蓝) / done(绿) / failed(红)

**Detail (`/video/:id`)**
- 视频信息区: 标题、时间、互动数据
- 字幕区: 完整拼接文本，可展开查看逐帧 OCR
- 盆景区: 截图 + 品种 + 场景描述 + 寓意解读 + 录制时间
- 观点区: 股市观点 + 关键词标签 + 情绪
- 元信息: 处理时间、模型信息

### 4.3 API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/videos | 视频列表（分页, 状态筛选） |
| GET | /api/videos/:id | 视频详情（含所有关联数据） |
| POST | /api/scrape/trigger | 手动触发抓取 |
| POST | /api/videos/:id/reprocess | 重新处理单个视频 |
| GET | /api/scrape/logs | 抓取日志列表 |
| GET | /api/stats | 统计数据 |

---

## 五、部署

### 5.1 部署环境

- OS: Debian 13
- 面板: 1panel
- 运行时: Python 3.11+, Playwright + Chromium
- 磁盘: 建议 50G+ 用于视频/截图存储

### 5.2 部署目录

```
/opt/daxiao/
├── backend/           # Python 源码
├── frontend/dist/     # 前端构建产物
├── data/
│   ├── daxiao.db
│   ├── videos/
│   └── screenshots/{video_id}/{full,subtitle,bonsai}/
├── .env               # API Key、DSN 等
├── venv/
└── deploy/daxiao.service
```

### 5.3 systemd 服务

```
[Unit]
Description=Daxiao Tracker
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/daxiao
ExecStart=/opt/daxiao/venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port 8080
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### 5.4 初始化流程

1. 创建 Python venv + 安装依赖
2. `playwright install chromium --with-deps`
3. 初始化 SQLite（自动建表）
4. 构建前端 `npm run build`，复制 dist 到 backend 目录
5. 配置 `.env`
6. `systemctl enable --now daxiao`

### 5.5 项目结构

```
daxiao/
├── backend/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── models.py            # SQLAlchemy 模型
│   ├── scraper.py           # Playwright 抓取模块
│   ├── processor.py         # 截图/OCR/VL/LLM 管线
│   ├── scheduler.py         # APScheduler 定时任务
│   ├── api.py               # REST API
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.vue
│   │   ├── router/index.ts
│   │   ├── views/
│   │   │   ├── Dashboard.vue
│   │   │   └── Detail.vue
│   │   ├── components/
│   │   │   ├── VideoCard.vue
│   │   │   └── TriggerButton.vue
│   │   └── api.ts           # API 调用封装
│   ├── package.json
│   └── vite.config.js
├── data/                    # gitignore
├── deploy/
│   └── daxiao.service
├── .env.example
├── .gitignore
└── README.md
```

---

## 六、可配置参数

```python
# config.py 默认值
SCREENSHOT_INTERVAL = 2        # 抽帧间隔(秒)
BONSAI_FRAME_SECOND = 10       # 盆景截图的视频时间点(秒)
SUBTITLE_CROP_RATIO = (0.0, 0.80, 1.0, 1.0)   # 底部 20%
BONSAI_CROP_RATIO   = (0.70, 0.0, 1.0, 0.50)  # 右侧中上部
OCR_CONFIDENCE_MIN  = 0.7      # OCR 最低置信度
DEDUP_SIMILARITY    = 0.8      # 字幕去重相似度阈值
SCRAPE_DELAY_MIN    = 2        # 页面请求最小间隔(秒)
SCRAPE_DELAY_MAX    = 5
DOUYIN_PROFILE_URL  = ""       # 李大霄主页URL
CRON_SCHEDULE       = "0 9 * * *"  # 每天早9点
DASHSCOPE_API_KEY   = ""       # 通义千问VL
DEEPSEEK_API_KEY    = ""      # DeepSeek
```

---

## 七、设计决策记录

1. **为什么单体而非微服务**: 每日低频抓取，流量和并发极低，单体应用减少运维复杂度，1panel 一条命令即可管理。
2. **为什么 PaddleOCR 而非云端 OCR**: 屏幕字幕文本量大（每视频可达数百帧），云端 API 费用高且延迟累积严重，本地 PaddleOCR 零费用、低延迟。
3. **为什么盆景只截一帧**: 盆景画面通常固定不动，一帧足以完成识别，避免 API 浪费。
4. **为什么盆景识别拆分两步**: DeepSeek 不具备多模态能力，先用通义千问 VL 做视觉理解，再交由 DeepSeek 做深层次寓意推理。
5. **为什么用 systemd 而非 Docker**: 1panel 原生支持 systemd 管理，减少一层容器抽象，简化 Chromium 依赖安装。
