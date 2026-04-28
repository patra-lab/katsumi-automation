# -*- coding: utf-8 -*-
"""
calendar_marked_generator.py

holiday_extractor.py の JSON 出力を読み込み、
対象期間（3ヶ月分）のカレンダーを生成し、
休日（法定・法定外）を赤背景で塗りつぶした PDF を出力する。

ヘッダーには以下を自動で印字する：

休日及び労働時間に関する協定（変形労働時間制）
事業場名：有限会社勝己鉄工所
所在地：岡山市中区江並204-5
対象期間：2026年4月1日〜2026年6月30日
労働者数：4名
作成日：2026年4月27日

使い方:
    python calendar_marked_generator.py holidays.json output.pdf
"""

import json
import sys
import calendar
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm


# 固定情報（必要に応じてここを書き換え）
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
    """最初と最後の日付から3ヶ月の対象期間を自動判定"""
    all_days = sorted(list(stat_set | non_stat_set))
    first = datetime.fromisoformat(all_days[0])
    start_year = first.year
    start_month = first.month
    return start_year, start_month


def draw_header(c):
    """申請用ヘッダーを描画"""
    c.setFont("Helvetica-Bold", 14)
    c.drawString(20*mm, 270*mm, "休日及び労働時間に関する協定（変形労働時間制）")

    c.setFont("Helvetica", 10)
    y = 260*mm
    line_gap = 6*mm

    c.drawString(20*mm, y, f"事業場名：{COMPANY_NAME}")
    y -= line_gap
    c.drawString(20*mm, y, f"所在地：{COMPANY_ADDRESS}")
    y -= line_gap
    c.drawString(20*mm, y, f"対象期間：{PERIOD_TEXT}")
    y -= line_gap
    c.drawString(20*mm, y, f"労働者数：{WORKER_COUNT_TEXT}")
    y -= line_gap
    c.drawString(20*mm, y, f"作成日：{CREATED_DATE_TEXT}")
    y -= line_gap

    # 凡例
    y -= 2*mm
    c.drawString(20*mm, y, "凡例：赤背景＝休日（法定休日・法定外休日を含む）")


def draw_month(c, year, month, x_offset, y_offset, stat_set, non_stat_set):
    cal = calendar.Calendar(firstweekday=6)  # 日曜始まり
    month_days = cal.monthdayscalendar(year, month)

    # タイトル
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x_offset, y_offset + 60*mm, f"{year}年 {month}月")

    # 曜日ヘッダ
    c.setFont("Helvetica", 9)
    weekdays = ["日","月","火","水","木","金","土"]
    for i, wd in enumerate(weekdays):
        c.drawString(x_offset + i*20*mm, y_offset + 55*mm, wd)

    # 日付マス
    cell_w = 20*mm
    cell_h = 10*mm
    c.setFont("Helvetica", 9)

    for row_idx, week in enumerate(month_days):
        for col_idx, day in enumerate(week):
            if day == 0:
                continue

            x = x_offset + col_idx * cell_w
            y = y_offset + (50*mm - row_idx * cell_h)

            d_str = f"{year}-{month:02d}-{day:02d}"

            # 休日は赤背景
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

    c = canvas.Canvas(output_path, pagesize=A4)

    # ヘッダー
    draw_header(c)

    # カレンダー本体（3ヶ月横並び）
    base_x = 15*mm
    base_y = 80*mm  # ヘッダーの下に配置
    gap_x = 60*mm

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

    json_path = sys.argv[1]
    output_path = sys.argv[2]

    create_calendar_pdf(json_path, output_path)
    print("PDF を生成しました:", output_path)
