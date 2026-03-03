"""UI helpers: форматирование и отображение статусов."""

from bot.styles import get_style

FULL_STATUS_MAP = {
    "completed": "✅ Готово",
    "processing": "⏳ В процессе",
    "pending": "🕐 В очереди",
    "queued": "🕐 В очереди",
    "failed": "❌ Ошибка",
    "canceled": "🚫 Отменено",
}

SHORT_STATUS_MAP = {
    "completed": "✅",
    "processing": "⏳",
    "pending": "🕐",
    "queued": "🕐",
    "failed": "❌",
    "canceled": "🚫",
}


def format_generations_text(gens: list[dict], compact: bool = False) -> str:
    lines = ["📋 <b>Твои последние образы:</b>\n"]
    status_map = SHORT_STATUS_MAP if compact else FULL_STATUS_MAP
    separator = "" if compact else " — "

    for generation in gens:
        style = get_style(generation["style_id"])
        emoji = style["emoji"] if style else "🎨"
        style_name = style["name"] if style else generation["style_id"]
        status = status_map.get(generation["status"], "❓")
        date = generation["created_at"].strftime("%d.%m %H:%M")
        lines.append(f"{emoji} {style_name}{separator}{status} ({date})")

    return "\n".join(lines)
