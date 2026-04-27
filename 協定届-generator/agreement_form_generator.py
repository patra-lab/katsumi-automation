# -*- coding: utf-8 -*-
"""
agreement_form_generator.py

協定届（様式第4号）PDF を自動生成するモジュール。

機能:
    - 休日 JSON から対象期間を自動判定
    - 総労働日数・最長連続労働日数・48時間超週数等を自動計算
    - 様式第4号レイアウトで PDF を生成

依存: pip install reportlab
使い方: python agreement_form_generator.py holidays.json [--out output.pdf]
"""
from __future__ import annotations

import argparse
import calendar
import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


# ---------------------------------------------------------------------------
# フォント設定
# ---------------------------------------------------------------------------
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "C:/Windows/Fonts/msgothic.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
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


# ---------------------------------------------------------------------------
# 期間判定・統計計算（agreement_letter_generator と共通ロジック）
# ---------------------------------------------------------------------------
def detect_period(holidays: dict) -> Tuple[date, date]:
    all_dates: List[date] = []
    for d_str in holidays.get("statutory_holidays", []):
        all_dates.append(date.fromisoformat(d_str))
    for d_str in holidays.get("non_statutory_holidays", []):
        all_dates.append(date.fromisoformat(d_str))
    if not all_dates:
        raise ValueError("休日データが空です")
    min_d, max_d = min(all_dates), max(all_dates)
    start = min_d.replace(day=1)
    _, last_day = calendar.monthrange(max_d.year, max_d.month)
    return start, max_d.replace(day=last_day)


def compute_stats(holidays: dict, start: date, end: date) -> Dict:
    all_holidays = set()
    for d_str in holidays.get("statutory_holidays", []):
        all_holidays.add(date.fromisoformat(d_str))
    for d_str in holidays.get("non_statutory_holidays", []):
        all_holidays.add(date.fromisoformat(d_str))

    total_days = (end - start).days + 1
    holiday_count = sum(1 for i in range(total_days) if (start + timedelta(days=i)) in all_holidays)
    working_days = total_days - holiday_count

    # 最長連続労働日数
    max_consec = 0
    streak = 0
    for i in range(total_days):
        if (start + timedelta(days=i)) not in all_holidays:
            streak += 1
            max_consec = max(max_consec, streak)
        else:
            streak = 0

    # 48時間超の週数計算（1週間ごとに労働時間を集計）
    weeks_over_48 = 0
    consec_weeks_over = 0
    max_consec_weeks_over = 0
    total_weeks = math.ceil(total_days / 7)
    for w in range(total_weeks):
        week_start = start + timedelta(days=w * 7)
        week_hours = 0
        for d in range(7):
            day = week_start + timedelta(days=d)
            if day > end:
                break
            if day not in all_holidays:
                week_hours += 8  # 1日 8時間固定
        if week_hours > 48:
            weeks_over_48 += 1
            consec_weeks_over += 1
            max_consec_weeks_over = max(max_consec_weeks_over, consec_weeks_over)
        else:
            consec_weeks_over = 0

    stat_count = len(holidays.get("statutory_holidays", []))
    non_stat_count = len(holidays.get("non_statutory_holidays", []))

    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "total_calendar_days": total_days,
        "total_holidays": holiday_count,
        "statutory_holidays": stat_count,
        "non_statutory_holidays": non_stat_count,
        "working_days": working_days,
        "max_consecutive_working_days": max_consec,
        "weeks_over_48h": weeks_over_48,
        "max_consecutive_weeks_over_48h": max_consec_weeks_over,
    }


