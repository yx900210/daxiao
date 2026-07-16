import json
import logging

import httpx

from backend.config import LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

logger = logging.getLogger(__name__)

PROMPT = """请将以下视频字幕整理为段落化的完整文稿。要求：
1. 修正明显的 OCR 识别错误
2. 正确断句，合理划分段落
3. 补全标点符号（逗号、句号、问号等）
4. 保持原文的表达风格和措辞，不要添加原文没有的内容

字幕原文：
{subtitle}

请输出整理后的完整文稿："""


def organize_subtitle(full_subtitle: str) -> str | None:
    if not LLM_API_KEY:
        logger.warning("未配置 LLM_API_KEY, 跳过整理")
        return None

    prompt = PROMPT.format(subtitle=full_subtitle)

    try:
        resp = httpx.post(
            f"{LLM_BASE_URL}/chat/completions",
            json={
                "model": LLM_MODEL,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 16384,
            },
            headers={
                "Authorization": f"Bearer {LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        logger.info(f"LLM 响应状态码: {resp.status_code}, 响应keys: {list(data.keys())}, 总chars: {len(resp.text)}")
        
        if "choices" not in data:
            logger.error(f"LLM 响应格式异常, 完整响应: {json.dumps(data, ensure_ascii=False)[:500]}")
            return None
            
        content = data["choices"][0]["message"].get("content") or ""
        if not content:
            content = data["choices"][0]["message"].get("reasoning_content") or ""
            logger.warning(f"content为空, 使用reasoning_content: {len(content)}字符")

        if not content:
            logger.error(f"LLM返回空内容, 完整message: {json.dumps(data['choices'][0]['message'], ensure_ascii=False)[:1000]}")
            return None

        logger.info(f"LLM 整理完成: {len(full_subtitle)} → {len(content)} 字符")
        return content.strip()
    except Exception as e:
        logger.error(f"LLM 调用失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"HTTP {e.response.status_code}: {e.response.text[:500]}")
        return None
