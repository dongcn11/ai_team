"""Tiện ích dùng chung."""
import re
import unicodedata

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Đưa tên tiếng Việt có dấu về slug ASCII.

    "Luyện thi IELTS 6.5 cấp tốc" -> "luyen-thi-ielts-6-5-cap-toc"

    Chữ 'đ' (U+0111) không tách được bằng NFD nên phải thay tay trước.
    """
    text = text.replace("Đ", "D").replace("đ", "d")
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = _NON_SLUG.sub("-", text.lower()).strip("-")
    return text or "khoa-hoc"
