import asyncio
import json
import logging
import os
import random
import re
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Response

from backend.config import (
    DOUYIN_PROFILE_URL,
    VIDEOS_DIR,
    SCRAPE_DELAY_MIN,
    SCRAPE_DELAY_MAX,
    PAGE_SCROLL_COUNT,
    SCRAPE_TIMEOUT,
)
from backend.database import SessionLocal
from backend.models import Video, ScrapeLog

logger = logging.getLogger(__name__)


def _parse_aweme(aweme: dict) -> dict:
    statistics = aweme.get("statistics", {})
    video = aweme.get("video", {}) or {}
    duration = aweme.get("duration") or video.get("duration", 0)
    if isinstance(duration, (int, float)) and duration > 1000:
        duration = duration / 1000.0

    create_time = aweme.get("create_time")
    if isinstance(create_time, (int, float)):
        if create_time > 1000000000000:
            create_time = datetime.fromtimestamp(create_time / 1000.0)
        else:
            create_time = datetime.fromtimestamp(create_time)
    elif not create_time:
        try:
            aweme_id = int(aweme.get("aweme_id", "0"))
            ts = aweme_id >> 32
            create_time = datetime.fromtimestamp(ts)
        except (ValueError, OSError):
            pass

    return {
        "douyin_video_id": aweme.get("aweme_id", ""),
        "title": aweme.get("desc", ""),
        "cover_url": video.get("cover", {}).get("url_list", [""])[0] if video else "",
        "video_url": _extract_play_url(video),
        "publish_time": create_time,
        "duration": duration,
        "like_count": statistics.get("digg_count", 0),
        "comment_count": statistics.get("comment_count", 0),
        "share_count": statistics.get("share_count", 0),
    }


def _extract_play_url(video: dict) -> str:
    for key in ("play_addr_h264", "play_addr", "play_addr_265"):
        pa = video.get(key, {})
        urls = pa.get("url_list", []) if isinstance(pa, dict) else []
        for u in urls:
            if isinstance(u, str) and u.startswith("http"):
                return u
    return ""


def _parse_api_response(body: str) -> list[dict]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return []

    aweme_list = (
        data.get("aweme_list")
        or data.get("data", {}).get("aweme_list")
        or data.get("data", {}).get("list")
        or data.get("data", {})
    )
    if isinstance(aweme_list, dict):
        aweme_list = aweme_list.get("aweme_list") or aweme_list.get("list") or []
    if isinstance(data, list):
        aweme_list = data
    if not isinstance(aweme_list, list):
        aweme_list = []

    return [_parse_aweme(a) for a in aweme_list if isinstance(a, dict) and a.get("aweme_id")]


def _parse_ssr_html(html: str) -> list[dict]:
    results = []
    for pattern in [
        r'<script[^>]*id="RENDER_DATA"[^>]*type="application/json"[^>]*>([^<]+)</script>',
        r'<script[^>]*id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>([^<]+)</script>',
    ]:
        match = re.search(pattern, html)
        if match:
            from urllib.parse import unquote
            raw = unquote(match.group(1))
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                app = data.get("app", data)
                user_page = app.get("userPage", app)
                post_data = user_page.get("post", {})
                aweme_list = (
                    post_data.get("aweme", {}).get("post", [])
                    or post_data.get("post", [])
                    or []
                )
                for a in aweme_list:
                    if isinstance(a, dict):
                        aweme = a.get("aweme", a.get("aweme_info", a))
                        if aweme.get("aweme_id"):
                            try:
                                results.append(_parse_aweme(aweme))
                            except Exception:
                                pass
            break
    return results


def _db_add_videos(video_list: list[dict]) -> int:
    new_count = 0
    db = SessionLocal()
    try:
        for v in video_list:
            douyin_id = v.get("douyin_video_id", "").strip()
            if not douyin_id:
                continue
            exists = db.query(Video).filter(Video.douyin_video_id == douyin_id).first()
            if exists:
                continue
            db.add(Video(
                douyin_video_id=douyin_id,
                title=v.get("title", ""),
                cover_url=v.get("cover_url", ""),
                video_url=v.get("video_url", ""),
                publish_time=v.get("publish_time"),
                duration=v.get("duration", 0),
                like_count=v.get("like_count", 0),
                comment_count=v.get("comment_count", 0),
                share_count=v.get("share_count", 0),
                fetch_status="pending",
            ))
            new_count += 1
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return new_count


async def _random_delay():
    delay = random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX)
    await asyncio.sleep(delay)


async def _load_profile_page(page: Page, url: str) -> str:
    resp = await page.goto(url, wait_until="domcontentloaded", timeout=SCRAPE_TIMEOUT)
    if resp and resp.status >= 400:
        raise RuntimeError(f"页面返回状态码 {resp.status}")
    try:
        await page.wait_for_selector('[data-e2e="user-post-list"]', timeout=15000)
        logger.info("用户视频列表已加载")
    except Exception:
        logger.warning("未检测到视频列表容器, 继续尝试...")
    await _random_delay()
    try:
        await page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        logger.warning("networkidle 超时, 继续...")
    return await page.content()


async def _scroll_page(page: Page, count: int = PAGE_SCROLL_COUNT):
    for i in range(count):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(1.5, 3.0))
        logger.info(f"滚动加载 {i + 1}/{count}")


async def scrape_profile() -> tuple[int, int]:
    collected: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        captured_urls: set[str] = set()

        async def _on_response(resp: Response):
            url = resp.url
            if "/aweme/post/" in url and resp.status == 200 and url not in captured_urls:
                captured_urls.add(url)
                try:
                    body = await resp.text()
                except Exception:
                    return
                items = _parse_api_response(body)
                for item in items:
                    vid = item.get("douyin_video_id")
                    if vid and vid not in collected:
                        collected[vid] = item
                logger.info(f"拦截API: {url[:100]} → {len(items)} 条, 累计 {len(collected)}")

        page.on("response", _on_response)

        try:
            html = await _load_profile_page(page, DOUYIN_PROFILE_URL)
            ssr_videos = _parse_ssr_html(html)
            if ssr_videos:
                for v in ssr_videos:
                    vid = v.get("douyin_video_id")
                    if vid and vid not in collected:
                        collected[vid] = v
                logger.info(f"从SSR数据提取到 {len(ssr_videos)} 个视频")
            await _scroll_page(page)
        except Exception as e:
            logger.error(f"抓取失败: {e}")
            raise
        finally:
            await browser.close()

    video_list = list(collected.values())
    total = len(video_list)
    new = _db_add_videos(video_list)
    logger.info(f"共计 {total} 个视频, 新增 {new} 个")
    return total, new
