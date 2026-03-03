"""
Vercel Serverless Function — Worker (вызывается через Cron каждую минуту).
Обрабатывает очередь генераций изображений.
"""

import asyncio
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from http.server import BaseHTTPRequestHandler
from bot.config import config
from bot.worker import run_worker

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        # Проверяем CRON_SECRET для защиты от несанкционированного вызова
        auth = self.headers.get("Authorization", "")
        expected = f"Bearer {config.CRON_SECRET}"
        if auth != expected:
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b"Unauthorized")
            return

        try:
            processed = asyncio.run(run_worker(max_tasks=3))
            result = f'{{"status": "ok", "processed": {processed}}}'
            self.send_response(200)
            self.end_headers()
            self.wfile.write(result.encode())
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'{"status": "error"}')

    def do_POST(self):
        # Можно вызывать и через POST (для тестирования)
        self.do_GET()

    def log_message(self, format, *args):
        pass
