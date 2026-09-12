"""Generate the fifteen needle documents + manifest.json for the needle-test skill.

Synthetic stand-ins for real photos/scans while no camera roll or Gmail inbox is wired up
yet (see CLAUDE.md open question #10). Re-run any time to regenerate deterministically:

    uv run python tests/needles/generate_needles.py
"""

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
DOCS_DIR = HERE / "docs"
MANIFEST_PATH = HERE / "manifest.json"

SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Courier.ttc"

random.seed(42)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def new_page(w: int = 900, h: int = 1200, bg: str = "white") -> Image.Image:
    return Image.new("RGB", (w, h), bg)


def draw_lines(draw: ImageDraw.ImageDraw, lines: list[str], f: ImageFont.FreeTypeFont,
                x: int = 60, y: int = 60, gap: int = 12, fill: str = "black") -> int:
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill)
        y += f.size + gap
    return y


def make_receipt(entity: str, date: str, items: list[tuple[str, float]], currency: str = "USD") -> Image.Image:
    img = new_page(700, 1000)
    d = ImageDraw.Draw(img)
    f_title = font(MONO, 30)
    f_body = font(MONO, 20)
    y = draw_lines(d, [entity.upper()], f_title, x=60, y=50)
    y = draw_lines(d, [f"Date: {date}", "-" * 34], f_body, x=60, y=y + 10)
    total = 0.0
    lines = []
    for name, price in items:
        total += price
        lines.append(f"{name:<24}{currency} {price:6.2f}")
    lines += ["-" * 34, f"{'TOTAL':<24}{currency} {total:6.2f}"]
    draw_lines(d, lines, f_body, x=60, y=y)
    return img, round(total, 2)


def make_card(header: str, fields: dict[str, str]) -> Image.Image:
    img = new_page(900, 560, bg="#eef2f7")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 880, 540], outline="#22344a", width=4)
    f_title = font(SANS, 34)
    f_body = font(SANS, 24)
    y = draw_lines(d, [header], f_title, x=60, y=70)
    lines = [f"{k}: {v}" for k, v in fields.items()]
    draw_lines(d, lines, f_body, x=60, y=y + 20, gap=18)
    return img


def make_form(letterhead: str, date: str, body: list[str]) -> Image.Image:
    img = new_page(850, 1100)
    d = ImageDraw.Draw(img)
    f_head = font(SANS, 26)
    f_body = font(SANS, 18)
    y = draw_lines(d, [letterhead, f"Date: {date}", ""], f_head, x=70, y=60, gap=14)
    draw_lines(d, body, f_body, x=70, y=y + 10, gap=10)
    return img


def make_screenshot(app_bar: str, messages: list[str]) -> Image.Image:
    img = new_page(700, 1400, bg="#111318")
    d = ImageDraw.Draw(img)
    f_bar = font(SANS, 24)
    f_msg = font(SANS, 20)
    d.rectangle([0, 0, 700, 70], fill="#1c1f26")
    d.text((30, 20), app_bar, font=f_bar, fill="white")
    y = 110
    for msg in messages:
        d.rounded_rectangle([30, y, 670, y + 60], radius=14, fill="#2a2f3a")
        d.text((50, y + 18), msg, font=f_msg, fill="#e8e8e8")
        y += 90
    return img


def make_junk_wide() -> Image.Image:
    img = Image.new("RGB", (4000, 220), "#a0a0a0")
    d = ImageDraw.Draw(img)
    for x in range(0, 4000, 40):
        d.line([(x, 0), (x, 220)], fill="#888888")
    return img


def make_junk_tiny() -> Image.Image:
    return Image.new("RGB", (32, 32), "#556677")


