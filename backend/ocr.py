import re
import logging
from difflib import SequenceMatcher

from backend.database import SessionLocal
from backend.models import Subtitle, VideoResult

logger = logging.getLogger(__name__)

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        logger.info("正在加载 EasyOCR 模型...")
        import easyocr
        _reader = easyocr.Reader(["ch_sim", "en"], gpu=False)
        logger.info("EasyOCR 模型加载完成")
    return _reader


def _clean_text(text: str) -> str:
    return re.sub(r"[^\u4e00-\u9fff\w]", "", text)


def _similarity(a: str, b: str) -> float:
    ca = _clean_text(a)
    cb = _clean_text(b)
    if not ca or not cb:
        return 0
    return SequenceMatcher(None, ca, cb).ratio()


def _deduplicate(texts: list[str]) -> list[str]:
    result = []
    for t in texts:
        if not t:
            continue
        if result and _similarity(t, result[-1]) > 0.75:
            continue
        result.append(t)
    return result


def process_subtitles(video_id: int):
    db = SessionLocal()

    subs = db.query(Subtitle).filter(
        Subtitle.video_id == video_id
    ).order_by(Subtitle.frame_index).all()

    if not subs:
        logger.warning(f"[vid={video_id}] 无字幕帧")
        db.close()
        return

    reader = _get_reader()
    texts = []

    for sub in subs:
        if not sub.screenshot_path:
            continue
        try:
            results = reader.readtext(sub.screenshot_path)
            if not results:
                sub.raw_text = ""
                continue

            lines = []
            max_conf = 0
            for (_, text, conf) in results:
                if conf > 0.5:
                    lines.append(text)
                if conf > max_conf:
                    max_conf = conf
            sub.raw_text = "\n".join(lines)
            sub.confidence = max_conf
            texts.append(sub.raw_text)
        except Exception as e:
            logger.warning(f"OCR 帧{sub.frame_index} 失败: {e}")

    db.commit()

    if not texts:
        logger.warning(f"[vid={video_id}] OCR 未识别到任何文字")
        db.close()
        return

    deduped = _deduplicate(texts)
    full_text = "\n".join(deduped)
    logger.info(f"[vid={video_id}] OCR 完成: {len(subs)}帧 → {len(texts)}条识别 → {len(deduped)}条去重")

    result = db.query(VideoResult).filter(VideoResult.video_id == video_id).first()
    if not result:
        result = VideoResult(video_id=video_id)
        db.add(result)
    result.full_subtitle = full_text
    result.subtitle_word_count = len(full_text)
    db.commit()
    db.close()
