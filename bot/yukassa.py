"""
Интеграция с ЮKassa (ex-Яндекс.Касса).
Документация: https://yookassa.ru/developers/
"""

import uuid
import aiohttp
import logging
from bot.config import config

logger = logging.getLogger(__name__)
YUKASSA_API = "https://api.yookassa.ru/v3"


def _auth():
    return aiohttp.BasicAuth(config.YUKASSA_SHOP_ID, config.YUKASSA_SECRET_KEY)


def _receipt(description: str, amount_rub: str) -> dict:
    # Для магазинов с включенной 54-ФЗ ЮKassa требует чек в каждом платеже.
    return {
        "customer": {"email": config.YUKASSA_RECEIPT_EMAIL},
        "items": [
            {
                "description": description[:128],
                "quantity": "1.00",
                "amount": {"value": amount_rub, "currency": "RUB"},
                "vat_code": "1",
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }
        ],
    }


async def create_payment(
    amount_kopecks: int,
    user_id: int,
    generation_ids: list,
    style_id: str,
    is_pack: bool,
    return_url: str,
    idempotence_key: str = None,
) -> dict:
    if idempotence_key is None:
        idempotence_key = str(uuid.uuid4())

    amount_rub = f"{amount_kopecks / 100:.2f}"
    description = (
        f"Пакет образов — Твой личный кастинг"
        if is_pack else
        f"Образ в стиле «{style_id}» — Твой личный кастинг"
    )

    payload = {
        "amount": {"value": amount_rub, "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "capture": True,
        "description": description,
        "receipt": _receipt(description, amount_rub),
        "metadata": {
            "user_id": str(user_id),
            "generation_ids": ",".join(str(g) for g in generation_ids),
            "style_id": style_id,
            "is_pack": str(is_pack).lower(),
        },
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{YUKASSA_API}/payments",
            json=payload,
            auth=_auth(),
            headers={"Idempotence-Key": idempotence_key, "Content-Type": "application/json"},
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            data = await resp.json()
            if resp.status not in (200, 201):
                raise RuntimeError(f"YuKassa error [{resp.status}]: {data}")

            payment_id = data["id"]
            confirmation_url = data["confirmation"]["confirmation_url"]
            logger.info(f"Payment created: id={payment_id}, amount={amount_rub}, user={user_id}")
            return {
                "payment_id": payment_id,
                "confirmation_url": confirmation_url,
                "status": data["status"],
                "idempotence_key": idempotence_key,
            }


async def get_payment_info(payment_id: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{YUKASSA_API}/payments/{payment_id}",
            auth=_auth(),
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            return await resp.json()