def make_junk_blank_photo() -> Image.Image:
    img = Image.new("RGB", (1200, 900), "#7fae7f")
    return img.filter(ImageFilter.GaussianBlur(20))


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []

    receipts = [
        ("Blue Bottle Coffee", "2026-08-14", [("Cold Brew 16oz", 6.50), ("Almond Croissant", 4.75), ("Tax", 0.98)]),
        ("Home Depot #4471", "2026-07-02", [("PVC Pipe 10ft", 12.99), ("Wood Screws 1lb", 8.25), ("Tax", 1.79)]),
        ("Trader Joe's", "2026-08-30", [("Bananas", 1.29), ("Oat Milk", 3.49), ("Bread", 3.99), ("Tax", 0.72)]),
    ]
    for i, (entity, date, items) in enumerate(receipts, start=1):
        img, total = make_receipt(entity, date, items)
        fname = f"receipt_{i:02d}.png"
        img.save(DOCS_DIR / fname)
        manifest.append({
            "file": fname,
            "expected_outcome": "extracted",
            "expected_fields": {"doc_type": "receipt", "entity": entity, "date": date, "amount": total},
        })

    cards = [
        ("MEMBER CARD", {"Name": "A. Priyadarshi", "Member ID": "M-88213-X", "Since": "2024"}),
        ("HEALTH INSURANCE", {"Insured": "A. Priyadarshi", "Policy #": "A4471-B", "Expires": "2029-03"}),
        ("EMPLOYEE ID", {"Name": "A. Priyadarshi", "Dept": "Engineering", "ID": "E-00931"}),
    ]
    for i, (header, fields) in enumerate(cards, start=1):
        img = make_card(header, fields)
        fname = f"card_{i:02d}.png"
        img.save(DOCS_DIR / fname)
        ident_key = [k for k in fields if "#" in k or "ID" in k or "Policy" in k][0]
        manifest.append({
            "file": fname,
            "expected_outcome": "extracted",
            "expected_fields": {"doc_type": "card", "identifiers": [fields[ident_key]]},
        })

    forms = [
        ("City Water Utility — Notice", "2026-06-01", [
            "Dear Resident,", "",
            "This notice confirms your service address has been", "updated in our billing system.",
            "", "Account: 771-2249", "Effective: 2026-06-15",
        ]),
        ("State DMV — Renewal Notice", "2026-05-12", [
            "Your vehicle registration is due for renewal.", "",
            "Plate: 7ABC901", "Renewal fee: $84.00", "Due date: 2026-07-01",
        ]),
        ("Acme Landlord LLC — Lease Notice", "2026-04-20", [
            "This letter serves as notice that your lease", "will renew automatically on 2026-09-01",
            "unless written notice is given 60 days prior.",
        ]),
    ]
    for i, (letterhead, date, body) in enumerate(forms, start=1):
        img = make_form(letterhead, date, body)
        fname = f"form_{i:02d}.png"
        img.save(DOCS_DIR / fname)
        manifest.append({
            "file": fname,
            "expected_outcome": "extracted",
            "expected_fields": {"doc_type": "form", "date": date},
        })

    screenshots = [
        ("Messages", ["Hey, can you send the wifi password?", "It's Sunflower2026!", "Thanks!"]),
        ("Mail — Subject: Flight Confirmation", ["Confirmation #: KX7719Q", "Departs: 2026-09-20 08:15 SFO"]),
        ("Notes", ["Grocery list:", "Milk, eggs, coffee, rice"]),
    ]
    for i, (app_bar, messages) in enumerate(screenshots, start=1):
        img = make_screenshot(app_bar, messages)
        fname = f"screenshot_{i:02d}.png"
        img.save(DOCS_DIR / fname)
        manifest.append({
            "file": fname,
            "expected_outcome": "extracted",
            "expected_fields": {"doc_type": "screenshot_text"},
        })

    # Negative needles — must be dropped, and dropped at the RIGHT gate.
    make_junk_wide().save(DOCS_DIR / "junk_panorama.png")
    manifest.append({"file": "junk_panorama.png", "expected_outcome": "dropped_at_metadata", "expected_fields": {}})

    make_junk_tiny().save(DOCS_DIR / "junk_tiny.png")
    manifest.append({"file": "junk_tiny.png", "expected_outcome": "dropped_at_metadata", "expected_fields": {}})

    make_junk_blank_photo().save(DOCS_DIR / "junk_blank_photo.png")
    manifest.append({"file": "junk_blank_photo.png", "expected_outcome": "dropped_at_ocr", "expected_fields": {}})

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(manifest)} needles to {DOCS_DIR} and {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
