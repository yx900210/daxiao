import argparse
import datetime
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import init_db, SessionLocal
from backend.models import ScrapeLog
from backend.scraper import scrape_profile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("daxiao")


async def do_scrape():
    init_db()
    db = SessionLocal()
    log_entry = ScrapeLog(started_at=datetime.datetime.utcnow(), status="running")
    db.add(log_entry)
    db.commit()
    log_id = log_entry.id
    db.close()

    try:
        total, new = await scrape_profile()
        db = SessionLocal()
        entry = db.get(ScrapeLog, log_id)
        entry.finished_at = datetime.datetime.utcnow()
        entry.total_videos = total
        entry.new_videos = new
        entry.status = "success"
        db.commit()
        db.close()
        logger.info(f"抓取完成: 总计{total}, 新增{new}")
    except Exception as e:
        logger.error(f"抓取异常: {e}")
        db = SessionLocal()
        entry = db.get(ScrapeLog, log_id)
        entry.finished_at = datetime.datetime.utcnow()
        entry.status = "failed"
        entry.error_msg = str(e)
        db.commit()
        db.close()


def main():
    parser = argparse.ArgumentParser(description="李大霄视频追踪系统")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("scrape", help="触发一次抓取")
    sub.add_parser("init-db", help="初始化数据库")
    sub.add_parser("serve", help="启动 Web 服务")

    args = parser.parse_args()

    if args.command == "scrape":
        import asyncio
        asyncio.run(do_scrape())
    elif args.command == "init-db":
        init_db()
        logger.info("数据库初始化完成")
    elif args.command == "serve":
        logger.info("Web 服务暂未实现")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
