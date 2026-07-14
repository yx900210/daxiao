import asyncio
import logging
import os
import re
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Page

from backend.config import (
    DOUYIN_PROFILE_URL,
    SCREENSHOT_INTERVAL,
    BONSAI_FRAME_SECOND,
    SUBTITLE_CROP_RATIO,
    BONSAI_CROP_RATIO,
    SCREENSHOTS_DIR,
    SCRAPE_TIMEOUT,
    PLAYWRIGHT_PROXY,
    PLAYWRIGHT_HEADLESS,
)
from backend.database import SessionLocal
from backend.models import Video, Frame, Subtitle, BonsaiScreenshot, VideoResult

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/16.0 Mobile/15E148 Safari/604.1"
)

VIDEO_PAGE_TMPL = "https://m.douyin.com/share/video/{aweme_id}"


async def _setup_page(page: Page):
    async def _handler(route):
        non_essential = ("image", "font")
        if route.request.resource_type in non_essential and "screenshot" not in route.request.url:
            await route.abort()
        else:
            await route.continue_()

    await page.route("**/*", _handler)


async def _crop_save(page: Page, video_dir: str, frame_index: int, timestamp: float, label: str):
    from PIL import Image
    import io

    buf = await page.screenshot(full_page=False, type="png")
    img = Image.open(io.BytesIO(buf))
    w, h = img.size

    full_path = os.path.join(video_dir, "full", f"frame_{frame_index:04d}.jpg")
    subtitle_path = os.path.join(video_dir, "subtitle", f"frame_{frame_index:04d}.jpg")
    bonsai_path = os.path.join(video_dir, "bonsai", f"frame_{frame_index:04d}.jpg")

    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    img.save(full_path, quality=85)

    l, t, r, b = SUBTITLE_CROP_RATIO
    sub_img = img.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
    os.makedirs(os.path.dirname(subtitle_path), exist_ok=True)
    sub_img.save(subtitle_path, quality=85)

    if label == "bonsai":
        l, t, r, b = BONSAI_CROP_RATIO
        bon_img = img.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
        os.makedirs(os.path.dirname(bonsai_path), exist_ok=True)
        bon_img.save(bonsai_path, quality=85)
    else:
        bonsai_path = None

    return full_path, subtitle_path, bonsai_path


async def process_video(video_id: int) -> bool:
    db = SessionLocal()
    video = db.query(Video).get(video_id)
    if not video:
        logger.error(f"视频不存在: id={video_id}")
        db.close()
        return False

    if video.fetch_status == "done":
        logger.info(f"视频已处理: {video.douyin_video_id}")
        db.close()
        return True

    video.fetch_status = "processing"
    db.commit()

    aweme_id = video.douyin_video_id
    duration = video.duration or 300
    video_dir = os.path.join(SCREENSHOTS_DIR, aweme_id)

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=PLAYWRIGHT_HEADLESS,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 390, "height": 844},
                device_scale_factor=3,
                is_mobile=True,
                has_touch=True,
                proxy={"server": PLAYWRIGHT_PROXY} if PLAYWRIGHT_PROXY else None,
            )
            page = await ctx.new_page()
            await page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            """)
            await _setup_page(page)

            url = VIDEO_PAGE_TMPL.format(aweme_id=aweme_id)
            await page.goto(url, wait_until="domcontentloaded", timeout=SCRAPE_TIMEOUT)
            await page.wait_for_timeout(2000)

            await page.evaluate("""
                () => {
                    const v = document.querySelector('video');
                    if (v) { v.muted = true; v.play().catch(() => {}); }
                }
            """)
            await page.wait_for_timeout(3000)

            frame_index = 0
            bonsai_done = False
            t = 1.0

            while t < duration:
                await page.evaluate(f"document.querySelector('video').currentTime = {t}")
                await page.wait_for_timeout(1500)

                ct = await page.evaluate("document.querySelector('video').currentTime")
                logger.debug(f"[{aweme_id}] seek {t}s → actual {ct:.1f}s")

                label = ""
                if not bonsai_done and abs(ct - BONSAI_FRAME_SECOND) <= 3:
                    label = "bonsai"
                    bonsai_done = True

                full_path, subtitle_path, bonsai_path = await _crop_save(
                    page, video_dir, frame_index, ct, label
                )

                frame = Frame(
                    video_id=video.id,
                    frame_index=frame_index,
                    frame_timestamp=ct,
                    full_screenshot=full_path,
                )
                db.add(frame)

                db.add(Subtitle(
                    video_id=video.id,
                    frame_index=frame_index,
                    frame_timestamp=ct,
                    screenshot_path=subtitle_path,
                ))

                if bonsai_path:
                    db.add(BonsaiScreenshot(
                        video_id=video.id,
                        frame_index=frame_index,
                        frame_timestamp=ct,
                        screenshot_path=bonsai_path,
                    ))

                db.commit()
                frame_index += 1
                t += SCREENSHOT_INTERVAL

            await browser.close()

        video.fetch_status = "screenshotted"
        db.commit()
        logger.info(f"视频截图完成: {aweme_id}, {frame_index} 帧")
        return True

    except Exception as e:
        logger.error(f"处理视频失败 {aweme_id}: {e}")
        video.fetch_status = "failed"
        video.error_msg = str(e)
        db.commit()
        return False
    finally:
        db.close()
