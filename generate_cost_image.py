import re
import sys
import datetime
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

USE_CSV_TOTALS = False
TITLE = "Daily AWS Cost Summary — Gen 2 (USD)"
OVERRIDES = {
    "Amazon Simple Storage Service": "S3",
    "Amazon Virtual Private Cloud": "VPC",
    "Amazon Elastic Compute Cloud - Compute": "EC2-Instances",
    "Amazon Simple Queue Service": "SQS",
    "Amazon Simple Notification Service": "SNS",
}

GREEN = (31, 92, 58)
LIGHT = (232, 240, 234)
RED = (192, 0, 0)
GOOD = (46, 125, 50)
RED_ON_DARK = (255, 158, 158)
GOOD_ON_DARK = (168, 230, 176)
LINE = (217, 217, 217)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)

S = 2
ROW_H, PAD = 36 * S, 8 * S
COL_A, COL_N = 360 * S, 130 * S

FONT_DIRS = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-{}.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial{}.ttf",
    "C:/Windows/Fonts/arial{}.ttf",
    "/Library/Fonts/Arial{}.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans{}.ttf",
]


def load_font(size, bold=False):
    suffixes = {True: ["Bold", "bd", "-Bold"], False: ["Regular", "", "-Regular"]}[bold]
    for tpl in FONT_DIRS:
        for suf in suffixes:
            try:
                return ImageFont.truetype(tpl.format(suf), size * S)
            except OSError:
                continue
    return ImageFont.load_default()


def clean_name(name: str) -> str:
    """Derive a display name from the CSV service name."""
    name = str(name).strip()
    if name in OVERRIDES:
        return OVERRIDES[name]
    name = re.sub(r"^(Amazon|AWS)\s*", "", name)   # "Amazon X", "AWS X", "AmazonCloudWatch"
    name = re.sub(r"\s*-\s*", "-", name)           # "EC2 - Other" -> "EC2-Other"
    return name or "Other"


def read_costs(path):
    df = pd.read_csv(path, encoding="utf-8-sig")
    df = df.rename(columns={df.columns[0]: "Service"})
    df = df[df["Service"].str.lower() != "total costs"]          # recomputed below
    date_cols = [c for c in df.columns if c not in ("Service", "Service total")]
    df[date_cols] = df[date_cols].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    df["Service"] = df["Service"].map(clean_name)
    if USE_CSV_TOTALS and "Service total" in df:
        df["total"] = pd.to_numeric(df["Service total"], errors="coerce")
    else:
        df["total"] = df[date_cols].sum(axis=1)
    df = df.sort_values("total", ascending=False).reset_index(drop=True)
    return df, date_cols


def trend(prev, cur):
    a, b = round(prev, 2), round(cur, 2)
    return "up" if b > a else "down" if b < a else None


def draw_tri(d, kind, x_right, y_mid, color, size=8 * S):
    """Hollow triangle (△ / ▽) drawn as a polygon so no font glyph is needed."""
    w = size * 1.25
    x0, x1, xm = x_right - w, x_right, x_right - w / 2
    if kind == "up":
        pts = [(x0, y_mid + size / 2), (x1, y_mid + size / 2), (xm, y_mid - size / 2)]
    else:
        pts = [(x0, y_mid - size / 2), (x1, y_mid - size / 2), (xm, y_mid + size / 2)]
    d.polygon(pts, outline=color, width=max(1, S))


def draw_money(d, x_right, y_mid, value, font, color, tri=None, tri_color=None):
    txt = f"${value:,.2f}"
    tri_w = 8 * S * 1.25 + 6 * S
    if tri:
        draw_tri(d, tri, x_right, y_mid, tri_color or color)
        x_right -= tri_w
    d.text((x_right, y_mid), txt, font=font, fill=color, anchor="rm")


