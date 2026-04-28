# -*- coding: utf-8 -*-
"""
agreement_letter_generator.py

休日設定カレンダー PDF から抽出した休日 JSON を元に、
協定書（誓約書）PDF を自動生成するモジュール。

機能:
    - 休日 JSON から対象期間を自動判定
    - 労働日・休日の一覧を算出
    - 労働時間 8:00-17:00（休憩 60 分）固定
    - 協定書 PDF を生成

依存: pip install reportlab
使い方: python agreement_letter_generator.py holidays.json [--out output.pdf]
"""
from __future__ import annotations

import argparse
import calendar
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


# ---------------------------------------------------------------------------
# フォント設定（日本語フォント）
# ---------------------------------------------------------------------------
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "/System/Library/Fonts/HelveticaNeue.ttc",
]
JP_FONT = "IPAGothic"  # 登録名


def register_jp_font() -> str:
    """日本語フォントを探して登録する。見つからなければ Helvetica を返す。"""
    for path in FONT_CANDIDATES:
        p = Path(path)
        if p.exists():
            try:
                pdfmetrics.registerFont(TTFont(JP_FONT, str(p)))
                return JP_FONT
            except Exception:
                continue
    return "Helvetica"


# ---------------------------------------------------------------------------
# 休日 JSON から対象期間を自動判定
# ---------------------------------------------------------------------------
def detect_period(holidays: dict) -> Tuple[date, date]:
    """
    休日 JSON の日付群から、最初の月初日〜最後の月末日を対象期間として返す。
    """
    all_dates: List[date] = []
    for d_str in holidays.get("statutory_holidays", []):
        all_dates.append(date.fromisoformat(d_str))
    for d_str in holidays.get("non_statutory_holidays", []):
        all_dates.append(date.fromisoformat(d_str))
    if not all_dates:
        raise ValueError("休日データが空です")
    min_d = min(all_dates)
    max_d = max(all_dates)
    start = min_d.replace(day=1)
    _, last_day = calendar.monthrange(max_d.year, max_d.month)
    end = max_d.replace(day=last_day)
    return start, end


# ---------------------------------------------------------------------------
# 労働統計計算
# ---------------------------------------------------------------------------
def compute_stats(holidays: dict, start: date, end: date) -> Dict:
    """対象期間の労働統計を計算する。"""
    all_holidays = set()
    for d_str in holidays.get("statutory_holidays", []):
        all_holidays.add(date.fromisoformat(d_str))
    for d_str in holidays.get("non_statutory_holidays", []):
        all_holidays.add(date.fromisoformat(d_str))

    total_days = (end - start).days + 1
    holiday_count = sum(1 for i in range(total_days) if (start + timedelta(days=i)) in all_holidays)
    working_days = total_days - holiday_count

    # 最長連続労働日数
    max_consecutive = 0
    current_streak = 0
    for i in range(total_days):
        d = start + timedelta(days=i)
        if d not in all_holidays:
            current_streak += 1
            max_consecutive = max(max_consecutive, current_streak)
        else:
            current_streak = 0

    # 48時間超の週数（通常8時間×6日=48時間なので、通常0）
    weeks_over_48 = 0
    max_consecutive_weeks_over_48 = 0

    stat = holidays.get("statutory_holidays", [])
    non_stat = holidays.get("non_statutory_holidays", [])

    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "total_calendar_days": total_days,
        "total_holidays": holiday_count,
        "statutory_holidays": len(stat),
        "non_statutory_holidays": len(non_stat),
        "working_days": working_days,
        "max_consecutive_working_days": max_consecutive,
        "weeks_over_48h": weeks_over_48,
        "max_consecutive_weeks_over_48h": max_consecutive_weeks_over_48,
        "work_start": "8:00",
        "work_end": "17:00",
        "break_minutes": 60,
        "daily_work_hours": 8.0,
    }


