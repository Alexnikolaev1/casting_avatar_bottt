import os
from dataclasses import dataclass, field


@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = field(default_factory=lambda: os.environ["BOT_TOKEN"])
    WEBHOOK_SECRET: str = field(default_factory=lambda: os.environ.get("WEBHOOK_SECRET", "supersecret"))
    BOT_USERNAME: str = field(default_factory=lambda: os.environ.get("BOT_USERNAME", "KastingBot"))

    # Yandex
    YANDEX_API_KEY: str = field(default_factory=lambda: os.environ["YANDEX_API_KEY"])
    YANDEX_FOLDER_ID: str = field(default_factory=lambda: os.environ["YANDEX_FOLDER_ID"])

    # YuKassa
    YUKASSA_SHOP_ID: str = field(default_factory=lambda: os.environ["YUKASSA_SHOP_ID"])
    YUKASSA_SECRET_KEY: str = field(default_factory=lambda: os.environ["YUKASSA_SECRET_KEY"])
    YUKASSA_RECEIPT_EMAIL: str = field(
        default_factory=lambda: os.environ.get("YUKASSA_RECEIPT_EMAIL", "buyer@example.com")
    )

    # Database
    DATABASE_URL: str = field(default_factory=lambda: os.environ["DATABASE_URL"])

    # Vercel KV (Redis)
    KV_REST_API_URL: str = field(default_factory=lambda: os.environ.get("KV_REST_API_URL", ""))
    KV_REST_API_TOKEN: str = field(default_factory=lambda: os.environ.get("KV_REST_API_TOKEN", ""))

    # Vercel Blob
    BLOB_READ_WRITE_TOKEN: str = field(default_factory=lambda: os.environ.get("BLOB_READ_WRITE_TOKEN", ""))

    # Cron
    CRON_SECRET: str = field(default_factory=lambda: os.environ.get("CRON_SECRET", "cronsecret"))

    # Business
    PRICE_SINGLE: int = 2000        # 20 руб. в копейках
    PRICE_PACK: int = 10000         # 100 руб. — пакет всех стилей
    PRICE_SINGLE_REF: int = 2000    # для совместимости: реферальная цена = базовой

    # Generation
    MAX_POLL_ATTEMPTS: int = 20
    POLL_INTERVAL_SEC: int = 3
    YANDEX_ULTRA_SIMILARITY: bool = field(
        default_factory=lambda: os.environ.get("YANDEX_ULTRA_SIMILARITY", "true").lower() in ("1", "true", "yes", "on")
    )
    YANDEX_IDENTITY_WEIGHT: str = field(default_factory=lambda: os.environ.get("YANDEX_IDENTITY_WEIGHT", "1.0"))
    YANDEX_STYLE_WEIGHT: str = field(default_factory=lambda: os.environ.get("YANDEX_STYLE_WEIGHT", "0.28"))
    YANDEX_REFERENCE_WEIGHT: str = field(default_factory=lambda: os.environ.get("YANDEX_REFERENCE_WEIGHT", "1.0"))
    YANDEX_MULTI_VARIANT: bool = field(
        default_factory=lambda: os.environ.get("YANDEX_MULTI_VARIANT", "true").lower() in ("1", "true", "yes", "on")
    )
    YANDEX_SECOND_VARIANT_STYLE_WEIGHT: str = field(
        default_factory=lambda: os.environ.get("YANDEX_SECOND_VARIANT_STYLE_WEIGHT", "0.18")
    )
    YANDEX_SECOND_VARIANT_SEED: str = field(
        default_factory=lambda: os.environ.get("YANDEX_SECOND_VARIANT_SEED", "54321")
    )
    YANDEX_THIRD_VARIANT: bool = field(
        default_factory=lambda: os.environ.get("YANDEX_THIRD_VARIANT", "true").lower() in ("1", "true", "yes", "on")
    )
    YANDEX_THIRD_VARIANT_STYLE_WEIGHT: str = field(
        default_factory=lambda: os.environ.get("YANDEX_THIRD_VARIANT_STYLE_WEIGHT", "0.10")
    )
    YANDEX_THIRD_VARIANT_SEED: str = field(
        default_factory=lambda: os.environ.get("YANDEX_THIRD_VARIANT_SEED", "77777")
    )
    FACE_BLEND_ENABLED: bool = field(
        default_factory=lambda: os.environ.get("FACE_BLEND_ENABLED", "true").lower() in ("1", "true", "yes", "on")
    )
    FACE_BLEND_STRENGTH: float = field(
        default_factory=lambda: float(os.environ.get("FACE_BLEND_STRENGTH", "0.70"))
    )
    FACE_BLEND_CORE_STRENGTH: float = field(
        default_factory=lambda: float(os.environ.get("FACE_BLEND_CORE_STRENGTH", "0.96"))
    )
    FACE_BLEND_SIMILARITY_STRENGTH: float = field(
        default_factory=lambda: float(os.environ.get("FACE_BLEND_SIMILARITY_STRENGTH", "0.72"))
    )
    FACE_BLEND_SIMILARITY_CORE_STRENGTH: float = field(
        default_factory=lambda: float(os.environ.get("FACE_BLEND_SIMILARITY_CORE_STRENGTH", "0.97"))
    )
    FACE_BLEND_FANTASY_STRENGTH: float = field(
        default_factory=lambda: float(os.environ.get("FACE_BLEND_FANTASY_STRENGTH", "0.58"))
    )
    FACE_BLEND_FANTASY_CORE_STRENGTH: float = field(
        default_factory=lambda: float(os.environ.get("FACE_BLEND_FANTASY_CORE_STRENGTH", "0.90"))
    )

    # Admin
    ADMIN_IDS: list = field(default_factory=lambda: [
        int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip()
    ])


config = Config()
