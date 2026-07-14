import asyncio
import json
import logging
import os
import traceback
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
    DATA_DIR,
)
from backend.database import SessionLocal, get_setting
from backend.models import Video, Frame, Subtitle, BonsaiScreenshot

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


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
    logger.info(f"[{aweme_id}] 正在调用抖音详情API...")
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
        logger.error(f"[{aweme_id}] 详情API返回非JSON (前200字): {body[:200]}")
        return None

    if "error" in data and isinstance(data.get("error"), int):
        logger.error(f"[{aweme_id}] 详情API返回错误码: {data['error']}")
        return None

    aweme_detail = data.get("aweme_detail", {})
    video = aweme_detail.get("video", {})

    for key in ("play_addr_h264", "play_addr", "play_addr_265"):
        pa = video.get(key, {})
        url_list = pa.get("url_list", []) if isinstance(pa, dict) else []
        for u in url_list:
            if isinstance(u, str) and u.startswith("http"):
                logger.info(f"[{aweme_id}] 视频地址: {key} → {u[:80]}...")
                return u

    logger.error(f"[{aweme_id}] 未找到可播放的视频地址, video keys: {list(video.keys())[:10]}")
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
    t_start = datetime.utcnow()

    db = SessionLocal()
    video = db.query(Video).get(video_id)
    if not video:
        logger.error(f"[vid={video_id}] 视频不存在")
        db.close()
        return False

    aweme_id = video.douyin_video_id
    title = (video.title or "")[:30]
    logger.info(f"[{aweme_id}] ======== 开始处理: {title} (id={video_id}) ========")

    if video.fetch_status == "done":
        logger.info(f"[{aweme_id}] 已处理过, 跳过")
        db.close()
        return True

    video.fetch_status = "processing"
    db.commit()

    duration = video.duration or 300
    video_dir = os.path.join(SCREENSHOTS_DIR, aweme_id)
    max_sec = min(duration, float(os.environ.get("PROCESS_MAX_DURATION", str(duration))))

    # ── 封面下载 ──
    if video.cover_url:
        try:
            import httpx
            cover_path = os.path.join(video_dir, "cover.jpg")
            os.makedirs(video_dir, exist_ok=True)
            logger.info(f"[{aweme_id}] 下载封面...")
            r = httpx.get(video.cover_url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=20)
            if r.status_code == 200 and len(r.content) > 500:
                with open(cover_path, "wb") as f:
                    f.write(r.content)
                logger.info(f"[{aweme_id}] 封面已保存 ({len(r.content)} bytes)")
            else:
                logger.warning(f"[{aweme_id}] 封面下载失败 status={r.status_code} len={len(r.content)}")
        except Exception as e:
            logger.warning(f"[{aweme_id}] 封面下载异常: {e}")

    # ── 浏览器截图 ──
    try:
        logger.info(f"[{aweme_id}] 启动浏览器...")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=PLAYWRIGHT_HEADLESS,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            db_proxy = get_setting("http_proxy", PLAYWRIGHT_PROXY) or ""
            proxy_info = f"代理={db_proxy}" if db_proxy else "无代理"
            logger.info(f"[{aweme_id}] 浏览器已启动, {proxy_info}")

            ctx = await browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 720},
                device_scale_factor=1,
                proxy={"server": db_proxy} if db_proxy else None,
            )

            cookie_str = get_setting("douyin_cookie", DOUYIN_COOKIE)
            if cookie_str:
                cookies = _parse_cookie_string(cookie_str)
                await ctx.add_cookies(cookies)
                logger.info(f"[{aweme_id}] 已注入 {len(cookies)} 个 cookie")
            else:
                logger.warning(f"[{aweme_id}] 未配置 cookie")

            page = await ctx.new_page()

            # Step 1: 访问抖音页面
            mobile_url = f"https://m.douyin.com/share/video/{aweme_id}"
            logger.info(f"[{aweme_id}] 访问页面: {mobile_url}")
            resp = await page.goto(mobile_url, wait_until="domcontentloaded", timeout=30000)
            logger.info(f"[{aweme_id}] 页面状态码: {resp.status if resp else 'N/A'}")
            await page.wait_for_timeout(3000)

            # Step 2: 获取视频地址
            video_url = await _fetch_video_url(page, aweme_id)

            if not video_url:
                logger.error(f"[{aweme_id}] 失败: 无法获取视频地址")
                video.fetch_status = "failed"
                video.error_msg = "无法解析视频地址"
                db.commit()
                await browser.close()
                db.close()
                return False

            # Step 3: 加载自定义播放器
            logger.info(f"[{aweme_id}] 加载视频播放器...")
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

            logger.info(f"[{aweme_id}] 等待视频就绪...")
            ready = await page.evaluate("""
                () => {
                    const v = document.getElementById('v');
                    return new Promise((resolve) => {
                        if (v.readyState >= 2) { resolve(true); return; }
                        v.oncanplay = () => resolve(true);
                        v.onerror = (e) => { console.error('video error', e); resolve(false); };
                        setTimeout(() => resolve(false), 15000);
                    });
                }
            """)

            if not ready:
                logger.error(f"[{aweme_id}] 视频加载失败 (CDN可能过期或网络不通)")
                video.fetch_status = "failed"
                video.error_msg = "视频无法加载(CDN过期/网络)"
                db.commit()
                await browser.close()
                db.close()
                return False

            dur = await page.evaluate("document.getElementById('v').duration")
            logger.info(f"[{aweme_id}] 视频就绪, 实际时长={dur:.0f}s, 将处理 {max_sec:.0f}s")
            if dur and dur > 0:
                max_sec = min(dur, max_sec)

            # Step 4: 逐帧截图
            frame_index = 0
            bonsai_done = False
            t = 1.0
            total_frames = int(max_sec / SCREENSHOT_INTERVAL)
            logger.info(f"[{aweme_id}] 开始截图, 预计 {total_frames} 帧")

            while t < max_sec:
                seek_ok = await page.evaluate(f"""
                    () => {{
                        const v = document.getElementById('v');
                        if (!v) return false;
                        v.currentTime = {t};
                        return true;
                    }}
                """)

                if not seek_ok:
                    logger.error(f"[{aweme_id}] video元素丢失, 终止(已截图{frame_index}帧)")
                    break

                await page.wait_for_timeout(2000)

                ct = await page.evaluate("""
                    () => {
                        const v = document.getElementById('v');
                        return v ? v.currentTime : -1;
                    }
                """)

                label = ""
                if not bonsai_done and abs(ct - BONSAI_FRAME_SECOND) <= 4:
                    label = "bonsai"
                    bonsai_done = True

                full_path, subtitle_path, bonsai_path = await _crop_save(
                    page, video_dir, frame_index, ct, label,
                )

                extra = f" [{label}]" if label else ""
                logger.info(f"[{aweme_id}] 帧{frame_index:03d} @ {ct:5.1f}s{extra}")

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

        elapsed = (datetime.utcnow() - t_start).total_seconds()
        video.fetch_status = "screenshotted"
        db.commit()
        logger.info(f"[{aweme_id}] ======== 完成: {frame_index}帧, 耗时{elapsed:.0f}s ========")
        return True

    except Exception as e:
        elapsed = (datetime.utcnow() - t_start).total_seconds()
        logger.error(f"[{aweme_id}] 失败(耗时{elapsed:.0f}s): {e}")
        logger.debug(traceback.format_exc())
        video.fetch_status = "failed"
        video.error_msg = f"{type(e).__name__}: {e}"
        db.commit()
        return False
    finally:
        db.close()
