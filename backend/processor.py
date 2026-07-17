import json
import logging
import os
from datetime import datetime
from typing import Optional

import cv2
import httpx

from backend.config import (
    SCREENSHOT_INTERVAL,
    BONSAI_FRAME_SECOND,
    SUBTITLE_CROP_RATIO,
    BONSAI_CROP_RATIO,
    SCREENSHOTS_DIR,
    VIDEOS_DIR,
)
from backend.database import SessionLocal
from backend.models import Video, Frame, Subtitle, BonsaiScreenshot

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/150.0.0.0 Safari/537.36"
)


def _download_video(aweme_id: str, video_url: str) -> Optional[str]:
    os.makedirs(VIDEOS_DIR, exist_ok=True)
    output_path = os.path.join(VIDEOS_DIR, f"{aweme_id}.mp4")

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1024:
        logger.info(f"[{aweme_id}] 视频已存在: {output_path}")
        return output_path

    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://www.douyin.com/",
    }

    try:
        logger.info(f"[{aweme_id}] 开始下载视频...")
        with httpx.stream("GET", video_url, headers=headers, timeout=300, follow_redirects=True) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=65536):
                    f.write(chunk)
                    downloaded += len(chunk)
            if total > 0:
                logger.info(f"[{aweme_id}] 下载完成: {downloaded}/{total} bytes")
            else:
                logger.info(f"[{aweme_id}] 下载完成: {downloaded} bytes")

        if os.path.getsize(output_path) < 1024:
            os.remove(output_path)
            logger.error(f"[{aweme_id}] 下载文件过小，可能失败")
            return None

        return output_path
    except Exception as e:
        logger.error(f"[{aweme_id}] 下载失败: {e}")
        if os.path.exists(output_path):
            os.remove(output_path)
        return None


