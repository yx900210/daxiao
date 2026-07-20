import json
import logging
import re

import httpx

from backend.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, BONSAI_MODEL
from backend.database import get_setting

logger = logging.getLogger(__name__)

ORGANIZE_DEFAULT = """请将以下视频字幕整理为段落化的完整文稿。要求：
1. 修正明显的 OCR 识别错误
2. 正确断句，合理划分段落
3. 补全标点符号（逗号、句号、问号等）
4. 保持原文的表达风格和措辞，不要添加原文没有的内容

字幕原文：
{subtitle}

请输出整理后的完整文稿："""

VIEWPOINT_DEFAULT = """请从以下文稿中提炼核心观点，按 JSON 格式输出。要求：
1. 提取股市相关的核心观点（3-8 条），每条一句话概括
2. 判断整体情绪倾向（看多/看空/中性）
3. 提取 3-5 个关键词标签

文稿：
{text}

输出格式（仅输出 JSON，不要其他内容）：
{{
  "points": ["观点1", "观点2", ...],
  "sentiment": "看多/看空/中性",
  "keywords": ["标签1", "标签2", ...]
}}"""


def _get_prompt(key: str, default: str) -> str:
    val = get_setting(key, "")
    return val if val else default


def _call_llm(messages: list[dict], max_tokens: int = 16384) -> str | None:
    if not LLM_API_KEY:
        logger.warning("未配置 LLM_API_KEY")
        return None

    try:
        resp = httpx.post(
            f"{LLM_BASE_URL}/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": max_tokens,
            },
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"].get("content") or ""
        if not content:
            finish = data["choices"][0].get("finish_reason", "?")
            logger.error(f"LLM返回空内容, finish_reason={finish}")
            return None

        return content.strip()
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        return None


def organize_subtitle(full_subtitle: str) -> str | None:
    prompt = _get_prompt("prompt_organize", ORGANIZE_DEFAULT).format(subtitle=full_subtitle)
    result = _call_llm([{"role": "user", "content": prompt}])
    if result:
        logger.info(f"整理完成: {len(full_subtitle)} → {len(result)} 字符")
    return result


def extract_viewpoints(text: str) -> dict | None:
    prompt = _get_prompt("prompt_viewpoint", VIEWPOINT_DEFAULT).format(text=text)
    result = _call_llm([{"role": "user", "content": prompt}], max_tokens=2048)
    if not result:
        return None

    json_match = re.search(r"\{[\s\S]*\}", result)
    if json_match:
        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {result[:300]}")
            return None
    else:
        logger.error(f"未找到JSON: {result[:300]}")
        return None

    logger.info(f"观点提取完成: {len(parsed.get('points', []))} 条观点, 情绪={parsed.get('sentiment')}")
    return {
        "points": parsed.get("points", []),
        "sentiment": parsed.get("sentiment", "中性"),
        "keywords": parsed.get("keywords", []),
    }

BONSAI_ELEMENTS_DEFAULT = """请仔细观察这张盆景图片，列出盆景中所包含的所有元素。
包括但不限于：植物种类、山石、人物摆件、建筑物、动物、水体、文字等。
请用简洁的语言逐项列出。"""

BONSAI_MEANING_DEFAULT = """基于盆景中的以下元素：
{elements}

请解读这盆盆景可能蕴含的寓意，结合股市投资语境进行分析。
要求：简洁有力，100-300字。"""


def _image_to_base64(path: str) -> str:
    import base64
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _call_llm_vision(b64: str, prompt: str) -> str | None:
    if not LLM_API_KEY:
        logger.warning("未配置 LLM_API_KEY")
        return None

    try:
        resp = httpx.post(
            f"{LLM_BASE_URL}/chat/completions",
            json={
                "model": BONSAI_MODEL,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": prompt},
                    ],
                }],
                "temperature": 0.3,
                "max_tokens": 1024,
            },
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"].get("content") or ""
        return content.strip() if content else None
    except Exception as e:
        logger.error(f"Bonsai VL 调用失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"VL HTTP {e.response.status_code}: {e.response.text[:500]}")
        return None


def _clean_bonsai_elements(text: str) -> str:
    import re as _re
    text = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL)
    text = _re.sub(r"<thinking>.*?</thinking>", "", text, flags=_re.DOTALL)
    text = _re.sub(r"[a-zA-Z]+", "", text)
    text = _re.sub(r"\s+", " ", text).strip()
    text = _re.sub(r"[,，、\s]+", "、", text)
    return text.strip("、")


def analyze_bonsai(image_path: str) -> tuple[str | None, str | None]:
    logger.info(f"Bonsai 分析: {image_path}")

    try:
        b64 = _image_to_base64(image_path)
    except Exception as e:
        logger.error(f"Bonsai 读取图片失败: {e}")
        return None, None

    from backend.config import BONSAI_MODEL
    elements_prompt = _get_prompt("prompt_bonsai_elements", BONSAI_ELEMENTS_DEFAULT)
    logger.info(f"Bonsai Stage 1: 识别元素 (模型={BONSAI_MODEL})...")
    elements = _call_llm_vision(b64, elements_prompt)
    if not elements:
        logger.error("Bonsai Stage 1 失败")
        return None, None
    elements = _clean_bonsai_elements(elements)
    logger.info(f"Bonsai 元素: {elements[:150]}...")

    meaning_prompt = _get_prompt("prompt_bonsai_meaning", BONSAI_MEANING_DEFAULT).format(elements=elements)
    logger.info("Bonsai Stage 2: 解读寓意...")
    meaning = _call_llm([{"role": "user", "content": meaning_prompt}], max_tokens=1024)
    if not meaning:
        logger.error("Bonsai Stage 2 失败")
        return elements, None
    logger.info(f"Bonsai 寓意: {meaning[:100]}...")

    return elements, meaning
