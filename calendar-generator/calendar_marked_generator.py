# -*- coding: utf-8 -*-
"""
calendar_marked_generator.py（修正版）

holiday_extractor.py の JSON 出力を読み込み、
対象期間（3ヶ月分）のカレンダーを生成し、
休日（法定・法定外休日）を赤背景で塗りつぶした PDF を出力する。

A4 横向き（landscape）で、数字が確実に表示されるように座標を調整済み。
"""

import json
import sys
import calendar
from datetime import datetime
from reportlab.lib.pagesizes import landscape, A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm

# 固定情報
COMPANY_NAME = "有限会社勝己鉄工所"
COMPANY_ADDRESS = "岡山市中区江並204-5"
PERIOD_TEXT = "2026年4月1日〜2026年6月30日"
WORKER_COUNT_TEXT = "4名"
CREATED_DATE_TEXT = "2026年4月27日"


def load_holidays(json_path):
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    stat = set(data["statutory_holidays"])
    non_stat = set(data["non_statutory_holidays"])
    return stat, non_stat


def detect_period(stat_set, non_stat_set):
    all_days = sorted(list(stat_set | non_stat_set))
    first = datetime.fromisoformat(all_days[0])
    return first.year, first.month


def draw_header(c):
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, 190*mm, "休日及び労働時間に関する協定（変形労働時間制）")

    c.setFont("Helvetica", 11)
    y = 180*mm
    gap = 7*mm

    c.drawString(20*mm, y, f"事業場名：{COMPANY_NAME}")
    y -= gap
    c.drawString(20*mm, y, f"所在地：{COMPANY_ADDRESS}")
    y -= gap
    c.drawString(20*mm, y, f"対象期間：{PERIOD_TEXT}")
    y -= gap
    c.drawString(20*mm, y, f"労働者数：{WORKER_COUNT_TEXT}")
    y -= gap
    c.drawString(20*mm, y, f"作成日：{CREATED_DATE_TEXT}")
    y -= gap

    c.drawString(20*mm, y, "凡例：赤背景＝休日（法定休日・法定外休日を含む）")


def draw_month(c, year, month, x_offset, y_offset, stat_set, non_stat_set):
    cal = calendar.Calendar(firstweekday=6)
    month_days = cal.monthdayscalendar(year, month)

    # タイトル
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_offset, y_offset + 45*mm, f"{year}年 {month}月")

    # 曜日
    c.setFont("Helvetica", 9)
    weekdays = ["日","月","火","水","木","金","土"]
    for i, wd in enumerate(weekdays):
        c.drawString(x_offset + i*18*mm, y_offset + 40*mm, wd)

    # マス
    cell_w = 18*mm
    cell_h = 12*mm

    for row_idx, week in enumerate(month_days):
        for col_idx, day in enumerate(week):
            if day == 0:
                continue

            x = x_offset + col_idx * cell_w
            y = y_offset + (35*mm - row_idx * cell_h)

            d_str = f"{year}-{month:02d}-{day:02d}"

            # 休日
            if d_str in stat_set or d_str in non_stat_set:
                c.setFillColor(colors.red)
                c.rect(x, y - cell_h + 2, cell_w, cell_h, fill=1, stroke=0)
                c.setFillColor(colors.white)
            else:
                c.setFillColor(colors.black)

            c.drawString(x + 2*mm, y - cell_h + 4, str(day))
            c.setFillColor(colors.black)


def create_calendar_pdf(json_path, output_path):
    stat_set, non_stat_set = load_holidays(json_path)
    year, start_month = detect_period(stat_set, non_stat_set)

    c = canvas.Canvas(output_path, pagesize=landscape(A4))

    draw_header(c)

    # 横向きなので広く使える
    base_x = 20*mm
    base_y = 110*mm
    gap_x = 70*mm

    for i in range(3):
        month = start_month + i
        y = year
        if month > 12:
            month -= 12
            y += 1

        draw_month(c, y, month, base_x + i*gap_x, base_y, stat_set, non_stat_set)

    c.showPage()
    c.save()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("使い方: python calendar_marked_generator.py holidays.json output.pdf")
        sys.exit(1)

    create_calendar_pdf(sys.argv[1], sys.argv[2])
    print("PDF を生成しました:", sys.argv[2])
