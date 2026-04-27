# -*- coding: utf-8 -*-
"""
holiday_extractor.py

休日設定カレンダー PDF から、日付ごとの休日区分を抽出するモジュール。

仕様:
    入力 : 休日設定カレンダー PDF
            - 赤色のセル = 法定休日
            - 黄色のセル = 法定外休日
    処理 :
            1. PDF を画像化して各ページを解析
            2. OCR で日付を抽出
            3. セルの背景色を HSV で判定し赤/黄に分類
            4. メモ欄の数字と突き合わせて整合性チェック
    出力 : JSON
            {
                "statutory_holidays":     ["YYYY-MM-DD", ...],
                "non_statutory_holidays": ["YYYY-MM-DD", ...]
            }

依存ライブラリ:
    pip install pdf2image Pillow numpy opencv-python pytesseract

使い方:
    python holiday_extractor.py <input.pdf> [--year 2026] [--out result.json]
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
from pdf2image import convert_from_path
import pytesseract

# ---------------------------------------------------------------------------
# ログ設定
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("holiday_extractor")


# ---------------------------------------------------------------------------
# 色判定の閾値（HSV 空間）
#   OpenCV の HSV は H:0-179, S:0-255, V:0-255
# ---------------------------------------------------------------------------
# 赤は HSV の両端（0 付近と 180 付近）に分かれるため2レンジ
RED_RANGES: List[Tuple[np.ndarray, np.ndarray]] = [
    (np.array([0, 80, 80]), np.array([10, 255, 255])),
    (np.array([170, 80, 80]), np.array([179, 255, 255])),
]
# 黄色レンジ
YELLOW_RANGE: Tuple[np.ndarray, np.ndarray] = (
    np.array([18, 80, 80]),
    np.array([35, 255, 255]),
)

# 1セルと判定する最小面積（ノイズ除去用）
MIN_CELL_AREA = 400


@dataclass
class MonthResult:
    """各月の抽出結果。"""
    month: int
    statutory: List[date] = field(default_factory=list)
    non_statutory: List[date] = field(default_factory=list)
    memo_statutory: Optional[int] = None
    memo_non_statutory: Optional[int] = None
    memo_total: Optional[int] = None


# ---------------------------------------------------------------------------
# PDF -> 画像
# ---------------------------------------------------------------------------
def pdf_to_images(pdf_path: Path, dpi: int = 300) -> List[Image.Image]:
    """PDF を DPI 指定でページごとに画像リストに変換する。"""
    logger.info("PDF を画像に変換中: %s", pdf_path)
    return convert_from_path(str(pdf_path), dpi=dpi)


# ---------------------------------------------------------------------------
# 色マスク生成
# ---------------------------------------------------------------------------
def build_color_masks(bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """赤マスクと黄マスクを生成して返す。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    red_mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
    for lo, hi in RED_RANGES:
        red_mask = cv2.bitwise_or(red_mask, cv2.inRange(hsv, lo, hi))
    yellow_mask = cv2.inRange(hsv, *YELLOW_RANGE)
    kernel = np.ones((3, 3), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
    yellow_mask = cv2.morphologyEx(yellow_mask, cv2.MORPH_OPEN, kernel)
    return red_mask, yellow_mask


# ---------------------------------------------------------------------------
# マスク上の各セルの bounding box を得る
# ---------------------------------------------------------------------------
def extract_colored_cells(mask: np.ndarray) -> List[Tuple[int, int, int, int]]:
    """色マスクからセルの (x, y, w, h) を抽出する。"""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes: List[Tuple[int, int, int, int]] = []
    for c in contours:
        if cv2.contourArea(c) < MIN_CELL_AREA:
            continue
        boxes.append(cv2.boundingRect(c))
    return boxes


# ---------------------------------------------------------------------------
# OCR で bounding box 内の数字（日付）を読む
# ---------------------------------------------------------------------------
def ocr_day_number(bgr: np.ndarray, box: Tuple[int, int, int, int]) -> Optional[int]:
    """指定領域を OCR し、整数 1..31 であれば返す。"""
    x, y, w, h = box
    roi = bgr[y:y + h, x:x + w]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    _, bin_img = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    config = "--psm 7 -c tessedit_char_whitelist=0123456789"
    text = pytesseract.image_to_string(bin_img, config=config)
    m = re.search(r"\d{1,2}", text)
    if m and 1 <= int(m.group(0)) <= 31:
        return int(m.group(0))
    return None


# ---------------------------------------------------------------------------
# メモ欄の数字を読み取り
# ---------------------------------------------------------------------------
MEMO_PATTERNS = {
    "statutory":     re.compile(r"法定休日\s*[::\uff1a]?\s*(\d+)"),
    "non_statutory": re.compile(r"法定外休日\s*[::\uff1a]?\s*(\d+)"),
    "total":         re.compile(r"休日日数\s*計?\s*[::\uff1a]?\s*(\d+)"),
}


def parse_memo(text: str) -> Dict[str, Optional[int]]:
    """メモ欄のテキストから数値を抽出する。"""
    result: Dict[str, Optional[int]] = {
        "statutory": None, "non_statutory": None, "total": None
    }
    for key, pat in MEMO_PATTERNS.items():
        m = pat.search(text)
        if m:
            result[key] = int(m.group(1))
    return result


# ---------------------------------------------------------------------------
# 1 ページ（= 1 か月想定）を解析
# ---------------------------------------------------------------------------
def analyze_page(page_image: Image.Image, year: int, month: int) -> MonthResult:
    """1 ページ分の画像から MonthResult を構築する。"""
    bgr = cv2.cvtColor(np.array(page_image), cv2.COLOR_RGB2BGR)
    red_mask, yellow_mask = build_color_masks(bgr)
    red_boxes = extract_colored_cells(red_mask)
    yellow_boxes = extract_colored_cells(yellow_mask)
    result = MonthResult(month=month)

    # 赤セル = 法定休日
    for box in red_boxes:
        day = ocr_day_number(bgr, box)
        if day is not None:
            try:
                result.statutory.append(date(year, month, day))
            except ValueError:
                logger.debug("不正な日付をスキップ: %04d-%02d-%02d", year, month, day)

    # 黄セル = 法定外休日
    for box in yellow_boxes:
        day = ocr_day_number(bgr, box)
        if day is not None:
            try:
                result.non_statutory.append(date(year, month, day))
            except ValueError:
                logger.debug("不正な日付をスキップ: %04d-%02d-%02d", year, month, day)

    # 重複削除＆ソート
    result.statutory = sorted(set(result.statutory))
    result.non_statutory = sorted(set(result.non_statutory))

    # メモ欄 OCR
    page_text = pytesseract.image_to_string(bgr, lang="jpn")
    memo = parse_memo(page_text)
    result.memo_statutory = memo["statutory"]
    result.memo_non_statutory = memo["non_statutory"]
    result.memo_total = memo["total"]
    return result


# ---------------------------------------------------------------------------
# 整合性チェック
# ---------------------------------------------------------------------------
def check_consistency(mr: MonthResult) -> List[str]:
    """メモ欄の数字と抽出結果を突き合わせ、不一致を警告メッセージで返す。"""
    warnings: List[str] = []
    if mr.memo_statutory is not None and len(mr.statutory) != mr.memo_statutory:
        warnings.append(
            f"{mr.month}月: 法定休日数が不一致 "
            f"(抽出={len(mr.statutory)}, メモ={mr.memo_statutory})"
        )
    if mr.memo_non_statutory is not None and len(mr.non_statutory) != mr.memo_non_statutory:
        warnings.append(
            f"{mr.month}月: 法定外休日数が不一致 "
            f"(抽出={len(mr.non_statutory)}, メモ={mr.memo_non_statutory})"
        )
    if mr.memo_total is not None:
        actual_total = len(mr.statutory) + len(mr.non_statutory)
        if actual_total != mr.memo_total:
            warnings.append(
                f"{mr.month}月: 休日日数計が不一致 "
                f"(抽出={actual_total}, メモ={mr.memo_total})"
            )
    return warnings


# ---------------------------------------------------------------------------
# メイン処理
# ---------------------------------------------------------------------------
def extract_holidays(
    pdf_path: Path,
    year: int,
    start_month: int = 1,
    num_pages: Optional[int] = None,
) -> dict:
    """
    PDF から休日情報を抽出し、JSON シリアライズ可能な dict を返す。

    Args:
        pdf_path:    休日設定カレンダー PDF のパス
        year:        対象年度
        start_month: 最初のページが何月か (default: 1)
        num_pages:   解析するページ数 (default: 全ページ)
    """
    pages = pdf_to_images(pdf_path)
    if num_pages is not None:
        pages = pages[:num_pages]

    all_statutory: List[str] = []
    all_non_statutory: List[str] = []
    all_warnings: List[str] = []

    for i, page in enumerate(pages):
        month = start_month + i
        if month > 12:
            month -= 12  # 年度跨ぎ対応
        logger.info("%d月を解析中...", month)
        mr = analyze_page(page, year, month)

        # 整合性チェック
        warns = check_consistency(mr)
        for w in warns:
            logger.warning(w)
        all_warnings.extend(warns)

        all_statutory.extend(d.isoformat() for d in mr.statutory)
        all_non_statutory.extend(d.isoformat() for d in mr.non_statutory)

    result = {
        "statutory_holidays": sorted(all_statutory),
        "non_statutory_holidays": sorted(all_non_statutory),
    }

    if all_warnings:
        result["warnings"] = all_warnings

    logger.info(
        "抽出完了: 法定休日 %d日, 法定外休日 %d日",
        len(result["statutory_holidays"]),
        len(result["non_statutory_holidays"]),
    )
    return result


# ---------------------------------------------------------------------------
# CLI エントリポイント
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="休日設定カレンダー PDF から休日情報を抽出する"
    )
    parser.add_argument("pdf", type=Path, help="入力 PDF ファイルパス")
    parser.add_argument("--year", type=int, default=2026, help="対象年度 (default: 2026)")
    parser.add_argument("--start-month", type=int, default=1, help="最初のページの月 (default: 1)")
    parser.add_argument("--out", type=Path, default=None, help="出力 JSON ファイルパス")
    args = parser.parse_args()

    if not args.pdf.exists():
        logger.error("PDF ファイルが見つかりません: %s", args.pdf)
        sys.exit(1)

    result = extract_holidays(
        pdf_path=args.pdf,
        year=args.year,
        start_month=args.start_month,
    )

    output_json = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        args.out.write_text(output_json, encoding="utf-8")
        logger.info("JSON を保存しました: %s", args.out)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
