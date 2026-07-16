import asyncio
import json
import logging
import random

import httpx
import websockets

from backend.config import (
    DOUYIN_PROFILE_URL,
    SCRAPE_DELAY_MIN,
    SCRAPE_DELAY_MAX,
    PAGE_SCROLL_COUNT,
    CHROME_CDP_URL,
    SCRAPE_TIMEOUT,
)
from backend.database import SessionLocal
from backend.models import Video, ScrapeLog

logger = logging.getLogger(__name__)


def _parse_aweme_video_url(video: dict) -> str:
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

    from datetime import datetime
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
        "video_url": _parse_aweme_video_url(video),
        "publish_time": create_time,
        "duration": duration,
        "like_count": statistics.get("digg_count", 0),
        "comment_count": statistics.get("comment_count", 0),
        "share_count": statistics.get("share_count", 0),
    }


def _parse_aweme_list(body: str) -> list[dict]:
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


class CDPClient:
    def __init__(self, browser_ws: str):
        self.browser_ws = browser_ws
        self._ws = None
        self._msg_id = 0

    async def connect(self):
        self._ws = await websockets.connect(self.browser_ws)
        resp = await self._recv_init()
        return resp

    async def _recv_init(self):
        raw = await asyncio.wait_for(self._ws.recv(), timeout=5)
        return json.loads(raw)

    async def send(self, method: str, params: dict = None) -> dict:
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(msg))
        while True:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
            resp = json.loads(raw)
            if resp.get("id") == self._msg_id:
                return resp

    async def create_page(self) -> str:
        resp = await self.send("Target.createTarget", {"url": "about:blank"})
        return resp["result"]["targetId"]

    async def navigate(self, url: str) -> dict:
        return await self.send("Page.navigate", {"url": url})

    async def evaluate(self, expression: str) -> str:
        resp = await self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        })
        result = resp.get("result", {}).get("result", {})
        return result.get("value", "")

    async def close(self):
        if self._ws:
            await self._ws.close()


async def _get_browser_ws() -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CHROME_CDP_URL}/json/version")
        data = r.json()
        return data["webSocketDebuggerUrl"]


async def _get_page_ws(target_id: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{CHROME_CDP_URL}/json")
        pages = r.json()
        for p in pages:
            if p.get("id") == target_id:
                return p["webSocketDebuggerUrl"]
        raise RuntimeError(f"Target {target_id} not found")


async def scrape_profile() -> tuple[int, int]:
    collected: dict[str, dict] = {}

    browser_ws = await _get_browser_ws()
    logger.info(f"CDP browser WS: {browser_ws[:80]}...")

    browser = CDPClient(browser_ws)
    await browser.connect()
    logger.info("CDP browser 已连接")

    try:
        target_id = await browser.create_page()
        logger.info(f"新页面 targetId: {target_id}")

        await asyncio.sleep(1)

        page_ws = None
        for attempt in range(5):
            try:
                page_ws = await _get_page_ws(target_id)
                break
            except RuntimeError:
                await asyncio.sleep(0.5)
        if not page_ws:
            raise RuntimeError(f"无法获取 target {target_id} 的 WS 地址")

        logger.info(f"CDP page WS: {page_ws[:80]}...")
        page = CDPClient(page_ws)
        await page.connect()
        logger.info("CDP page 已连接")

        await page.navigate(DOUYIN_PROFILE_URL)
        logger.info("已导航到主页")
        await asyncio.sleep(3)

        for i in range(PAGE_SCROLL_COUNT):
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(random.uniform(1.5, 3.0))
            logger.info(f"滚动加载 {i + 1}/{PAGE_SCROLL_COUNT}")

        html = await page.evaluate("document.documentElement.outerHTML")
        if not isinstance(html, str):
            html = ""

        import re
        from urllib.parse import unquote

        results = []
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
                                results.append(_parse_aweme(aweme))
                break

        for item in results:
            vid = item.get("douyin_video_id")
            if vid:
                collected[vid] = item

        logger.info(f"从SSR提取 {len(collected)} 个视频")

        # 补全 video_url (部分视频可能需要调详情API)
        need_urls = [vid for vid, item in collected.items() if not item.get("video_url")]
        if need_urls:
            logger.info(f"补全 {len(need_urls)} 个视频地址...")
            for vid in need_urls:
                try:
                    body = await page.evaluate(
                        f'fetch("https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id={vid}&aid=6383",{{credentials:"include"}}).then(r=>r.text())'
                    )
                    if isinstance(body, str) and body.startswith("{"):
                        data = json.loads(body)
                        vobj = data.get("aweme_detail", {}).get("video", {})
                        url = _parse_aweme_video_url(vobj)
                        if url:
                            collected[vid]["video_url"] = url
                            logger.info(f"[{vid}] ✅ {url[:100]}...")
                except Exception as e:
                    logger.warning(f"[{vid}] 补全失败: {e}")

        await page.close()
    finally:
        await browser.close()

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
