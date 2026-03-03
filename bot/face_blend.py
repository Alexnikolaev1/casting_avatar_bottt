"""Пост-обработка для усиления сходства лица."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None


def _largest_face(faces) -> tuple[int, int, int, int] | None:
    if faces is None or len(faces) == 0:
        return None
    return max(faces, key=lambda item: item[2] * item[3])


def _decode_image(image_bytes: bytes):
    if cv2 is None or np is None:
        return None
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


def _encode_jpeg(image) -> bytes | None:
    ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
    if not ok:
        return None
    return encoded.tobytes()


def _face_detector():
    if cv2 is None:
        return None
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    return detector if not detector.empty() else None


def _match_roi_lighting(source_roi, target_roi):
    """Подгоняет освещение/тон source под target (LAB mean/std), сохраняя стиль сцены."""
    src_lab = cv2.cvtColor(source_roi, cv2.COLOR_BGR2LAB).astype(np.float32)
    tgt_lab = cv2.cvtColor(target_roi, cv2.COLOR_BGR2LAB).astype(np.float32)

    src_mean = src_lab.reshape(-1, 3).mean(axis=0)
    src_std = src_lab.reshape(-1, 3).std(axis=0) + 1e-6
    tgt_mean = tgt_lab.reshape(-1, 3).mean(axis=0)
    tgt_std = tgt_lab.reshape(-1, 3).std(axis=0) + 1e-6

    matched = (src_lab - src_mean) * (tgt_std / src_std) + tgt_mean
    matched = np.clip(matched, 0, 255).astype(np.uint8)
    return cv2.cvtColor(matched, cv2.COLOR_LAB2BGR)


def blend_face(
    source_bytes: bytes,
    generated_bytes: bytes,
    strength: float = 0.70,
    core_strength: float = 0.96,
) -> bytes:
    """Подмешивает лицо с исходного фото в сгенерированное.

    Если не удалось найти лицо или нет OpenCV, возвращает исходный generated_bytes.
    """
    if cv2 is None or np is None:
        logger.warning("OpenCV/Numpy not installed, skip face blending")
        return generated_bytes

    strength = max(0.0, min(1.0, strength))
    core_strength = max(strength, min(1.0, core_strength))
    if strength <= 0.0:
        return generated_bytes

    src = _decode_image(source_bytes)
    gen = _decode_image(generated_bytes)
    if src is None or gen is None:
        return generated_bytes

    detector = _face_detector()
    if detector is None:
        return generated_bytes

    src_gray = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
    gen_gray = cv2.cvtColor(gen, cv2.COLOR_BGR2GRAY)

    src_faces = detector.detectMultiScale(src_gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
    gen_faces = detector.detectMultiScale(gen_gray, scaleFactor=1.1, minNeighbors=5, minSize=(48, 48))
    src_face = _largest_face(src_faces)
    gen_face = _largest_face(gen_faces)
    if not src_face or not gen_face:
        return generated_bytes

    sx, sy, sw, sh = src_face
    gx, gy, gw, gh = gen_face

    src_crop = src[sy:sy + sh, sx:sx + sw]
    if src_crop.size == 0:
        return generated_bytes

    # Масштабируем лицо источника под рамку лица результата.
    src_resized = cv2.resize(src_crop, (gw, gh), interpolation=cv2.INTER_CUBIC)
    gen_roi = gen[gy:gy + gh, gx:gx + gw]
    if gen_roi.shape[:2] != src_resized.shape[:2]:
        return generated_bytes

    # Подгоняем тон/свет лица источника под стиль результата.
    src_matched = _match_roi_lighting(src_resized, gen_roi)

    # Двухзонная маска:
    # - внутреннее ядро сильнее для узнаваемости,
    # - внешнее кольцо мягче для сохранения стилевой оболочки.
    outer_mask = np.zeros((gh, gw), dtype=np.float32)
    core_mask = np.zeros((gh, gw), dtype=np.float32)
    center = (gw // 2, gh // 2)
    outer_axes = (max(1, int(gw * 0.34)), max(1, int(gh * 0.42)))
    core_axes = (max(1, int(gw * 0.23)), max(1, int(gh * 0.30)))
    cv2.ellipse(outer_mask, center, outer_axes, 0, 0, 360, 1.0, -1)
    cv2.ellipse(core_mask, center, core_axes, 0, 0, 360, 1.0, -1)

    blur_outer = max(21, int(max(gw, gh) * 0.22) | 1)
    blur_core = max(15, int(max(gw, gh) * 0.16) | 1)
    outer_mask = cv2.GaussianBlur(outer_mask, (blur_outer, blur_outer), 0)
    core_mask = cv2.GaussianBlur(core_mask, (blur_core, blur_core), 0)

    outer_alpha = outer_mask * strength
    core_alpha = core_mask * core_strength
    alpha = np.maximum(outer_alpha, core_alpha)[:, :, None]

    blended_roi = (src_matched.astype(np.float32) * alpha + gen_roi.astype(np.float32) * (1.0 - alpha))
    blended_roi = np.clip(blended_roi, 0, 255).astype(np.uint8)
    gen[gy:gy + gh, gx:gx + gw] = blended_roi

    encoded = _encode_jpeg(gen)
    return encoded if encoded else generated_bytes
