# katsumi-automation

有限会社勝己鉄工所　業務自動化リポジトリ

## フォルダ構成

```
katsumi-automation/
├─ calendar-generator/     # 休日カレンダー解析
│   └─ holiday_extractor.py
├─ 協定届-generator/        # 協定書・協定届 PDF 自動生成
│   ├─ agreement_letter_generator.py
│   └─ agreement_form_generator.py
├─ pdf-templates/          # PDF テンプレート保管
├─ daic-config/            # DAIC 設定ファイル
└─ skills/                 # Claude スキル定義
```

---

## 1. holiday_extractor.py（休日抽出）

休日設定カレンダー PDF から休日を抽出し、JSON で出力します。

### 入力
- 休日設定カレンダー PDF（赤＝法定休日、黄＝法定外休日）

### 出力
```json
{
  "statutory_holidays": ["2026-01-01", "2026-01-04", ...],
  "non_statutory_holidays": ["2026-01-02", "2026-01-03", ...]
}
```

### 使い方
```bash
pip install pdfplumber Pillow
python holiday_extractor.py calendar.pdf --out holidays.json
```

---

## 2. agreement_letter_generator.py（協定書 PDF）

休日 JSON から協定書（誓約書）PDF を自動生成します。

### 機能
- 対象期間自動判定（PDFの最初の月〜最後の月）
- 総労働日数・最長連続労働日数・48h超週数を自動計算
- 会社情報はデフォルト設定済み

### 使い方
```bash
pip install reportlab
python agreement_letter_generator.py holidays.json --out agreement_letter.pdf
```

### オプション
```bash
--company "会社名"          # デフォルト: 有限会社勝己鉄工所
--representative "代表者名"  # デフォルト: 代表取締役 浜場 大介
--worker-rep "労働者代表名"  # デフォルト: 労働者代表 製造部門 影山雅幸
```

---

## 3. agreement_form_generator.py（協定届 PDF）

休日 JSON から協定届（様式第4号）PDF を自動生成します。

### 使い方
```bash
pip install reportlab
python agreement_form_generator.py holidays.json --out agreement_form.pdf
```

### オプション
```bash
--company "会社名"
--representative "代表者名"
--worker-rep "労働者代表名"
--worker-count 10            # 労働者数
--prev-period "2025-10-01 〜 2025-12-31"  # 旧協定期間
```

---

## 4. 全体ワークフロー（PDF → 協定書 + 協定届）

```bash
# Step 1: 休日抽出
python holiday_extractor.py calendar.pdf --out holidays.json

# Step 2: 協定書 PDF 生成
python agreement_letter_generator.py holidays.json --out agreement_letter.pdf

# Step 3: 協定届 PDF 生成
python agreement_form_generator.py holidays.json --out agreement_form.pdf
```

---

## 5. Claude に投げる指示例

Claude に以下のように指示するだけで、PDFを渡せば自動で動きます。

### 指示例 1（フル自動）

```
添付の休日設定カレンダー PDF を解析して、
協定書（誓約書）と協定届（様式第4号）の PDF を生成してください。

スクリプトは以下の GitHub リポジトリにあります：
https://github.com/patra-lab/katsumi-automation

手順：
1. holiday_extractor.py で休日を抽出
2. agreement_letter_generator.py で協定書 PDF を生成
3. agreement_form_generator.py で協定届 PDF を生成
```

### 指示例 2（休日抽出のみ）

```
添付のカレンダー PDF から休日を抽出して JSON で返してください。
赤＝法定休日、黄＝法定外休日です。
https://github.com/patra-lab/katsumi-automation/blob/main/calendar-generator/holiday_extractor.py
```

---

## 6. GitHub raw URL の使い方

Claude がスクリプトを読み込むための URL 形式：

### blob URL（ブラウザで見る用）
```
https://github.com/patra-lab/katsumi-automation/blob/main/フォルダ/ファイル名
```

### raw URL（コードを直接取得）
```
https://raw.githubusercontent.com/patra-lab/katsumi-automation/main/フォルダ/ファイル名
```

### 各スクリプトの URL

| スクリプト | blob URL |
|---|---|
| holiday_extractor.py | `calendar-generator/holiday_extractor.py` |
| agreement_letter_generator.py | `協定届-generator/agreement_letter_generator.py` |
| agreement_form_generator.py | `協定届-generator/agreement_form_generator.py` |

> **注意**: このリポジトリはプライベートのため、raw URL でアクセスするには認証が必要です。
> Claude には blob URL を渡してブラウザで読み込んでもらうのが確実です。

---

## 会社情報（デフォルト値）

| 項目 | 値 |
|---|---|
| 会社名 | 有限会社勝己鉄工所 |
| 住所 | 岡山市中区江並204-5 |
| 代表者 | 代表取締役 浜場 大介 |
| 労働者代表 | 製造部門 影山雅幸 |
