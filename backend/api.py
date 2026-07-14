import datetime
import logging
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from backend.database import get_db, init_db
from backend.models import Video, Subtitle, BonsaiScreenshot, VideoResult, ScrapeLog, Setting

logger = logging.getLogger(__name__)

app = FastAPI(title="李大霄视频追踪", version="0.1.0")


@app.on_event("startup")
def startup():
    import os as _os
    from backend.config import SCREENSHOTS_DIR, DATA_DIR, DOUYIN_COOKIE, PLAYWRIGHT_PROXY
    _os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    _os.makedirs(_os.path.join(DATA_DIR, "videos"), exist_ok=True)
    init_db()

    db = next(get_db())
    defaults = {
        "douyin_cookie": DOUYIN_COOKIE,
        "http_proxy": PLAYWRIGHT_PROXY or "http://nas.900210.top:53128",
    }
    for k, v in defaults.items():
        if not db.query(Setting).get(k):
            db.add(Setting(key=k, value=v or ""))
    db.commit()
    db.close()


# ── Dashboard ──────────────────────────────────────────

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    total = db.query(Video).count()
    done = db.query(Video).filter(Video.fetch_status == "done").count()
    processing = db.query(Video).filter(Video.fetch_status.in_(["pending", "processing", "screenshotted"])).count()
    latest = db.query(Video).order_by(Video.publish_time.desc()).first()
    last_scrape = db.query(ScrapeLog).filter(ScrapeLog.status == "success").order_by(ScrapeLog.id.desc()).first()

    return {
        "total_videos": total,
        "processed": done,
        "pending": processing,
        "latest_video": {
            "title": latest.title if latest else None,
            "publish_time": latest.publish_time.isoformat() if latest and latest.publish_time else None,
        } if latest else None,
        "last_scrape": last_scrape.finished_at.isoformat() if last_scrape and last_scrape.finished_at else None,
    }


@app.get("/api/videos")
def list_videos(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    status: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Video)
    if status:
        q = q.filter(Video.fetch_status == status)
    q = q.order_by(Video.publish_time.desc())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": v.id,
                "douyin_video_id": v.douyin_video_id,
                "title": v.title,
                "cover_url": v.cover_url,
                "publish_time": v.publish_time.isoformat() if v.publish_time else None,
                "duration": v.duration,
                "like_count": v.like_count,
                "comment_count": v.comment_count,
                "share_count": v.share_count,
                "fetch_status": v.fetch_status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in items
        ],
    }


@app.get("/api/videos/{video_id}")
def get_video(video_id: int, db: Session = Depends(get_db)):
    v = db.query(Video).get(video_id)
    if not v:
        raise HTTPException(404, "视频不存在")

    result = db.query(VideoResult).filter(VideoResult.video_id == video_id).first()
    subs = db.query(Subtitle).filter(Subtitle.video_id == video_id).order_by(Subtitle.frame_index).all()
    bonsai = db.query(BonsaiScreenshot).filter(BonsaiScreenshot.video_id == video_id).first()

    return {
        "id": v.id,
        "douyin_video_id": v.douyin_video_id,
        "title": v.title,
        "cover_url": v.cover_url,
        "publish_time": v.publish_time.isoformat() if v.publish_time else None,
        "duration": v.duration,
        "like_count": v.like_count,
        "comment_count": v.comment_count,
        "share_count": v.share_count,
        "fetch_status": v.fetch_status,
        "error_msg": v.error_msg,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "result": {
            "full_subtitle": result.full_subtitle if result else None,
            "stock_summary": result.stock_summary if result else None,
            "stock_keywords": result.stock_keywords if result else None,
            "stock_sentiment": result.stock_sentiment if result else None,
            "bonsai_summary": result.bonsai_summary if result else None,
            "processed_at": result.processed_at.isoformat() if result and result.processed_at else None,
        },
        "subtitles": [
            {"frame_index": s.frame_index, "timestamp": s.frame_timestamp, "text": s.raw_text}
            for s in subs
        ],
        "bonsai": {
            "screenshot_path": bonsai.screenshot_path if bonsai else None,
            "record_time": bonsai.record_time if bonsai else None,
            "species": bonsai.species if bonsai else None,
            "description": bonsai.description if bonsai else None,
            "meaning": bonsai.meaning if bonsai else None,
        } if bonsai else None,
    }


@app.get("/api/scrape/logs")
def scrape_logs(db: Session = Depends(get_db)):
    logs = db.query(ScrapeLog).order_by(ScrapeLog.started_at.desc()).limit(20).all()
    return {
        "items": [
            {
                "id": l.id,
                "started_at": l.started_at.isoformat() if l.started_at else None,
                "finished_at": l.finished_at.isoformat() if l.finished_at else None,
                "total_videos": l.total_videos,
                "new_videos": l.new_videos,
                "status": l.status,
                "error_msg": l.error_msg,
            }
            for l in logs
        ]
    }


