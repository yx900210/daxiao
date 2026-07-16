import json
import logging
import re

import httpx

from backend.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

ORGANIZE_PROMPT = """请将以下视频字幕整理为段落化的完整文稿。要求：
1. 修正明显的 OCR 识别错误
2. 正确断句，合理划分段落
3. 补全标点符号（逗号、句号、问号等）
4. 保持原文的表达风格和措辞，不要添加原文没有的内容

字幕原文：
{subtitle}

请输出整理后的完整文稿："""


VIEWPOINT_PROMPT = """请从以下文稿中提炼核心观点，按 JSON 格式输出。要求：
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
    prompt = ORGANIZE_PROMPT.format(subtitle=full_subtitle)
    result = _call_llm([{"role": "user", "content": prompt}])
    if result:
        logger.info(f"整理完成: {len(full_subtitle)} → {len(result)} 字符")
    return result


def extract_viewpoints(text: str) -> dict | None:
    prompt = VIEWPOINT_PROMPT.format(text=text)
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
