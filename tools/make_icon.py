"""서비 아이콘(.ico)과 웹 파비콘을 만듭니다: python tools/make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = Path("C:/Windows/Fonts/malgunbd.ttf")
S = 1024


def tile() -> Image.Image:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    m, r = 56, 230
    # 그림자
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle((m, m + 26, S - m, S - m + 26), r, fill=(60, 20, 10, 110))
    img.alpha_composite(sh.filter(ImageFilter.GaussianBlur(28)))
    # 주황 그라데이션 타일
    grad = Image.new("RGBA", (S, S))
    top, bot = (222, 112, 80), (184, 76, 46)
    gd = ImageDraw.Draw(grad)
    for y in range(S):
        t = y / (S - 1)
        gd.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bot)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((m, m, S - m, S - m), r, fill=255)
    img.paste(grad, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # 말풍선 꼬리(비서 느낌) — 오른쪽 아래
    d.polygon([(S - m - 250, S - m - 6), (S - m - 70, S - m - 6), (S - m - 40, S - m + 70)], fill=(178, 72, 42, 255))
    # 글자 '서' (부드러운 그림자)
    font = ImageFont.truetype(str(FONT), 540)
    box = d.textbbox((0, 0), "서", font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    x, y = (S - w) / 2 - box[0] - 30, (S - h) / 2 - box[1] - 4
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x, y + 18), "서", font=font, fill=(110, 35, 15, 120))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(img)
    d.text((x, y), "서", font=font, fill=(255, 255, 255, 255))
    # 반짝임(AI) — 오른쪽 위 모서리
    cx, cy, R = S - m - 132, m + 128, 58
    star = [(cx, cy - R), (cx + R * .24, cy - R * .24), (cx + R, cy), (cx + R * .24, cy + R * .24),
            (cx, cy + R), (cx - R * .24, cy + R * .24), (cx - R, cy), (cx - R * .24, cy - R * .24)]
    d.polygon(star, fill=(255, 236, 214, 255))
    return img


def main() -> None:
    big = tile()
    out = ROOT / "web" / "seobi.ico"
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    big.resize((256, 256), Image.LANCZOS).save(out, sizes=sizes)
    big.resize((512, 512), Image.LANCZOS).save(ROOT / "web" / "seobi-512.png")
    (ROOT / "web" / "favicon.ico").write_bytes(out.read_bytes())
    print("만들었습니다:", out)


if __name__ == "__main__":
    main()