def render(df, date_cols, out_path):
    n = len(date_cols)
    width = COL_A + COL_N * (n + 1) + PAD
    notes = [
        "Notes:",
        "• {up} = Cost increased vs previous day",
        "• {down} = Cost decreased vs previous day (green = good)",
        "• No symbol = Cost unchanged vs previous day (compared at 2-decimal rounding)",
        f"• First day ({pd.to_datetime(date_cols[0]):%b-%d}) has no trend indicator",
        f"• Data period: {pd.to_datetime(date_cols[0]):%d %b %Y} – "
        f"{pd.to_datetime(date_cols[-1]):%d %b %Y} ({n} days)",
    ]
    nrows = len(df) + 1                                   # + total row
    height = ROW_H * (3 + nrows) + 20 * S + len(notes) * 26 * S + PAD

    img = Image.new("RGB", (width, height), WHITE)
    d = ImageDraw.Draw(img)
    f_title, f_norm, f_bold = load_font(20, True), load_font(17), load_font(17, True)
    f_small, f_small_b = load_font(15), load_font(15, True)

    right_edges = [COL_A + COL_N * (i + 1) - PAD for i in range(n + 1)]

    # title + legend bars
    d.rectangle([0, 0, width, ROW_H], fill=GREEN)
    d.text((PAD, ROW_H / 2), TITLE, font=f_title, fill=WHITE, anchor="lm")
    d.rectangle([0, ROW_H, width, ROW_H * 1.7], fill=LIGHT)
    ly = ROW_H * 1.35
    x = PAD
    for kind, label in (("up", " Increase (cost up)"), ("down", " Decrease (cost down)")):
        if x == PAD:
            d.text((x, ly), "Trend:", font=f_small, fill=BLACK, anchor="lm")
            x += 54 * S
        draw_tri(d, kind, x + 10 * S, ly, BLACK, 7 * S)
        x += 14 * S
        d.text((x, ly), label.strip(), font=f_small, fill=BLACK, anchor="lm")
        x += d.textlength(label, font=f_small) + 12 * S
        d.text((x, ly), "|", font=f_small, fill=BLACK, anchor="lm")
        x += 18 * S
    d.text((x, ly), "No symbol = Stable", font=f_small, fill=BLACK, anchor="lm")

    # header row
    y = ROW_H * 1.7
    d.rectangle([0, y, width, y + ROW_H], fill=GREEN)
    d.text((PAD, y + ROW_H / 2), "Service", font=f_bold, fill=WHITE, anchor="lm")
    d.text((right_edges[0], y + ROW_H / 2), "Service total", font=f_bold, fill=WHITE, anchor="rm")
    for i, c in enumerate(date_cols):
        d.text((right_edges[i + 1], y + ROW_H / 2), f"{pd.to_datetime(c):%b-%d}*",
               font=f_bold, fill=WHITE, anchor="rm")
    y += ROW_H

    # total row
    tot_days = [df[c].sum() for c in date_cols]
    d.rectangle([0, y, width, y + ROW_H], fill=GREEN)
    ym = y + ROW_H / 2
    d.text((PAD, ym), "Total costs", font=f_bold, fill=WHITE, anchor="lm")
    d.text((right_edges[0], ym), f"${sum(tot_days):,.2f}" if not USE_CSV_TOTALS
           else f"${df['total'].sum():,.2f}", font=f_bold, fill=WHITE, anchor="rm")
    for i, v in enumerate(tot_days):
        t = trend(tot_days[i - 1], v) if i else None
        col = RED_ON_DARK if t == "up" else GOOD_ON_DARK if t == "down" else WHITE
        draw_money(d, right_edges[i + 1], ym, v, f_bold, col, t)
    y += ROW_H

    # service rows
    for _, r in df.iterrows():
        ym = y + ROW_H / 2
        d.text((PAD, ym), r["Service"], font=f_norm, fill=BLACK, anchor="lm")
        d.text((right_edges[0], ym), f"${r['total']:,.2f}", font=f_bold, fill=BLACK, anchor="rm")
        for i, c in enumerate(date_cols):
            t = trend(r[date_cols[i - 1]], r[c]) if i else None
            col = RED if t == "up" else GOOD if t == "down" else BLACK
            draw_money(d, right_edges[i + 1], ym, r[c], f_norm, col, t)
        y += ROW_H
        d.line([0, y, width, y], fill=LINE, width=S)

    # notes
    y += 20 * S
    for i, t in enumerate(notes):
        font = f_small_b if i == 0 else f_small
        kind = "up" if "{up}" in t else "down" if "{down}" in t else None
        if kind:
            head, tail = t.split("{" + kind + "}")
            d.text((PAD, y), head, font=font, fill=BLACK, anchor="lm")
            x = PAD + d.textlength(head, font=font)
            draw_tri(d, kind, x + 12 * S, y, BLACK, 7 * S)
            d.text((x + 16 * S, y), tail, font=font, fill=BLACK, anchor="lm")
        else:
            d.text((PAD, y), t, font=font, fill=BLACK, anchor="lm")
        y += 26 * S

    if out_path.lower().endswith((".jpg", ".jpeg")):
        img.save(out_path, quality=95)
    else:
        img.save(out_path)
    print("saved", out_path)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "cost-breakdown.csv"
    dst = sys.argv[2] if len(sys.argv) > 2 else src.rsplit(".", 1)[0] + ".png"
    data, days = read_costs(src)
    render(data, days, dst)