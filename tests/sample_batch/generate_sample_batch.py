"""Generate a small, varied demo/test batch — NOT the needle-test regression set
(tests/needles/ stays pinned and separate). This batch exists to:

  - give the search demo something to filter by amount/date/identifier (varied Faker content)
  - exercise identifiers/key_values with different real-world shapes (policy #, account #,
    expiry, license #, member ID)
  - show the metadata/OCR gates rejecting something live, without burning demo time on junk
  - look like it actually came off a phone: receipts/cards/forms/junk-photos get composited
    onto a "desk" background with rotation, vignette, grain, and real iPhone EXIF
    (Make=Apple, Model, DateTimeOriginal); screenshots stay flat digital captures with no
    camera EXIF, since that's what a real screenshot looks like.

Structure (per the brief this was built to): 6 receipts, 5 cards/IDs, 5 forms/letters,
5 screenshots-of-text = 21 real docs, + 6 noise images (blurry photo, landscape, selfie,
meme, tiny thumbnail, wide panorama) to demo the gates rejecting something.

    uv run python tests/sample_batch/generate_sample_batch.py

Gitignored like the needles (*.png) — regenerate on demand, don't commit the images.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from faker import Faker
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).parent
DOCS_DIR = HERE / "docs"
MANIFEST_PATH = HERE / "manifest.json"

SANS = "/System/Library/Fonts/Helvetica.ttc"
MONO = "/System/Library/Fonts/Courier.ttc"
IMPACT_ISH = "/System/Library/Fonts/Supplemental/Arial Black.ttf"

SEED = 11
random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

APPLE_MODELS = ["iPhone 13", "iPhone 14 Pro", "iPhone 15", "iPhone 15 Pro", "iPhone SE"]
DESK_COLORS = ["#8a7462", "#5c5c5c", "#3a3a3a", "#7a6a58", "#4a4f57", "#6b5d4f"]


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def new_page(w: int = 900, h: int = 1200, bg: str = "white") -> Image.Image:
    return Image.new("RGB", (w, h), bg)


def draw_lines(draw, lines, f, x=60, y=60, gap=12, fill="black"):
    for line in lines:
        draw.text((x, y), line, font=f, fill=fill)
        y += f.size + gap
    return y


def add_iphone_exif(img: Image.Image) -> Image.Exif:
    exif = Image.Exif()
    exif[0x010F] = "Apple"  # Make
    exif[0x0110] = random.choice(APPLE_MODELS)  # Model
    exif[0x0112] = 1  # Orientation
    exif[0x9003] = fake.date_time_between(start_date="-90d", end_date="now").strftime("%Y:%m:%d %H:%M:%S")
    return exif


def photograph(doc_img: Image.Image, canvas_size: tuple[int, int] = (1350, 1800)) -> Image.Image:
    """Composite a rendered 'paper' onto a desk background with rotation, vignette, blur
    and grain, so it reads as a phone photo rather than a flat digital scan."""
    cw, ch = canvas_size
    canvas = Image.new("RGB", (cw, ch), random.choice(DESK_COLORS))

    # Vignette: darken toward the edges via a radial mask multiply.
    vignette = Image.new("L", (cw, ch), 255)
    vd = ImageDraw.Draw(vignette)
    cx, cy = cw // 2, ch // 2
    max_r = int((cw**2 + ch**2) ** 0.5 / 2)
    for r in range(max_r, 0, -6):
        val = 255 - int(110 * (1 - r / max_r))
        vd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=val)
    canvas = ImageChops.multiply(canvas, vignette.convert("RGB"))

    # Scale the document to fit with margin, rotate with a transparent (alpha) border.
    scale = min((cw * 0.78) / doc_img.width, (ch * 0.78) / doc_img.height)
    doc_resized = doc_img.resize((max(1, int(doc_img.width * scale)), max(1, int(doc_img.height * scale))))
    angle = random.uniform(-7, 7)
    doc_rotated = doc_resized.convert("RGBA").rotate(angle, expand=True)

    px = (cw - doc_rotated.width) // 2 + random.randint(-50, 50)
    py = (ch - doc_rotated.height) // 2 + random.randint(-50, 50)
    canvas.paste(doc_rotated, (px, py), doc_rotated)

    canvas = canvas.filter(ImageFilter.GaussianBlur(random.uniform(0.4, 1.1)))

    # Film-grain-ish noise, blended in lightly.
    noise = Image.effect_noise(canvas.size, 20).convert("L")
    noise_rgb = Image.merge("RGB", (noise, noise, noise))
    canvas = Image.blend(canvas, noise_rgb, alpha=0.05)

    factor = random.uniform(0.85, 1.1)
    canvas = canvas.point(lambda p: max(0, min(255, int(p * factor))))
    return canvas


def save_photo(img: Image.Image, path: Path) -> None:
    photo = photograph(img)
    photo.save(path, exif=add_iphone_exif(photo))


def save_raw_with_exif(img: Image.Image, path: Path) -> None:
    """For images that are already camera-shaped on their own (e.g. a panorama) —
    add EXIF for realism, but skip the desk-compositing step, which would force them
    into a normal frame and erase the exact property (extreme dimensions) being tested."""
    img.save(path, exif=add_iphone_exif(img))


# ---------------------------------------------------------------------------
# Receipts — 6, varied merchants/dates/amounts
# ---------------------------------------------------------------------------

RECEIPT_STYLES = ["coffee_shop", "grocery", "gas_station", "restaurant", "parking", "pharmacy"]


def make_receipt(style: str) -> tuple[Image.Image, dict]:
    entity = fake.company()
    date = fake.date_between(start_date="-2y", end_date="today").isoformat()
    currency = "USD"
    img = new_page(700, 1050)
    d = ImageDraw.Draw(img)
    f_title = font(MONO, 28)
    f_body = font(MONO, 19)

    items: list[tuple[str, float]] = []
    if style == "coffee_shop":
        items = [(fake.random_element(["Latte", "Cold Brew", "Croissant", "Muffin"]), round(random.uniform(3, 9), 2))
                 for _ in range(random.randint(1, 3))]
    elif style == "grocery":
        items = [(fake.word().capitalize(), round(random.uniform(1, 15), 2)) for _ in range(random.randint(3, 8))]
    elif style == "gas_station":
        gallons = round(random.uniform(5, 18), 3)
        price_per_gal = round(random.uniform(3.2, 5.1), 3)
        items = [(f"Unleaded {gallons:.3f} gal", round(gallons * price_per_gal, 2))]
    elif style == "restaurant":
        items = [(fake.word().capitalize(), round(random.uniform(8, 32), 2)) for _ in range(random.randint(2, 5))]
        items.append(("Tip", round(random.uniform(3, 15), 2)))
    elif style == "parking":
        entity = f"{fake.city()} Parking Authority"
        items = [("Parking fee", round(random.uniform(2, 25), 2))]
    else:  # pharmacy
        items = [(fake.word().capitalize() + " Rx", round(random.uniform(5, 60), 2)) for _ in range(random.randint(1, 3))]

    tax = round(sum(p for _, p in items) * 0.08, 2)
    items.append(("Tax", tax))
    total = round(sum(p for _, p in items), 2)

    y = draw_lines(d, [entity.upper()[:34]], f_title, y=50)
    y = draw_lines(d, [f"Date: {date}", "-" * 34], f_body, y=y + 10)
    lines = [f"{name[:22]:<24}{currency} {price:6.2f}" for name, price in items]
    lines += ["-" * 34, f"{'TOTAL':<24}{currency} {total:6.2f}"]
    draw_lines(d, lines, f_body, y=y)

    return img, {"doc_type": "receipt", "entity": entity, "date": date, "amount": total, "currency": currency}


# ---------------------------------------------------------------------------
# Cards / IDs — 5, each a different identifier/key_values shape
# ---------------------------------------------------------------------------

def make_card_member() -> tuple[Image.Image, dict]:
    name = fake.name()
    ident = f"M-{fake.random_number(digits=5)}-{fake.random_uppercase_letter()}"
    since = str(fake.random_int(2018, 2026))
    fields = {"Name": name, "Member ID": ident, "Since": since}
    return _render_card("MEMBER CARD", fields), {
        "doc_type": "card", "identifiers": [ident], "key_values": {"since": since},
    }


def make_card_insurance() -> tuple[Image.Image, dict]:
    name = fake.name()
    ident = f"{fake.random_uppercase_letter()}{fake.random_number(digits=4)}-{fake.random_uppercase_letter()}"
    expiry = f"{fake.random_int(2027, 2031)}-{fake.random_int(1, 12):02d}"
    fields = {"Insured": name, "Policy #": ident, "Expires": expiry}
    return _render_card("HEALTH INSURANCE", fields), {
        "doc_type": "card", "identifiers": [ident], "key_values": {"expires": expiry},
    }


def make_card_employee() -> tuple[Image.Image, dict]:
    name = fake.name()
    ident = f"E-{fake.random_number(digits=5)}"
    dept = fake.job()[:20]
    fields = {"Name": name, "Dept": dept, "ID": ident}
    return _render_card("EMPLOYEE ID", fields), {
        "doc_type": "card", "identifiers": [ident], "key_values": {"dept": dept},
    }


def make_card_license() -> tuple[Image.Image, dict]:
    name = fake.name()
    ident = fake.bothify("DL-#######")
    dob = fake.date_of_birth(minimum_age=18, maximum_age=80).isoformat()
    fields = {"Name": name, "DOB": dob, "License #": ident}
    return _render_card("DRIVER LICENSE", fields), {
        "doc_type": "card", "identifiers": [ident], "key_values": {"dob": dob},
    }


def make_card_account() -> tuple[Image.Image, dict]:
    name = fake.name()
    ident = fake.bothify("ACCT-########")
    balance = f"${random.uniform(50, 5000):,.2f}"
    fields = {"Name": name, "Account #": ident, "Balance": balance}
    return _render_card("ACCOUNT SUMMARY", fields), {
        "doc_type": "card", "identifiers": [ident], "key_values": {"balance": balance},
    }


CARD_MAKERS = [make_card_member, make_card_insurance, make_card_employee, make_card_license, make_card_account]


def _render_card(header: str, fields: dict[str, str]) -> Image.Image:
    img = new_page(900, 560, bg=random.choice(["#eef2f7", "#f7f3ee", "#eef7f0"]))
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, 880, 540], outline="#22344a", width=4)
    f_title = font(SANS, 32)
    f_body = font(SANS, 23)
    y = draw_lines(d, [header], f_title, y=70)
    draw_lines(d, [f"{k}: {v}" for k, v in fields.items()], f_body, y=y + 20, gap=18)
    return img


# ---------------------------------------------------------------------------
# Forms / letters — 5
# ---------------------------------------------------------------------------

FORM_STYLES = ["utility_notice", "dmv_notice", "lease_notice", "medical_form", "invoice"]


def make_form(style: str) -> tuple[Image.Image, dict]:
    date = fake.date_between(start_date="-1y", end_date="today").isoformat()
    img = new_page(850, 1100)
    d = ImageDraw.Draw(img)
    f_head = font(SANS, 25)
    f_body = font(SANS, 18)

    if style == "utility_notice":
        letterhead = f"{fake.city()} Water Utility — Notice"
        body = ["Dear Resident,", "", "This notice confirms your service address has been",
                "updated in our billing system.", "", f"Account: {fake.random_number(digits=7)}",
                f"Effective: {date}"]
    elif style == "dmv_notice":
        letterhead = "State DMV — Renewal Notice"
        body = ["Your vehicle registration is due for renewal.", "",
                f"Plate: {fake.bothify('?######').upper()}",
                f"Renewal fee: ${random.randint(40, 120)}.00", f"Due date: {date}"]
    elif style == "lease_notice":
        letterhead = f"{fake.company()} — Lease Notice"
        body = ["This letter serves as notice that your lease", f"will renew automatically on {date}",
                "unless written notice is given 60 days prior."]
    elif style == "medical_form":
        letterhead = f"{fake.company()} Medical Group"
        body = ["Patient visit summary.", "", f"Patient: {fake.name()}", f"Visit date: {date}",
                f"Provider: Dr. {fake.last_name()}"]
    else:  # invoice
        letterhead = f"{fake.company()} — Invoice"
        amt = round(random.uniform(100, 3000), 2)
        body = [f"Invoice #: {fake.random_number(digits=6)}", f"Date: {date}",
                f"Amount due: ${amt:,.2f}", f"Bill to: {fake.name()}"]

    y = draw_lines(d, [letterhead, f"Date: {date}", ""], f_head, y=60, gap=14)
    draw_lines(d, body, f_body, y=y + 10, gap=10)

    return img, {"doc_type": "form", "date": date}


# ---------------------------------------------------------------------------
# Screenshots — 5. Flat digital captures, NOT photographed, no camera EXIF.
# ---------------------------------------------------------------------------

SCREENSHOT_STYLES = ["messages_dark", "messages_light", "email", "calendar", "banking_alert"]


def make_screenshot(style: str) -> tuple[Image.Image, dict]:
    dark = style == "messages_dark"
    bg = "#111318" if dark else "#f4f4f6"
    bubble_bg = "#2a2f3a" if dark else "#e2e2e8"
    text_fg = "#e8e8e8" if dark else "#111318"
    bar_bg = "#1c1f26" if dark else "#ffffff"
    bar_fg = "white" if dark else "black"

    img = new_page(700, 1250, bg=bg)
    d = ImageDraw.Draw(img)
    f_bar = font(SANS, 24)
    f_msg = font(SANS, 19)
    d.rectangle([0, 0, 700, 70], fill=bar_bg)

    if style in ("messages_dark", "messages_light"):
        app_bar = "Messages"
        messages = [fake.sentence(nb_words=6) for _ in range(random.randint(1, 3))]
    elif style == "email":
        app_bar = f"Mail — {fake.sentence(nb_words=4)[:-1]}"
        messages = [f"From: {fake.email()}", fake.sentence(nb_words=8)]
    elif style == "calendar":
        app_bar = "Calendar"
        messages = [fake.sentence(nb_words=3)[:-1], f"{fake.time()} — {fake.city()}"]
    else:  # banking_alert
        app_bar = "Bank Alert"
        amt = round(random.uniform(5, 500), 2)
        messages = [f"Charge of ${amt:.2f} at {fake.company()}", f"{fake.date_this_year().isoformat()}"]

    d.text((30, 20), app_bar, font=f_bar, fill=bar_fg)
    y = 110
    for msg in messages:
        h = 60 + 20 * (len(msg) // 40)
        d.rounded_rectangle([30, y, 670, y + h], radius=14, fill=bubble_bg)
        d.text((50, y + h // 2 - 10), msg[:60], font=f_msg, fill=text_fg)
        y += h + 30

    return img, {"doc_type": "screenshot_text"}


# ---------------------------------------------------------------------------
# Noise — 6. Just enough to show the gates rejecting something live.
# ---------------------------------------------------------------------------

def make_noise_landscape() -> Image.Image:
    img = new_page(1600, 1200, bg="#7fb0d8")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 800, 1600, 1200], fill="#6a9e5a")
    d.ellipse([1250, 100, 1450, 300], fill="#f5e08a")
    for _ in range(4):
        x = random.randint(0, 1600)
        pts = [(x - 200, 800), (x, 550), (x + 200, 800)]
        d.polygon(pts, fill="#4f7a45")
    return img.filter(ImageFilter.GaussianBlur(1.2))


def make_noise_selfie() -> Image.Image:
    img = new_page(1200, 1600, bg="#cbb79a")
    d = ImageDraw.Draw(img)
    d.ellipse([300, 350, 900, 1150], fill="#e0b48f")  # face-ish blob
    d.ellipse([420, 600, 520, 680], fill="#3a2a20")   # eye
    d.ellipse([680, 600, 780, 680], fill="#3a2a20")   # eye
    return img.filter(ImageFilter.GaussianBlur(3.5))


def make_noise_meme() -> Image.Image:
    img = new_page(1000, 1000, bg=random.choice(["#333333", "#446688"]))
    d = ImageDraw.Draw(img)
    d.ellipse([250, 250, 750, 750], fill="#dddddd")
    f = font(IMPACT_ISH, 60)
    d.text((60, 40), "SAME ENERGY", font=f, fill="white")
    return img


def make_noise_tiny() -> Image.Image:
    return Image.new("RGB", (30, 30), "#556677")


def make_noise_panorama() -> Image.Image:
    img = Image.new("RGB", (4200, 220), "#a0a0a0")
    d = ImageDraw.Draw(img)
    for x in range(0, 4200, 45):
        d.line([(x, 0), (x, 220)], fill="#888888")
    return img


def make_noise_blurry_photo() -> Image.Image:
    img = Image.new("RGB", (1200, 900), random.choice(["#7fae7f", "#a0785a", "#5a7fa0"]))
    return img.filter(ImageFilter.GaussianBlur(22))


# Third element: "desk" (full desk-photo compositing) | "raw_exif" (EXIF only, no
# compositing — for images that are already camera-shaped on their own) | "none".
NOISE_SPECS = [
    ("landscape", make_noise_landscape, "dropped_at_ocr", "desk"),
    ("selfie", make_noise_selfie, "dropped_at_ocr", "desk"),
    ("meme", make_noise_meme, "dropped_at_ocr", "desk"),
    ("tiny_thumbnail", make_noise_tiny, "dropped_at_metadata", "none"),
    ("wide_panorama", make_noise_panorama, "dropped_at_metadata", "raw_exif"),
    ("blurry_photo", make_noise_blurry_photo, "dropped_at_ocr", "desk"),
]


def main() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    counter = 0

    def next_name(prefix: str) -> str:
        nonlocal counter
        counter += 1
        return f"{prefix}_{counter:03d}.png"

    for _ in range(6):
        style = random.choice(RECEIPT_STYLES)
        img, expected = make_receipt(style)
        fname = next_name("receipt")
        save_photo(img, DOCS_DIR / fname)
        manifest.append({"file": fname, "expected_outcome": "extracted", "expected_fields": expected,
                          "style": style, "phone_photo": True})

    for maker in CARD_MAKERS:
        img, expected = maker()
        fname = next_name("card")
        save_photo(img, DOCS_DIR / fname)
        manifest.append({"file": fname, "expected_outcome": "extracted", "expected_fields": expected,
                          "phone_photo": True})

    for style in FORM_STYLES:
        img, expected = make_form(style)
        fname = next_name("form")
        save_photo(img, DOCS_DIR / fname)
        manifest.append({"file": fname, "expected_outcome": "extracted", "expected_fields": expected,
                          "style": style, "phone_photo": True})

    for style in SCREENSHOT_STYLES:
        img, expected = make_screenshot(style)
        fname = next_name("screenshot")
        img.save(DOCS_DIR / fname)  # no photograph(), no EXIF — real screenshots have neither
        manifest.append({"file": fname, "expected_outcome": "extracted", "expected_fields": expected,
                          "style": style, "phone_photo": False})

    for kind, maker, outcome, treatment in NOISE_SPECS:
        img = maker()
        fname = next_name(f"junk_{kind}")
        if treatment == "desk":
            save_photo(img, DOCS_DIR / fname)
        elif treatment == "raw_exif":
            save_raw_with_exif(img, DOCS_DIR / fname)
        else:
            img.save(DOCS_DIR / fname)
        manifest.append({"file": fname, "expected_outcome": outcome, "expected_fields": {},
                          "kind": kind, "phone_photo": treatment != "none"})

    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n")
    real = sum(1 for m in manifest if m["expected_outcome"] == "extracted")
    print(f"Wrote {len(manifest)} images ({real} real docs, {len(manifest) - real} noise) "
          f"to {DOCS_DIR} and {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
