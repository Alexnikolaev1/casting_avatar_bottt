"""
Работа с Vercel Blob Storage и Vercel KV (Redis).
"""

import aiohttp
import logging
import json
from collections import deque
from bot.config import config

logger = logging.getLogger(__name__)
_local_queue: deque[str] = deque()


# ─────────────────────────────────────────────
# Vercel Blob Storage
# ─────────────────────────────────────────────

async def upload_bytes_to_blob(data: bytes, filename: str, content_type: str = "image/jpeg") -> str:
    """Загружает байты в Vercel Blob. Возвращает публичный URL."""
    async with aiohttp.ClientSession() as session:
        async with session.put(
            f"https://blob.vercel-storage.com/{filename}",
            data=data,
            headers={
                "Authorization": f"Bearer {config.BLOB_READ_WRITE_TOKEN}",
                "x-content-type": content_type,
                "x-add-random-suffix": "0",
            },
        ) as resp:
            if resp.status not in (200, 201):
                text = await resp.text()
                raise RuntimeError(f"Blob upload failed [{resp.status}]: {text}")
            result = await resp.json()
            url = result.get("url") or result.get("downloadUrl")
            logger.info(f"Uploaded to blob: {url}")
            return url


async def download_from_url(url: str) -> bytes:
    """Скачивает файл по URL."""
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Download failed [{resp.status}]: {url}")
            return await resp.read()


# ─────────────────────────────────────────────
# Vercel KV (Redis) — через REST API
# ─────────────────────────────────────────────

async def _kv_request(method: str, endpoint: str, **kwargs) -> dict:
    url = f"{config.KV_REST_API_URL}{endpoint}"
    headers = {"Authorization": f"Bearer {config.KV_REST_API_TOKEN}"}
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, headers=headers, **kwargs) as resp:
            if resp.status >= 400:
                text = await resp.text()
                raise RuntimeError(f"KV request failed [{resp.status}] {endpoint}: {text}")
            return await resp.json()


def _use_local_queue() -> bool:
    url = (config.KV_REST_API_URL or "").strip()
    token = (config.KV_REST_API_TOKEN or "").strip()
    return (not url or not token or "your-kv-url" in url)


async def _local_lpush(value: str) -> int:
    _local_queue.appendleft(value)
    return len(_local_queue)


async def _local_rpop() -> str | None:
    return _local_queue.pop() if _local_queue else None


async def kv_lpush(key: str, value: str) -> int:
    """Добавляет элемент в начало списка Redis."""
    if _use_local_queue():
        return await _local_lpush(value)
    result = await _kv_request("POST", f"/lpush/{key}/{value}")
    return result.get("result", 0)


async def kv_rpop(key: str) -> str | None:
    """Извлекает элемент с конца списка Redis (FIFO)."""
    if _use_local_queue():
        return await _local_rpop()
    result = await _kv_request("POST", f"/rpop/{key}")
    return result.get("result")


async def kv_llen(key: str) -> int:
    """Возвращает длину списка."""
    if _use_local_queue():
        return len(_local_queue)
    result = await _kv_request("GET", f"/llen/{key}")
    return result.get("result", 0)


async def enqueue_generation_task(task: dict):
    """Добавляет задачу генерации в очередь."""
    task_json = json.dumps(task, ensure_ascii=False)
    try:
        await kv_lpush("generation_queue", task_json)
    except Exception as error:
        logger.warning("KV enqueue failed, using local queue fallback: %s", error)
        await _local_lpush(task_json)
    logger.info(f"Enqueued generation task: gen_id={task.get('generation_id')}")


async def dequeue_generation_task() -> dict | None:
    """Извлекает задачу из очереди. Возвращает None если очередь пуста."""
    try:
        raw = await kv_rpop("generation_queue")
    except Exception as error:
        logger.warning("KV dequeue failed, using local queue fallback: %s", error)
        raw = await _local_rpop()
    if not raw:
        return None
    # Vercel KV может вернуть URL-encoded строку
    import urllib.parse
    raw = urllib.parse.unquote(raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode task: {raw!r} — {e}")
        return None
