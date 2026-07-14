import asyncio
import json
import logging
import os
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Page

from backend.config import (
    SCREENSHOT_INTERVAL,
    BONSAI_FRAME_SECOND,
    SUBTITLE_CROP_RATIO,
    BONSAI_CROP_RATIO,
    SCREENSHOTS_DIR,
    PLAYWRIGHT_PROXY,
    PLAYWRIGHT_HEADLESS,
    DOUYIN_COOKIE,
)
from backend.database import SessionLocal
from backend.models import Video, Frame, Subtitle, BonsaiScreenshot

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DETAIL_API_URL = "https://www.douyin.com/aweme/v1/web/aweme/detail/"


def _parse_cookie_string(raw: str) -> list[dict]:
    cookies = []
    for item in raw.split(";"):
        item = item.strip()
        if "=" not in item:
            continue
        key, _, value = item.partition("=")
        cookies.append({
            "name": key.strip(),
            "value": value.strip(),
            "domain": ".douyin.com",
            "path": "/",
            "sameSite": "None",
        })
    return cookies


async def _fetch_video_url(page: Page, aweme_id: str) -> Optional[str]:
    body = await page.evaluate("""
        async (awemeId) => {
            const url = 'https://www.douyin.com/aweme/v1/web/aweme/detail/?' +
                new URLSearchParams({ aweme_id: awemeId, aid: '6383' }).toString();
            const resp = await fetch(url, { credentials: 'include' });
            if (!resp.ok) return JSON.stringify({error: resp.status});
            const text = await resp.text();
            return text;
        }
    """, aweme_id)

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        logger.error(f"API 返回非JSON: {body[:200]}")
        return None

    aweme_detail = data.get("aweme_detail", {})
    video = aweme_detail.get("video", {})

    for key in ("play_addr_h264", "play_addr", "play_addr_265"):
        pa = video.get(key, {})
        url_list = pa.get("url_list", []) if isinstance(pa, dict) else []
        for u in url_list:
            if isinstance(u, str) and u.startswith("http"):
                logger.info(f"解析到视频地址: {key} → {u[:80]}...")
                return u

    logger.error(f"未找到可播放的视频地址, keys: {list(video.keys())[:10]}")
    return None


async def _crop_save(page: Page, video_dir: str, frame_index: int, timestamp: float, label: str):
    from PIL import Image
    import io

    buf = await page.screenshot(full_page=False, type="png")
    img = Image.open(io.BytesIO(buf))
    w, h = img.size

    full_path = os.path.join(video_dir, "full", f"frame_{frame_index:04d}_{timestamp:.1f}s.jpg")
    subtitle_path = os.path.join(video_dir, "subtitle", f"frame_{frame_index:04d}_{timestamp:.1f}s.jpg")
    bonsai_path = os.path.join(video_dir, "bonsai", f"frame_{frame_index:04d}_{timestamp:.1f}s.jpg")

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
    max_sec = min(duration, float(os.environ.get("PROCESS_MAX_DURATION", str(duration))))

    if video.cover_url:
        try:
            import httpx
            cover_path = os.path.join(video_dir, "cover.jpg")
            os.makedirs(video_dir, exist_ok=True)
            r = httpx.get(video.cover_url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=20)
            if r.status_code == 200 and len(r.content) > 500:
                with open(cover_path, "wb") as f:
                    f.write(r.content)
                logger.info(f"封面已保存: {cover_path}")
            else:
                logger.warning(f"封面下载失败 status={r.status_code} len={len(r.content)}")
        except Exception as e:
            logger.warning(f"封面下载异常: {e}")

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=PLAYWRIGHT_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            ctx = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                proxy={"server": PLAYWRIGHT_PROXY} if PLAYWRIGHT_PROXY else None,
            )

            if DOUYIN_COOKIE:
                cookies = _parse_cookie_string(DOUYIN_COOKIE)
                await ctx.add_cookies(cookies)
                logger.info(f"已注入 {len(cookies)} 个 cookie")

            page = await ctx.new_page()

            await page.goto(f"https://www.douyin.com/video/{aweme_id}",
                            wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            video_url = await _fetch_video_url(page, aweme_id)

            if not video_url:
                video.fetch_status = "failed"
                video.error_msg = "无法解析视频地址"
                db.commit()
                await browser.close()
                db.close()
                return False

            player_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
* {{ margin:0; padding:0; background:#000; }}
video {{ width:100vw; height:100vh; object-fit:contain; }}
</style></head><body>
<video id="v" src="{video_url}" crossorigin="anonymous" muted playsinline
       preload="auto"></video>
</body></html>"""

            await page.set_content(player_html)
            await page.wait_for_timeout(1500)

            ready = await page.evaluate("""
                () => {
                    const v = document.getElementById('v');
                    return new Promise((resolve) => {
                        if (v.readyState >= 2) { resolve(true); return; }
                        v.oncanplay = () => resolve(true);
                        v.onerror = () => resolve(false);
                        setTimeout(() => resolve(false), 15000);
                    });
                }
            """)

            if not ready:
                logger.error("视频加载失败")
                video.fetch_status = "failed"
                video.error_msg = "视频无法加载"
                db.commit()
                await browser.close()
                db.close()
                return False

            dur = await page.evaluate("document.getElementById('v').duration")
            if dur and dur > 0:
                max_sec = min(dur, max_sec)

            frame_index = 0
            bonsai_done = False
            t = 1.0

            while t < max_sec:
                ct = await page.evaluate("""
                    () => {
                        const v = document.getElementById('v');
                        return v ? v.currentTime : -1;
                    }
                """)
                if ct < 0:
                    logger.error("video 元素丢失，终止截图")
                    break

                await page.evaluate(f"document.getElementById('v').currentTime = {t}")
                await page.wait_for_timeout(2000)

                ct = await page.evaluate("""
                    () => {
                        const v = document.getElementById('v');
                        return v ? v.currentTime : -1;
                    }
                """)
                logger.info(f"[{aweme_id}] frame {frame_index:03d} @ {ct:.1f}s")

                label = ""
                if not bonsai_done and abs(ct - BONSAI_FRAME_SECOND) <= 4:
                    label = "bonsai"
                    bonsai_done = True

                full_path, subtitle_path, bonsai_path = await _crop_save(
                    page, video_dir, frame_index, ct, label,
                )

                db.add(Frame(
                    video_id=video.id,
                    frame_index=frame_index,
                    frame_timestamp=ct,
                    full_screenshot=full_path,
                ))
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