@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db)):
    rows = db.query(Setting).all()
    return {r.key: r.value for r in rows}


@app.put("/api/settings/{key}")
def update_setting(key: str, body: dict, db: Session = Depends(get_db)):
    row = db.query(Setting).get(key)
    if not row:
        raise HTTPException(404, "设置项不存在")
    row.value = body.get("value", "")
    db.commit()
    return {"ok": True, "key": key, "value": row.value}


@app.post("/api/reset")
def reset_all():
    import shutil
    import os as _os
    from backend.config import SCREENSHOTS_DIR, DATA_DIR, DB_PATH, DOUYIN_COOKIE, PLAYWRIGHT_PROXY
    from backend.database import engine

    engine.dispose()
    try:
        _os.remove(DB_PATH)
    except FileNotFoundError:
        pass
    if _os.path.exists(SCREENSHOTS_DIR):
        shutil.rmtree(SCREENSHOTS_DIR)
    vdir = _os.path.join(DATA_DIR, "videos")
    if _os.path.exists(vdir):
        shutil.rmtree(vdir)
    cf = _os.path.join(DATA_DIR, "cookies.json")
    if _os.path.exists(cf):
        _os.remove(cf)
    init_db()

    db = next(get_db())
    defaults = {
        "douyin_cookie": DOUYIN_COOKIE,
        "http_proxy": PLAYWRIGHT_PROXY or "http://nas.900210.top:53128",
    }
    for k, v in defaults.items():
        if not db.query(Setting).get(k):
            db.add(Setting(key=k, value=v or ""))
    db.commit()
    db.close()

    return {"ok": True, "msg": "所有数据已清空，数据库已重建"}


@app.post("/api/scrape/trigger")
def trigger_scrape():
    from backend.scraper import scrape_profile
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        total, new = loop.run_until_complete(scrape_profile())
        if new > 0:
            _start_process_background()
        return {"ok": True, "total": total, "new": new}
    except Exception as e:
        logger.error(f"手动抓取失败: {e}")
        return {"ok": False, "error": str(e)}
    finally:
        loop.close()


@app.post("/api/process/pending")
def process_pending():
    _start_process_background()
    return {"ok": True, "msg": "处理任务已在后台启动"}


def _start_process_background():
    import threading

    def _run():
        import asyncio as _asyncio
        from backend.processor import process_video
        from backend.database import SessionLocal
        from backend.models import Video

        db = SessionLocal()
        pending = db.query(Video.id).filter(
            Video.fetch_status.in_(["pending", "screenshotted"])
        ).all()
        db.close()

        pending_ids = [row[0] for row in pending]
        total = len(pending_ids)
        logger.info(f"[后台处理] 发现 {total} 个待处理视频")

        for i, vid in enumerate(pending_ids):
            logger.info(f"[后台处理] ({i+1}/{total}) 开始处理视频 id={vid}")
            try:
                loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(loop)
                ok = loop.run_until_complete(process_video(vid))
                loop.close()
                logger.info(f"[后台处理] ({i+1}/{total}) id={vid} {'成功' if ok else '失败'}")
            except Exception as e:
                logger.error(f"[后台处理] ({i+1}/{total}) id={vid} 异常: {e}")

        logger.info("[后台处理] ====== 全部完成 ======")

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@app.post("/api/videos/{video_id}/reprocess")
def reprocess_video(video_id: int):
    import asyncio
    from backend.processor import process_video

    loop = asyncio.new_event_loop()
    try:
        ok = loop.run_until_complete(process_video(video_id))
        return {"ok": ok}
    finally:
        loop.close()


# ── Screenshot static files ────────────────────────────

import os as _os
from backend.config import SCREENSHOTS_DIR, BASE_DIR, DATA_DIR

_os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
_os.makedirs(_os.path.join(DATA_DIR, "videos"), exist_ok=True)

app.mount("/screenshots", StaticFiles(directory=_os.path.abspath(SCREENSHOTS_DIR)), name="screenshots")

_frontend_dist = _os.path.join(BASE_DIR, "frontend", "dist")
if _os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=_os.path.join(_frontend_dist, "assets")), name="assets")

    from fastapi.responses import FileResponse
    from fastapi import Request

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str, request: Request):
        path = _os.path.join(_frontend_dist, full_path) if full_path else _frontend_dist
        if _os.path.isfile(path):
            return FileResponse(path)
        return FileResponse(_os.path.join(_frontend_dist, "index.html"))
