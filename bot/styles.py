"""
Определение стилей генерации образов.
Каждый стиль содержит название, описание, эмодзи и детальный промт для YandexART.
"""

STYLES: dict[str, dict] = {
    "leader": {
        "id": "leader",
        "name": "Лидер мнений",
        "emoji": "🎤",
        "description": "Деловой портрет бизнес-спикера на сцене",
        "prompt": (
            "ФОКУС: тот же человек, максимальная узнаваемость лица. "
            "Фотореалистичный премиальный деловой cinematic-портрет спикера на большой конференц-сцене. "
            "Уверенная поза, микрофон, строгий темно-синий костюм, белая рубашка, аккуратный галстук. "
            "Мощный сценический свет, объем, LED-экран с абстрактной бизнес-графикой, фон с аудиторией в боке. "
            "Кадр по пояс/3-4, лицо резкое, кожа естественная, high detail, 8K, photorealistic."
        ),
        "negative_prompt": (
            "cartoon, anime, painting, blurry face, deformed face, extra limbs, "
            "bad anatomy, low quality, watermark, text overlay"
        ),
    },
    "cyberpunk": {
        "id": "cyberpunk",
        "name": "Кибер-панк + космос",
        "emoji": "⚡",
        "description": "Неоновый sci-fi образ: киберпанк и космическая атмосфера",
        "prompt": (
            "ФОКУС: тот же человек, лицо максимально узнаваемо. "
            "Фотореалистичный кибер-панк + космос портрет: неоновый sci-fi мегаполис, "
            "звездное небо, туманности и дальние планеты в фоне. "
            "Футуристичная куртка, аккуратные кибер-детали без закрытия лица, объемный контрастный свет, "
            "яркие отражения, частицы, атмосферная дымка, cinematic depth of field. "
            "Кадр по пояс/3-4, sharp face, high detail, 8K, photorealistic."
        ),
        "negative_prompt": (
            "daytime, bright daylight, anime style, cartoon, low quality, blurry face, "
            "deformed, extra limbs, bad anatomy"
        ),
    },
    "medieval": {
        "id": "medieval",
        "name": "Средневековье",
        "emoji": "🏰",
        "description": "Кинематографичный портрет в атмосфере средневекового замка",
        "prompt": (
            "ФОКУС: тот же человек, лицо максимально узнаваемо. "
            "Фотореалистичный портрет в эстетике высокого средневековья: замок, факелы, "
            "теплый огонь, дымка, фактура камня и дерева, историчный костюм из ткани/кожи/металла. "
            "Глубокие тени, объемный cinematic-свет, драматичный контраст, богатый детализированный фон. "
            "Кадр по пояс/3-4, sharp face, natural skin, high detail, photorealistic."
        ),
        "negative_prompt": (
            "modern clothes, futuristic elements, sci-fi, cartoon, anime, deformed face, "
            "gender swap, low quality, blurry, overprocessed skin"
        ),
    },
    "cartoon": {
        "id": "cartoon",
        "name": "Мультфильм",
        "emoji": "🎬",
        "description": "Яркий кинематографичный мульт-образ с узнаваемым лицом",
        "prompt": (
            "ФОКУС: тот же человек, но стиль строго МУЛЬТФИЛЬМ 2D. "
            "Сильный cartoon-рендер: clean lineart, очень жирные контуры, cel-shading, упрощенные анимационные формы, "
            "крупные выразительные черты лица, насыщенная палитра и динамичная мульт-композиция. "
            "Категорически не фотореализм, не semi-realistic и не 3D. "
            "Кадр по пояс/3-4, детализированный художественный фон, динамичная композиция. "
            "High quality 2D cartoon illustration, bold outlines, stylized animation look."
        ),
        "negative_prompt": (
            "photorealistic skin, realistic photo style, semi-realistic portrait, painterly realism, 3d render, horror, creepy, ugly, "
            "disfigured face, wrong person, gender swap, extreme close-up, "
            "low quality, blurry, noisy image, text, watermark"
        ),
    },
    "anime": {
        "id": "anime",
        "name": "Аниме",
        "emoji": "🌸",
        "description": "Современный аниме-арт с сохранением узнаваемости",
        "prompt": (
            "ФОКУС: тот же человек, но стиль строго АНИМЕ. "
            "Премиальный modern anime-арт: чистый lineart, аккуратный cel-shading, "
            "выразительные глаза, насыщенные цвета, атмосферный детализированный фон. "
            "Категорически не фотореализм и не 3D; сохранить узнаваемость лица и тип внешности. "
            "Кадр по пояс/3-4, сбалансированная композиция, cinematic lighting. "
            "High-end anime portrait, film-quality illustration, identity preserved."
        ),
        "negative_prompt": (
            "photorealistic photo style, realistic skin texture, wrong person, gender swap, "
            "oversexualized, nsfw, child-like body, extreme close-up, "
            "deformed anatomy, low quality, blurry, text, watermark"
        ),
    },
}

# Пакет "все образы" — специальная опция
PACK_STYLE_IDS = ["leader", "medieval", "cartoon", "anime", "cyberpunk"]


def get_style(style_id: str) -> dict | None:
    return STYLES.get(style_id)


def get_all_styles() -> list[dict]:
    return list(STYLES.values())
