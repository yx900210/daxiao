import asyncio
import json
import logging
import random
import re
from datetime import datetime
from urllib.parse import unquote

from playwright.async_api import async_playwright, Browser, Page, Response

from backend.config import (
    DOUYIN_PROFILE_URL,
    SCRAPE_DELAY_MIN,
    SCRAPE_DELAY_MAX,
    PAGE_SCROLL_COUNT,
    CHROME_CDP_URL,
    SCRAPE_TIMEOUT,
)
from backend.database import SessionLocal
from backend.models import Video

logger = logging.getLogger(__name__)


def _extract_play_url(video: dict) -> str:
    for key in ("play_addr_h264", "play_addr", "play_addr_265"):
        pa = video.get(key, {})
        urls = pa.get("url_list", []) if isinstance(pa, dict) else []
        for u in urls:
            if isinstance(u, str) and u.startswith("http"):
                return u
    return ""


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


async def _fetch_detail_urls(page: Page, collected: dict):
    need = [vid for vid, item in collected.items() if not item.get("video_url")]
    if not need:
        return
    logger.info(f"补全 {len(need)} 个视频地址...")
    for vid in need:
        try:
            body = await page.evaluate("""
                async (id) => {
                    const url = 'https://www.douyin.com/aweme/v1/web/aweme/detail/?' +
                        new URLSearchParams({ aweme_id: id, aid: '6383' }).toString();
                    const ctrl = new AbortController();
                    setTimeout(() => ctrl.abort(), 10000);
                    const resp = await fetch(url, { credentials: 'include', signal: ctrl.signal });
                    return resp.ok ? await resp.text() : '';
                }
            """, vid)
            if body:
                data = json.loads(body)
                vobj = data.get("aweme_detail", {}).get("video", {})
                url = _extract_play_url(vobj)
                if url:
                    collected[vid]["video_url"] = url
                    logger.info(f"[{vid}] ✅ {url[:100]}...")
        except Exception as e:
            logger.warning(f"[{vid}] 失败: {e}")


async def scrape_profile() -> tuple[int, int]:
    collected: dict[str, dict] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.connect_over_cdp(CHROME_CDP_URL)
        contexts = browser.contexts
        context = contexts[0] if contexts else await browser.new_context()
        page = await context.new_page()

        async def _on_response(resp: Response):
            url = resp.url
            if "/aweme/post/" in url and resp.status == 200:
                try:
                    body = await resp.text()
                except Exception:
                    return
                for item in _parse_api_response(body):
                    vid = item.get("douyin_video_id")
                    if vid and vid not in collected:
                        collected[vid] = item
                logger.info(f"拦截API → {len(_parse_api_response(body))} 条, 累计 {len(collected)}")

        page.on("response", _on_response)

        try:
            resp = await page.goto(DOUYIN_PROFILE_URL, wait_until="domcontentloaded", timeout=SCRAPE_TIMEOUT)
            logger.info(f"页面状态码: {resp.status if resp else 'N/A'}")

            html = await page.content()
            for pattern in [
                r'<script[^>]*id="RENDER_DATA"[^>]*type="application/json"[^>]*>([^<]+)</script>',
                r'<script[^>]*id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>([^<]+)</script>',
            ]:
                match = re.search(pattern, html)
                if match:
                    raw = unquote(match.group(1))
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    app = data.get("app", data)
                    user_page = app.get("userPage", app)
                    post_data = user_page.get("post", {})
                    aweme_list = post_data.get("aweme", {}).get("post", []) or post_data.get("post", []) or []
                    for a in aweme_list:
                        if isinstance(a, dict):
                            aweme = a.get("aweme", a.get("aweme_info", a))
                            if aweme.get("aweme_id"):
                                item = _parse_aweme(aweme)
                                vid = item.get("douyin_video_id")
                                if vid and vid not in collected:
                                    collected[vid] = item
                    logger.info(f"SSR提取 {len(aweme_list)} 个视频")
                    break

            for i in range(PAGE_SCROLL_COUNT):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(random.uniform(1.5, 3.0))
                if (i + 1) % 2 == 0:
                    logger.info(f"滚动 {i + 1}/{PAGE_SCROLL_COUNT}")

            await _fetch_detail_urls(page, collected)

        except Exception as e:
            logger.error(f"抓取失败: {e}")
            raise
        finally:
            await page.close()

    video_list = list(collected.values())
    total = len(video_list)
    new = _db_add_videos(video_list)
    logger.info(f"共计 {total} 个视频, 新增 {new} 个")
    return total, new


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
