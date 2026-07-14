import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
from playwright.async_api import async_playwright, Page, Response

from backend.config import (
    DOUYIN_PROFILE_URL,
    VIDEOS_DIR,
    SCRAPE_DELAY_MIN,
    SCRAPE_DELAY_MAX,
    MAX_RETRIES,
    PAGE_SCROLL_COUNT,
    PLAYWRIGHT_HEADLESS,
    PLAYWRIGHT_PROXY,
    SCRAPE_TIMEOUT,
)
from backend.database import SessionLocal, get_setting
from backend.models import Video, ScrapeLog

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.0 Mobile/15E148 Safari/604.1"
)

COOKIE_FILE = os.path.join(os.path.dirname(VIDEOS_DIR), "cookies.json")


def extract_sec_uid(url: str) -> str:
    path = urlparse(url).path
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] == "user":
        return parts[1]
    raise ValueError(f"无法从URL提取 sec_uid: {url}")


def _parse_aweme(aweme: dict) -> dict:
    statistics = aweme.get("statistics", {})
    video = aweme.get("video", {}) or {}
    duration = aweme.get("duration") or video.get("duration", 0)
    if isinstance(duration, (int, float)) and duration > 1000:
        duration = duration / 1000.0

    create_time = aweme.get("create_time")
    if not create_time:
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

    if not results:
        match = re.search(
            r'window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>',
            html,
            re.DOTALL,
        )
        if match:
            try:
                from urllib.parse import unquote
                state = json.loads(unquote(match.group(1)))
                raw = state.get("user", {}).get("aweme", {}).get("post", [])
                for a in raw:
                    if isinstance(a, dict):
                        aweme = a.get("aweme", a.get("aweme_info", a))
                        if aweme.get("aweme_id"):
                            try:
                                results.append(_parse_aweme(aweme))
                            except Exception:
                                pass
            except (json.JSONDecodeError, Exception):
                pass

    return results


def _save_cookies(cookies: list[dict]):
    os.makedirs(os.path.dirname(COOKIE_FILE), exist_ok=True)
    with open(COOKIE_FILE, "w") as f:
        json.dump(cookies, f)


def _load_cookies() -> list[dict]:
    if os.path.exists(COOKIE_FILE):
        try:
            with open(COOKIE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return []


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


async def _setup_page(page: Page):
    async def _handle_route(route):
        if route.request.resource_type in ("image", "font", "media"):
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", _handle_route)


async def _random_delay():
    delay = random.uniform(SCRAPE_DELAY_MIN, SCRAPE_DELAY_MAX)
    logger.debug(f"等待 {delay:.1f} 秒...")
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
        browser = await pw.chromium.launch(
            headless=PLAYWRIGHT_HEADLESS,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )
        db_proxy = get_setting("http_proxy", PLAYWRIGHT_PROXY) or ""
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            is_mobile=True,
            has_touch=True,
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            proxy={"server": db_proxy} if db_proxy else None,
        )

        existing_cookies = _load_cookies()
        if existing_cookies:
            await context.add_cookies(existing_cookies)

        page = await context.new_page()

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
        """)

        captured_urls: set[str] = set()

        async def _on_response(resp: Response):
            url = resp.url
            if "/aweme/post/" in url and resp.status == 200 and url not in captured_urls:
                captured_urls.add(url)
                try:
                    body = await resp.text()
                except Exception:
                    return
                debug_dir = os.path.join(os.path.dirname(VIDEOS_DIR), "debug")
                os.makedirs(debug_dir, exist_ok=True)
                api_debug = os.path.join(debug_dir, "api_response.json")
                if not os.path.exists(api_debug):
                    with open(api_debug, "w") as f:
                        f.write(body[:50000])
                items = _parse_api_response(body)
                for item in items:
                    vid = item.get("douyin_video_id")
                    if vid and vid not in collected:
                        collected[vid] = item
                logger.info(f"拦截API: {url[:100]} → {len(items)} 条, 累计 {len(collected)}")

        page.on("response", _on_response)

        await _setup_page(page)

        try:
            html = await _load_profile_page(page, DOUYIN_PROFILE_URL)

            debug_dir = os.path.join(os.path.dirname(VIDEOS_DIR), "debug")
            os.makedirs(debug_dir, exist_ok=True)
            debug_path = os.path.join(debug_dir, "page.html")
            with open(debug_path, "w") as f:
                f.write(html)
            logger.info(f"页面HTML已保存至 {debug_path}")

            logger.info(f"页面标题: {await page.title()}")

            ssr_videos = _parse_ssr_html(html)
            if ssr_videos:
                for v in ssr_videos:
                    vid = v.get("douyin_video_id")
                    if vid and vid not in collected:
                        collected[vid] = v
                logger.info(f"从SSR数据提取到 {len(ssr_videos)} 个视频")

            await _scroll_page(page)

            cookies = await context.cookies()
            _save_cookies(cookies)

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


async def _download_video(client: httpx.AsyncClient, video_url: str, output_path: str) -> bool:
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Referer": "https://www.douyin.com/",
        }
        with client.stream("GET", video_url, headers=headers, timeout=120) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        return True
    except Exception as e:
        logger.warning(f"下载视频失败 {video_url}: {e}")
        return False
