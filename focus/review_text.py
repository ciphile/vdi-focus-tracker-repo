"""Chỉnh lại chữ AI viết trong lời đánh giá cuối ngày / cuối tuần (lọc bằng code, không dựa vào việc AI nghe dặn).

AI viết theo từng mục: một dòng tên mục ngắn, rồi nội dung; các mục cách nhau một dòng trống. Hai việc ở đây:
- drop_wish_heading: bỏ dòng tên mục của lời chúc cuối ngày ("Chúc buổi tối", "Chúc cuối tuần"), chỉ giữ lời chúc.
- sections: tách thành (tên mục, nội dung) để báo cáo HTML tô nổi tên mục.
"""
import re

MAX_HEADING = 40  # tên mục dài hơn thế thì coi là câu văn thường
WISH_HEADING = re.compile(r"^\W*(lời\s+)?chúc\b", re.IGNORECASE)
HEADING_END = ".!?:;,…"


def _split(text):
    """Danh sách đoạn: mỗi đoạn là list dòng (bỏ dòng trống thừa)."""
    out = []
    for para in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [x.rstrip() for x in para.strip().split("\n") if x.strip()]
        if lines:
            out.append(lines)
    return out


def _heading_of(lines):
    """Dòng đầu của đoạn nếu là tên mục (ngắn, không kết thúc như câu văn, phía sau còn nội dung), ngược lại None."""
    first = lines[0].strip()
    if len(lines) >= 2 and len(first) <= MAX_HEADING and first[-1] not in HEADING_END:
        return first
    return None


def sections(text):
    """[(tên mục hoặc None, [các dòng nội dung])] theo thứ tự trong text."""
    out = []
    for lines in _split(text):
        head = _heading_of(lines)
        out.append((head, lines[1:] if head else lines))
    return out


def drop_wish_heading(text):
    """Bỏ dòng tên mục của lời chúc; phần còn lại giữ nguyên. Không có thì trả lại đúng text ban đầu."""
    if not text:
        return text
    paras = _split(text)
    changed = False
    out = []
    for lines in paras:
        head = _heading_of(lines)
        if head and WISH_HEADING.match(head):
            lines, changed = lines[1:], True
        out.append("\n".join(lines))
    return "\n\n".join(out) if changed else text