# ---------------------------------------------------------------------------
# 協定届 PDF 生成（様式第4号）
# ---------------------------------------------------------------------------
def generate_agreement_form(
    holidays: dict,
    stats: Dict,
    output_path: Path,
    company_name: str = "有限会社勝己鉄工所",
    representative: str = "代表取締役　浜場　大介",
    worker_rep: str = "労働者代表　製造部門　影山雅幸",
    worker_count: int = 10,
    prev_period: str = "",
) -> Path:
    """協定届（様式第4号）PDF を生成する。"""
    font_name = register_jp_font()
    c = canvas.Canvas(str(output_path), pagesize=A4)
    w, h = A4

    def text(s: str, x: float, y: float, size: int = 9):
        c.setFont(font_name, size)
        c.drawString(x, y, s)

    def draw_row(y: float, label: str, value: str, row_h: float = 7 * mm):
        """1行のラベル+値を描画する。"""
        left = 20 * mm
        mid = 90 * mm
        right = 190 * mm
        c.setStrokeColor(colors.black)
        c.rect(left, y - row_h, mid - left, row_h)
        c.rect(mid, y - row_h, right - mid, row_h)
        text(label, left + 2 * mm, y - row_h + 2 * mm)
        text(value, mid + 2 * mm, y - row_h + 2 * mm)
        return y - row_h

    start = date.fromisoformat(stats["period_start"])
    end = date.fromisoformat(stats["period_end"])

    # --- タイトル ---
    y = h - 25 * mm
    text("様式第4号（第5条関係）", 20 * mm, y, 8)
    y -= 8 * mm
    c.setFont(font_name, 14)
    c.drawCentredString(w / 2, y, "休日及び休日労働に関する協定届")
    y -= 12 * mm

    # --- 事業場情報 ---
    y = draw_row(y, "事業の種類", "製造業")
    y = draw_row(y, "事業の名称", company_name)
    y = draw_row(y, "事業の所在地", "（事業場住所）")
    y = draw_row(y, "労働者数", f"{worker_count}人")
    y -= 5 * mm

    # --- 協定内容 ---
    period_str = f"{start.year}年{start.month}月{start.day}日 〜 {end.year}年{end.month}月{end.day}日"
    y = draw_row(y, "協定の有効期間", period_str)
    if prev_period:
        y = draw_row(y, "旧協定の有効期間", prev_period)
    y -= 3 * mm

    c.setFont(font_name, 10)
    c.drawString(20 * mm, y, "【休日に関する事項】")
    y -= 8 * mm

    y = draw_row(y, "法定休日の日数", f"{stats['statutory_holidays']}日")
    y = draw_row(y, "法定外休日の日数", f"{stats['non_statutory_holidays']}日")
    y = draw_row(y, "休日日数合計", f"{stats['total_holidays']}日")
    y = draw_row(y, "総労働日数", f"{stats['working_days']}日")
    y = draw_row(y, "最長連続労働日数", f"{stats['max_consecutive_working_days']}日")
    y -= 3 * mm

    c.setFont(font_name, 10)
    c.drawString(20 * mm, y, "【48時間を超える週に関する事項】")
    y -= 8 * mm

    y = draw_row(y, "48時間を超える週数", f"{stats['weeks_over_48h']}週")
    y = draw_row(y, "48時間超の最長連続週数", f"{stats['max_consecutive_weeks_over_48h']}週")
    y -= 3 * mm

    c.setFont(font_name, 10)
    c.drawString(20 * mm, y, "【労働時間に関する事項】")
    y -= 8 * mm

    y = draw_row(y, "始業時刻", "8時00分")
    y = draw_row(y, "終業時刻", "17時00分")
    y = draw_row(y, "休憩時間", "60分")
    y = draw_row(y, "1日の所定労働時間", "8時間")
    y -= 10 * mm

    # --- 署名欄 ---
    today = date.today()
    text(f"{today.year}年{today.month}月{today.day}日", 20 * mm, y)
    y -= 10 * mm
    text(f"使用者  {representative}", 20 * mm, y)
    y -= 8 * mm
    text(f"労働者の過半数で組織する労働組合又は労働者の過半数を代表する者", 20 * mm, y)
    y -= 7 * mm
    text(f"  {worker_rep}", 20 * mm, y)

    c.save()
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="協定届（様式第4号）PDF を生成する")
    parser.add_argument("json_file", type=Path, help="休日 JSON ファイルパス")
    parser.add_argument("--out", type=Path, default=Path("agreement_form.pdf"), help="出力 PDF パス")
    parser.add_argument("--company", default="有限会社勝己鉄工所", help="会社名")
    parser.add_argument("--representative", default="代表取締役　浜場　大介", help="代表者名")
    parser.add_argument("--worker-rep", default="労働者代表　製造部門　影山雅幸", help="労働者代表名")
    parser.add_argument("--worker-count", type=int, default=10, help="労働者数")
    parser.add_argument("--prev-period", default="", help="旧協定期間 (例: 2025-10-01 〜 2025-12-31)")
    args = parser.parse_args()

    if not args.json_file.exists():
        print(f"[ERROR] JSON ファイルが見つかりません: {args.json_file}", file=sys.stderr)
        sys.exit(1)

    holidays = json.loads(args.json_file.read_text(encoding="utf-8"))
    start, end = detect_period(holidays)
    stats = compute_stats(holidays, start, end)

    print(f"[期間判定] {stats['period_start']} 〜 {stats['period_end']}")
    print(f"[統計] 労働日={stats['working_days']}, 休日={stats['total_holidays']}, "
          f"最長連続労働={stats['max_consecutive_working_days']}, "
          f"48h超週={stats['weeks_over_48h']}")

    out = generate_agreement_form(
        holidays=holidays,
        stats=stats,
        output_path=args.out,
        company_name=args.company,
        representative=args.representative,
        worker_rep=args.worker_rep,
        worker_count=args.worker_count,
        prev_period=args.prev_period,
    )
    print(f"[完了] 協定届 PDF を保存しました: {out}")


if __name__ == "__main__":
    main()