# ---------------------------------------------------------------------------
# 協定書 PDF 生成
# ---------------------------------------------------------------------------
def generate_agreement_letter(
    holidays: dict,
    stats: Dict,
    output_path: Path,
    company_name: str = "有限会社勝己鉄工所",
    representative: str = "代表取締役　浜場　大介",
    worker_rep: str = "労働者代表　製造部門　影山雅幸",
    worker_count: int = 4,
    address: str = "岡山市中区江並204-5",
) -> Path:
    """協定書（誓約書）PDF を生成する。"""
    font_name = register_jp_font()
    c = canvas.Canvas(str(output_path), pagesize=A4)
    w, h = A4
    y = h - 40 * mm

    def draw_text(text: str, x: float, yy: float, size: int = 10):
        c.setFont(font_name, size)
        c.drawString(x, yy, text)
        return yy - size * 1.6

    start = date.fromisoformat(stats["period_start"])
    end = date.fromisoformat(stats["period_end"])
    period_str = f"{start.year}年{start.month}月{start.day}日 〜 {end.year}年{end.month}月{end.day}日"

    # --- タイトル ---
    y = draw_text("休日及び労働時間に関する協定書", 30 * mm, y, 16)
    y -= 10

    # --- 本文 ---
    y = draw_text(f"対象期間：{period_str}", 20 * mm, y)
    y -= 5
    y = draw_text(f"事業場名：{company_name}", 20 * mm, y)
    y = draw_text(f"所在地　：{address}", 20 * mm, y)
    y = draw_text(f"労働者数：{worker_count}人", 20 * mm, y)
    y -= 10

    y = draw_text("第1条（労働時間）", 20 * mm, y, 11)
    y = draw_text("  始業時刻：8時00分  終業時刻：17時00分  休憩時間：60分", 20 * mm, y)
    y = draw_text(f"  1日の所定労働時間：{stats['daily_work_hours']}時間", 20 * mm, y)
    y -= 10

    y = draw_text("第2条（休日）", 20 * mm, y, 11)
    y = draw_text(f"  法定休日数：{stats['statutory_holidays']}日", 20 * mm, y)
    y = draw_text(f"  法定外休日数：{stats['non_statutory_holidays']}日", 20 * mm, y)
    y = draw_text(f"  休日合計：{stats['total_holidays']}日", 20 * mm, y)
    y -= 5

    # 休日一覧（法定休日）
    y = draw_text("  【法定休日】", 20 * mm, y)
    stat_dates = holidays.get("statutory_holidays", [])
    line = "  "
    for i, d_str in enumerate(stat_dates):
        d = date.fromisoformat(d_str)
        line += f"{d.month}/{d.day} "
        if (i + 1) % 10 == 0:
            y = draw_text(line, 20 * mm, y, 9)
            line = "  "
    if line.strip():
        y = draw_text(line, 20 * mm, y, 9)
    y -= 5

    # 休日一覧（法定外休日）
    y = draw_text("  【法定外休日】", 20 * mm, y)
    non_stat_dates = holidays.get("non_statutory_holidays", [])
    line = "  "
    for i, d_str in enumerate(non_stat_dates):
        d = date.fromisoformat(d_str)
        line += f"{d.month}/{d.day} "
        if (i + 1) % 10 == 0:
            y = draw_text(line, 20 * mm, y, 9)
            line = "  "
    if line.strip():
        y = draw_text(line, 20 * mm, y, 9)
    y -= 10

    y = draw_text("第3条（労働日数）", 20 * mm, y, 11)
    y = draw_text(f"  総労働日数：{stats['working_days']}日", 20 * mm, y)
    y = draw_text(f"  最長連続労働日数：{stats['max_consecutive_working_days']}日", 20 * mm, y)
    y -= 15

    y = draw_text("上記のとおり協定し、届け出る。", 20 * mm, y)
    y -= 20
    today = date.today()
    y = draw_text(f"{today.year}年{today.month}月{today.day}日", 20 * mm, y)
    y -= 15
    y = draw_text(f"使用者  {representative}", 20 * mm, y)
    y -= 10
    y = draw_text(f"労働者代表  {worker_rep}", 20 * mm, y)

    c.save()
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="協定書（誓約書）PDF を生成する")
    parser.add_argument("json_file", type=Path, help="休日 JSON ファイルパス")
    parser.add_argument("--out", type=Path, default=Path("agreement_letter.pdf"), help="出力 PDF パス")
    parser.add_argument("--company", default="有限会社勝己鉄工所", help="会社名")
    parser.add_argument("--representative", default="代表取締役　浜場　大介", help="代表者名")
    parser.add_argument("--worker-rep", default="労働者代表　製造部門　影山雅幸", help="労働者代表名")
    parser.add_argument("--worker-count", type=int, default=4, help="労働者数")
    parser.add_argument("--address", default="岡山市中区江並204-5", help="事業場所在地")
    args = parser.parse_args()

    if not args.json_file.exists():
        print(f"[ERROR] JSON ファイルが見つかりません: {args.json_file}", file=sys.stderr)
        sys.exit(1)

    holidays = json.loads(args.json_
