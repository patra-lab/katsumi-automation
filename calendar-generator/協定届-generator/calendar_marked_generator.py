# -*- coding: utf-8 -*-
"""
calendar_marked_generator.py

holiday_extractor.py の JSON 出力を用いて、
3ヶ月分のカレンダーに休日マーク（法定休日・法定外休日ともに赤背景）を付け、
1枚の PDF として出力するスキル。

使い方:
    python calendar_marked_generator.py holidays.json --year 2026 --start-month 1 --out marked_calendar.pdf
"""

from __future__ import annotations

import argparse
import calendar
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# 既存スキルと同じフォント候補
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
]
JP_FONT = "IPAGothic"


def register_jp_font() -> str:
    for path in FONT_CANDIDATES:
        p = Path(path)
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont(JP_FONT, str(p)))
                return JP_FONT
            except Exception:
                continue
    return "Helvetica"


@dataclass(frozen=True)
class HolidayInfo:
    statutory: Set[date]
    non_statutory: Set[date]


def load_holidays(json_path: Path) -> HolidayInfo:
    """holiday_extractor.py の JSON を読み込む。"""
    data: Dict = json.loads(json_path.read_text(encoding="utf-8"))
    stat = {
        datetime.strptime(d, "%Y-%m-%d").date()
        for d in data.get("statutory_holidays", [])
    }
    non_stat = {
        datetime.strptime(d, "%Y-%m-%d").date()
        for d in data.get("non_statutory_holidays", [])
    }
    return HolidayInfo(statutory=stat, non_statutory=non_stat)


def draw_month_calendar(
    c: canvas.Canvas,
    font_name: str,
    year: int,
    month: int,
    holiday_info: HolidayInfo,
    origin_x: float,
    origin_y: float,
    cell_w: float,
    cell_h: float,
) -> None:
    """
    指定位置（origin_x, origin_y）を左上として、1ヶ月分のカレンダーを描画する。

    - 上部に「YYYY年M月」
    - 7列（曜日）、最大6行のグリッド
    - 法定 / 法定外休日はセル背景を赤塗りつぶし
    """

    # タイトル
    c.setFont(font_name, 12)
    title = f"{year}年{month}月"
    c.drawString(origin_x, origin_y, title)

    # 曜日ヘッダ
    weekdays = ["月", "火", "水", "木", "金", "土", "日"]
    header_y = origin_y - 6 * mm
    c.setFont(font_name, 9)
    for i, wd in enumerate(weekdays):
        x = origin_x + i * cell_w
        c.drawString(x + 1.5 * mm, header_y, wd)

    # カレンダー本体（Monday=0）
    cal = calendar.Calendar(firstweekday=0)
    weeks = list(cal.monthdayscalendar(year, month))

    grid_top_y = header_y - 3 * mm

    for row_idx, week in enumerate(weeks):
        for col_idx, day in enumerate(week):
            x0 = origin_x + col_idx * cell_w
            y0 = grid_top_y - row_idx * cell_h
            x1 = x0 + cell_w
            y1 = y0 - cell_h

            # 枠線
            c.setStrokeColor(colors.black)
            c.rect(x0, y1, cell_w, cell_h, stroke=1, fill=0)

            if day == 0:
                continue

            d = date(year, month, day)

            # 休日セルの背景塗りつぶし（法定・法定外とも赤）
            if d in holiday_info.statutory or d in holiday_info.non_statutory:
                c.setFillColor(colors.red)
                c.rect(x0 + 0.5 * mm, y1 + 0.5 * mm, cell_w - 1 * mm, cell_h - 1 * mm, stroke=0, fill=1)
                c.setFillColor(colors.black)
            else:
                c.setFillColor(colors.black)

            # 日付文字
            c.setFont(font_name, 8)
            text_x = x0 + 1.5 * mm
            text_y = y0 - 3.5 * mm
            c.drawString(text_x, text_y, str(day))


def generate_marked_calendar_pdf(
    json_path: Path,
    output_pdf_path: Path,
    year: int,
    start_month: int,
) -> None:
    """3ヶ月分のマーク付きカレンダー PDF を生成する。"""
    holiday_info = load_holidays(json_path)
    font_name = register_jp_font()

    width, height = A4
    c = canvas.Canvas(str(output_pdf_path), pagesize=A4)

    margin_x = 15 * mm
    margin_y = 20 * mm

    # 横3列レイアウト
    months_per_row = 3
    usable_w = width - 2 * margin_x
    cell_w = usable_w / (months_per_row * 7)
    cell_h = 8 * mm  # 行の高さ

    month_block_w = cell_w * 7

    top_y = height - margin_y

    for idx in range(3):
        m = start_month + idx
        y = year
        if m > 12:
            m -= 12
            y += 1  # 年またぎ

        origin_x = margin_x + idx * month_block_w
        origin_y = top_y

        draw_month_calendar(
            c=c,
            font_name=font_name,
            year=y,
            month=m,
            holiday_info=holiday_info,
            origin_x=origin_x,
            origin_y=origin_y,
            cell_w=cell_w,
            cell_h=cell_h,
        )

    c.showPage()
    c.save()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="holiday_extractor の JSON から3ヶ月分のマーク付きカレンダー PDF を生成する"
    )
    parser.add_argument("json", type=Path, help="holiday_extractor 出力 JSON のパス")
    parser.add_argument("--year", type=int, default=2026, help="対象年度 (default: 2026)")
    parser.add_argument("--start-month", type=int, default=1, help="開始月 (default: 1)")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("marked_calendar.pdf"),
        help="出力 PDF ファイルパス (default: marked_calendar.pdf)",
    )

    args = parser.parse_args()

    generate_marked_calendar_pdf(
        json_path=args.json,
        output_pdf_path=args.out,
        year=args.year,
        start_month=args.start_month,
    )


if __name__ == "__main__":
    main()
