import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from backend.config import CRON_SCHEDULE

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone="Asia/Shanghai")


def _run_scrape():
    import asyncio
    from backend.scraper import scrape_profile
    from backend.database import SessionLocal, init_db
    from backend.models import ScrapeLog
    import datetime

    init_db()
    db = SessionLocal()
    log_entry = ScrapeLog(started_at=datetime.datetime.utcnow(), status="running")
    db.add(log_entry)
    db.commit()
    log_id = log_entry.id
    db.close()

    try:
        loop = asyncio.new_event_loop()
        total, new = loop.run_until_complete(scrape_profile())
        loop.close()

        db = SessionLocal()
        entry = db.get(ScrapeLog, log_id)
        entry.finished_at = datetime.datetime.utcnow()
        entry.total_videos = total
        entry.new_videos = new
        entry.status = "success"
        db.commit()
        db.close()
        logger.info(f"[定时] 抓取完成: 总计{total}, 新增{new}")
    except Exception as e:
        logger.error(f"[定时] 抓取失败: {e}")
        db = SessionLocal()
        entry = db.get(ScrapeLog, log_id)
        entry.finished_at = datetime.datetime.utcnow()
        entry.status = "failed"
        entry.error_msg = str(e)
        db.commit()
        db.close()


def start_scheduler():
    if scheduler.running:
        return

    cron_parts = CRON_SCHEDULE.strip().split()
    if len(cron_parts) == 5:
        trigger = CronTrigger(
            minute=cron_parts[0],
            hour=cron_parts[1],
            day=cron_parts[2],
            month=cron_parts[3],
            day_of_week=cron_parts[4],
            timezone="Asia/Shanghai",
        )
    else:
        trigger = CronTrigger(hour=9, minute=0, timezone="Asia/Shanghai")

    scheduler.add_job(_run_scrape, trigger=trigger, id="daily_scrape", name="每日抓取")
    scheduler.start()
    logger.info(f"定时任务已启动: {CRON_SCHEDULE}")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
