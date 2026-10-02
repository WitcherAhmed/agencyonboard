"""Generate the demo brand-guidelines PDF the client uploads during the demo.

  python make_sample_pdf.py
"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).resolve().parent / "CairoBeans_BrandGuidelines.pdf"

BODY = """
<b>1. Brand idea</b><br/>
Cairo Beans exists to make specialty coffee feel like an everyday ritual in New Cairo. The brand is
warm, curious and a little playful. We roast in small batches and we teach people what they are tasting.

<b>2. Brand colors</b>
Primary: Espresso Brown #3B2416<br/>
Secondary: Crema #E8D5B7<br/>
Accent: Teal #1F7A6B<br/>
Neutral: Charcoal #22201E<br/>
Accent colors are reserved for CTA buttons and price tags. Never place body copy on Espresso Brown.

<b>3. Typography</b>
Headlines: Playfair Display, Bold.<br/>
Body: Inter, Regular / Medium.<br/>
Never use all-caps for body text. Keep headlines under 8 words.

<b>4. Tone of voice</b>
Warm, direct, lightly playful. Short sentences. Contractions are fine. We explain the coffee without
talking down to the customer. Encouraging over instructive. Zero pushy sales language, zero shouting.
Emojis are allowed sparingly, at most one per post, and never in the first line.

<b>5. Visual style</b>
Warm natural light photography, matte finishes, visible texture of beans and crema. Shots of hands
preparing coffee are welcome. Overhead flat lays for the menu. Soft shadows, no harsh filters.
Video: short (7-15s), handheld, sound-off readable with captions.

<b>6. Do / Don't</b>
Do: name the origin, the roast level and the tasting notes.<br/>
Do: celebrate the neighborhood, the farmers, the baristas.<br/>
Don't: use stock-photo smiling models with paper cups.<br/>
Don't: use more than three colors in one layout.<br/>
Don't: post price-shaming or "best in town" absolutes.

<b>7. Photography and assets</b>
Logo files are provided as logo_dark.svg, logo_light.svg and a one-color stamp version.
Minimum clear space around the logo equals the height of the crema letter. Never stretch or recolor
the logo. Menu photos are shot on a matte beige surface.

<b>8. Logo</b>
The wordmark reads "Cairo Beans" in a serif with a small bean glyph replacing the dot of the 'i'.
"""

MENU_ROWS = [
    ["Item", "Price", "Note"],
    ["Single Origin V60", "EGP 95", "Light-medium roast, floral, jasmine"],
    ["Caramel Latte", "EGP 110", "House blend, signature drink"],
    ["Flat White", "EGP 85", "Double ristretto"],
    ["Cold Brew Tonic", "EGP 105", "Seasonal, summer only"],
    ["Cold Brew 250ml", "EGP 70", "Take-away bottle"],
    ["Date & Tahini Cookie", "EGP 45", "Homemade daily"],
]


def build() -> Path:
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], textColor="#3B2416", fontSize=24)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor="#1F7A6B", spaceBefore=10)
    body = ParagraphStyle("b", parent=styles["BodyText"], leading=14, fontSize=9.5)

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
    story = [
        Paragraph("Cairo Beans", title),
        Paragraph("Brand Guidelines &amp; Menu Reference - v1.2 - New Cairo, Egypt", styles["Normal"]),
        Spacer(1, 6 * mm),
    ]
    for block in BODY.strip().split("\n\n"):
        lines = block.split("\n")
        first = lines[0]
        if first.startswith("<b>"):
            story.append(Paragraph(first, h2))
            if len(lines) > 1:
                story.append(Paragraph("<br/>".join(lines[1:]), body))
        else:
            story.append(Paragraph("<br/>".join(lines), body))
        story.append(Spacer(1, 3 * mm))

    story.append(Paragraph("Appendix A - Core Menu", h2))
    table = Table(MENU_ROWS, colWidths=[55 * mm, 25 * mm, 75 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), "#3B2416"),
        ("TEXTCOLOR", (0, 0), (-1, 0), "white"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, "#E8D5B7"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), ["#FFFFFF", "#F6F1E9"]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(table)
    doc.build(story)
    return OUT


if __name__ == "__main__":
    print("wrote", build())