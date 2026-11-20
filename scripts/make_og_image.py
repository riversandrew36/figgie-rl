"""Regenerate the original link preview using Pillow's embedded font."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def make_image() -> Image.Image:
    image = Image.new("RGB", (1200, 630), "#062622")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((34, 34, 1165, 595), radius=38, fill="#0a3a34", outline="#3f665e", width=2)

    def label(x: int, y: int, content: str, size: int, color: str) -> None:
        draw.text((x, y), content, fill=color, font=ImageFont.load_default(size=size))

    label(84, 98, "TRADE  /  READ THE MARKET", 28, "#ffd166")
    label(84, 172, "Figgie", 94, "#f3fff7")
    label(84, 281, "Learning Lab", 82, "#f3fff7")
    label(88, 418, "Trade cards and guess which suit pays.", 34, "#bee7d6")
    label(88, 472, "Play the daily deal or learn the basics.", 29, "#bee7d6")

    for x, y in [(875, 152), (1007, 152), (875, 284), (1007, 284)]:
        draw.rounded_rectangle((x, y, x + 108, y + 108), radius=18, fill="#164b42")
    gold, coral = "#ffd166", "#ff8f7b"
    # Four pip silhouettes drawn from basic shapes.
    draw.polygon([(929, 172), (899, 205), (959, 205)], fill=gold)
    draw.ellipse((899, 188, 932, 221), fill=gold)
    draw.ellipse((926, 188, 959, 221), fill=gold)
    draw.polygon([(929, 207), (916, 235), (942, 235)], fill=gold)
    draw.ellipse((1030, 181, 1065, 216), fill=coral)
    draw.ellipse((1057, 181, 1092, 216), fill=coral)
    draw.polygon([(1030, 201), (1092, 201), (1061, 236)], fill=coral)
    for x, y in [(913, 305), (897, 326), (929, 326)]:
        draw.ellipse((x, y, x + 32, y + 32), fill=gold)
    draw.polygon([(929, 339), (916, 368), (942, 368)], fill=gold)
    draw.polygon([(1061, 301), (1089, 338), (1061, 375), (1033, 338)], fill=coral)
    return image


if __name__ == "__main__":
    output = Path(__file__).resolve().parents[1] / "figgie_rl/arena/og-image.png"
    make_image().save(output, optimize=True)
