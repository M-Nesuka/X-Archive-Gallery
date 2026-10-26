# X Archive Gallery v1.6.0
<!-- PRE-RELEASE DRAFT. Do not publish until the October 27 release artifacts have been verified. -->

Xの公式データアーカイブから画像・GIF・動画を取り込み、作品をローカルで整理・振り返るWindows向けアプリ「X Archive Gallery」のアップデートです。

## 新機能・改善点

### はじめての取り込みが分かりやすく
- 広い初回セットアップ画面で「保存先を選ぶ → X公式アーカイブZIPを選ぶ → 取り込み開始」を案内。
- Analytics CSVは任意。最初にZIPと一緒に取り込むか、あとから追加できます。
- 設定途中からの再開、保存先を変更する導線、低解像度・高DPI時の配置を改善。

### タグ整理を強化
- タグをグループに分類するツリー表示。
- 複数タグの一括グループ移動・削除・色変更。色はクリックですぐ適用。
- タグの基本設定と自動タグ設定を整理し、意図しない色の変更を修正。
- 赤・黒・白・金を追加して計34色に（銀は以前から対応）。

### 投稿文・ハッシュタグからの自動タグ
- 登録済みのタグ名や「検索する言葉」を投稿本文・ハッシュタグと照合して自動付与。登録語は1投稿から対象。
- 任意の「よく使うハッシュタグを自動登録」を追加。初期OFF。ONの場合、初期設定は20投稿以上・最大50種類で、詳細設定から変更できます。
- 複数画像がある投稿も1投稿として数えます。頻出タグの上限に達した場合は案内を表示。
- 過去の作品への反映、タグの削除・除外状態の保持、文字種の違いによる重複・除外漏れを改善。
- **画像をAI解析してタグを付ける機能ではありません。**

### アーカイブと既存設定の引き継ぎ
- 追加アーカイブの取り込みで同じ投稿・添付の重複表示を抑制し、投稿と添付の関係を保持。
- 保存先を移動した後の取り込みと、同一ライブラリを異なるパスから開いた場合の設定引き継ぎを改善。
- タグ・グループ・お気に入り・非表示などの設定を維持。

### Analyticsの全体順位判定
- 同じライブラリに作品が存在する投稿について、保存済みAnalyticsを合わせて「高成績」「NO.1」を再判定。
- 検索条件や年月の絞り込みで、全体順位は変わりません。
- **新しいCSVに含まれない過去作品の数値は以前の取り込み値のままです。** 全期間の最新数値を自動取得する機能ではありません。
- CSV原本バックアップの初期設定と長いWindows保存先での動作を改善。

### 処理の効率化と不具合修正
- 内容や設定が変わっていない自動タグの再判定を省力化し、大量照合をバックグラウンドで実行。
- 色変更時の一覧再構築や、同色指定時の不要なDB書き込みを削減。
- 大画像の読み込み待ちを制限し、50MiB超のCSVを全読み込み前に拒否。
- 従来の仮想描画・キャッシュ上限・最小化時の省電力を維持。

## v1.5.0からの更新方法
1. アプリを閉じてから、v1.6.0のWindows ZIPを展開します。
2. 展開フォルダー内の `XArchiveGallery.exe` を、以前と同じWindowsユーザーで起動します。
3. 作品が自動で開かない場合は「保存済みの作品を開く」から**これまでの作品フォルダー**を指定します。初期化は不要です。

**注意：** v1.6.0では個人DBがschema 8から9へ移行します。移行前バックアップを保管してください。v1.5.0へ戻す場合は、アプリ終了後、現在のDBを退避して**更新前DBのバックアップ**を復元してください。旧EXEで新DBを直接開かないでください。

## 配布ファイル
- `XArchiveGallery_v1.6.0_Windows_x64.zip`：Windows版アプリ
- `XArchiveGallery_v1.6.0_ThirdPartySources.zip`：同梱第三者ライブラリの対応ソース等
- `SHA256SUMS.txt`：配布ファイルのSHA-256

Windows版ZIPと第三者ソースZIPを**同一Releaseへ併せて公開**します。後者は省略しません。

従来からの日本語・English、ダーク・ライト、複数アカウント、手動タグ、スライドショー、任意Analyticsなどの機能も引き続き利用できます。

アプリの独自ソースはSource Available、第三者ライブラリは各ライセンスに従います。コード署名は未実施です。X Corp.の公式製品ではありません。

---

## English

X Archive Gallery v1.6.0 improves the local Windows application for importing and organizing images, GIFs and videos from your official X data archive.

### What's new
- Clearer first-run setup, with steps for choosing a destination, selecting an archive ZIP and starting the import. Analytics CSV remains optional.
- Tag groups with a tree view, bulk moving/deleting/recoloring, and 34 tag colors, including new red, black, white and gold.
- Rules that apply registered tags using post text and hashtags.
- Optional frequent-hashtag registration, **off by default**, initially requiring 20 posts and allowing up to 50 tags. These limits are configurable.
- Safer archive updates and restoration of settings when the same library is reached via another path.
- Updated overall Analytics rankings across gallery posts with saved metrics. **Past posts absent from a newly imported CSV retain their previously imported figures.** This is not live X analytics.
- Reduced redundant tag work and database writes, background tag processing, safer handling of large images and oversized CSVs.

### Updating from v1.5.0
Close the app, extract the new Windows ZIP, and run `XArchiveGallery.exe` under the same Windows user account. If needed, reconnect the existing artwork folder; do not initialize or replace it.

**Database compatibility:** The personal database is upgraded from schema 8 to schema 9. Downgrading to v1.5.0 requires restoring the pre-upgrade database backup. Keep a separate copy of your current data before restoring.

### Downloads and licensing
The release must include the Windows ZIP, the matching third-party source ZIP, and SHA-256 checksums. The application's original code is Source Available; third-party licenses apply separately. The application is not affiliated with X Corp.

---

*Release draft prepared from the October 27, 2026 update summary. Final artifact hashes, final author's acceptance test, and repository source synchronization must be checked before publishing.*