def _extract_frames(video_path: str, aweme_id: str, duration: float, video_id: int,
                    db: SessionLocal, max_sec: float):
    video_dir = os.path.join(SCREENSHOTS_DIR, aweme_id)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logger.error(f"[{aweme_id}] 无法打开视频文件")
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    actual_duration = cap.get(cv2.CAP_PROP_FRAME_COUNT) / fps if fps > 0 else duration
    process_sec = min(actual_duration, max_sec)

    frame_index = 0
    bonsai_done = False
    t = 1.0
    total_frames = int(process_sec / SCREENSHOT_INTERVAL)
    logger.info(f"[{aweme_id}] 视频就绪, fps={fps:.1f}, 时长={actual_duration:.0f}s, 将处理{process_sec:.0f}s, 预计{total_frames}帧")

    while t < process_sec:
        target_ms = t * 1000
        cap.set(cv2.CAP_PROP_POS_MSEC, target_ms)
        ret, frame = cap.read()

        if not ret:
            logger.warning(f"[{aweme_id}] 帧{t:.1f}s读取失败, 跳过")
            t += SCREENSHOT_INTERVAL
            continue

        h, w = frame.shape[:2]
        actual_t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0

        full_path = os.path.join(video_dir, "full", f"frame_{frame_index:04d}_{actual_t:.1f}s.jpg")
        subtitle_path = os.path.join(video_dir, "subtitle", f"frame_{frame_index:04d}_{actual_t:.1f}s.jpg")
        bonsai_path = os.path.join(video_dir, "bonsai", f"frame_{frame_index:04d}_{actual_t:.1f}s.jpg")

        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        cv2.imwrite(full_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        l, t_r, r, b = SUBTITLE_CROP_RATIO
        sub_frame = frame[int(h * t_r):int(h * b), int(w * l):int(w * r)]
        os.makedirs(os.path.dirname(subtitle_path), exist_ok=True)
        cv2.imwrite(subtitle_path, sub_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

        label = ""
        if not bonsai_done and abs(actual_t - BONSAI_FRAME_SECOND) <= 4:
            label = "bonsai"
            bonsai_done = True
            l, t_r, r, b = BONSAI_CROP_RATIO
            bon_frame = frame[int(h * t_r):int(h * b), int(w * l):int(w * r)]
            os.makedirs(os.path.dirname(bonsai_path), exist_ok=True)
            cv2.imwrite(bonsai_path, bon_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        else:
            bonsai_path = None

        extra = f" [{label}]" if label else ""
        logger.info(f"[{aweme_id}] 帧{frame_index:03d} @ {actual_t:5.1f}s{extra}")

        db.add(Frame(
            video_id=video_id,
            frame_index=frame_index,
            frame_timestamp=actual_t,
            full_screenshot=full_path,
        ))
        db.add(Subtitle(
            video_id=video_id,
            frame_index=frame_index,
            frame_timestamp=actual_t,
            screenshot_path=subtitle_path,
        ))
        if bonsai_path:
            db.add(BonsaiScreenshot(
                video_id=video_id,
                frame_index=frame_index,
                frame_timestamp=actual_t,
                screenshot_path=bonsai_path,
            ))

        db.commit()
        frame_index += 1
        t += SCREENSHOT_INTERVAL

    cap.release()
    return frame_index


def _run_ai_steps(video_id: int):
    from backend.database import SessionLocal
    from backend.models import VideoResult

    db = SessionLocal()
    result = db.query(VideoResult).filter(VideoResult.video_id == video_id).first()
    if not result or not result.full_subtitle:
        logger.warning(f"[vid={video_id}] 无字幕，跳过AI步骤")
        db.close()
        return
    db.close()

    try:
        from backend.llm import organize_subtitle, extract_viewpoints
    except ImportError:
        logger.warning("AI模块未加载")
        return

    if not result.organized_subtitle:
        logger.info(f"[vid={video_id}] AI 整理段落...")
        organized = organize_subtitle(result.full_subtitle)
        if organized:
            db = SessionLocal()
            r = db.query(VideoResult).filter(VideoResult.video_id == video_id).first()
            r.organized_subtitle = organized
            db.commit()
            result.organized_subtitle = organized
            db.close()
            logger.info(f"[vid={video_id}] AI 整理完成")

    if result.organized_subtitle or result.full_subtitle:
        text = result.organized_subtitle or result.full_subtitle
        db = SessionLocal()
        r = db.query(VideoResult).filter(VideoResult.video_id == video_id).first()
        if not r.stock_summary:
            logger.info(f"[vid={video_id}] 提炼核心观点...")
            vp = extract_viewpoints(text)
            if vp:
                r.stock_summary = "\n".join(f"{i+1}. {p}" for i, p in enumerate(vp.get("points", [])))
                r.stock_keywords = json.dumps(vp.get("keywords", []), ensure_ascii=False)
                r.stock_sentiment = vp.get("sentiment", "中性")
                db.commit()
                logger.info(f"[vid={video_id}] 观点提炼完成 ({len(vp.get('points',[]))}条)")
        db.close()


def process_video(video_id: int) -> bool:
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
        _result = db.query(VideoResult).filter(VideoResult.video_id == video_id).first()
        if _result and _result.full_subtitle and not _result.organized_subtitle:
            logger.info(f"[{aweme_id}] 已完成, 补充AI整理+观点...")
            _run_ai_steps(video.id)
        else:
            logger.info(f"[{aweme_id}] 已处理过, 跳过")
        db.close()
        return True

    if video.fetch_status == "screenshotted" and video.local_video_path:
        logger.info(f"[{aweme_id}] 已截图, 运行OCR+AI...")
        from backend.ocr import process_subtitles
        process_subtitles(video.id)
        _run_ai_steps(video.id)
        video.fetch_status = "done"
        db.commit()
        db.close()
        return True

    video.fetch_status = "processing"
    db.commit()

    duration = video.duration or 300
    max_sec = min(duration, float(os.environ.get("PROCESS_MAX_DURATION", str(duration))))

    # ── 封面下载 ──
    if video.cover_url:
        try:
            cover_path = os.path.join(SCREENSHOTS_DIR, aweme_id, "cover.jpg")
            os.makedirs(os.path.dirname(cover_path), exist_ok=True)
            logger.info(f"[{aweme_id}] 下载封面...")
            r = httpx.get(video.cover_url, headers={"User-Agent": USER_AGENT, "Referer": "https://www.douyin.com/"}, timeout=20)
            if r.status_code == 200 and len(r.content) > 500:
                with open(cover_path, "wb") as f:
                    f.write(r.content)
                logger.info(f"[{aweme_id}] 封面已保存 ({len(r.content)} bytes)")
        except Exception as e:
            logger.warning(f"[{aweme_id}] 封面下载异常: {e}")

    # ── 视频地址 ──
    video_url = video.video_url
    if not video_url:
        logger.error(f"[{aweme_id}] 失败: 无视频地址")
        video.fetch_status = "failed"
        video.error_msg = "无视频地址"
        db.commit()
        db.close()
        return False
    logger.info(f"[{aweme_id}] 视频地址: {video_url[:100]}...")

    # ── 下载视频 ──
    video_path = _download_video(aweme_id, video_url)
    if not video_path:
        video.fetch_status = "failed"
        video.error_msg = "视频下载失败"
        db.commit()
        db.close()
        return False

    video.local_video_path = video_path
    db.commit()

    # ── OpenCV 抽帧 ──
    try:
        frame_count = _extract_frames(video_path, aweme_id, duration, video.id, db, max_sec)
        elapsed = (datetime.utcnow() - t_start).total_seconds()
        video.fetch_status = "screenshotted"
        db.commit()
        logger.info(f"[{aweme_id}] ======== 截图完成: {frame_count}帧, 耗时{elapsed:.0f}s ========")

        try:
            from backend.ocr import process_subtitles
            logger.info(f"[{aweme_id}] 开始 OCR 识别...")
            process_subtitles(video.id)
            logger.info(f"[{aweme_id}] OCR 完成")

            _run_ai_steps(video.id)

            video.fetch_status = "done"
            db.commit()
            elapsed2 = (datetime.utcnow() - t_start).total_seconds()
            logger.info(f"[{aweme_id}] ======== 全部完成(含OCR): 总耗时{elapsed2:.0f}s ========")
        except ImportError as e:
            logger.warning(f"[{aweme_id}] PaddleOCR 未安装, 跳过OCR。详情: {e}")
        except Exception as e:
            logger.error(f"[{aweme_id}] OCR 失败: {e}")

        return True
    except Exception as e:
        elapsed = (datetime.utcnow() - t_start).total_seconds()
        logger.error(f"[{aweme_id}] 抽帧失败(耗时{elapsed:.0f}s): {e}")
        video.fetch_status = "failed"
        video.error_msg = str(e)
        db.commit()
        return False
    finally:
        db.close()
