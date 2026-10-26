# 投稿文の自動タグ / Automatic post tags — v1.6.0

新規はOFFです。ONにすると、自分で登録したタグと検索する言葉だけで判定します。
別項目「よく使うハッシュタグを自動登録」をONにした場合だけ、20投稿以上のハッシュタグを最大50種類まで登録します。画像解析・外部APIは使いません。

登録タグ「動物」／検索「ねこ,いぬ」のように表へ入力します。いずれかの語で同じタグが付きます。
1投稿だけでも対象。日本語1文字・英数字2文字以下は本文から探しませんが、完全一致ハッシュタグは対象です。
手動付与と個別解除を保持し、ライブラリごとに分離します。旧自動生成タグの既存付与も保持します。
投稿数と種類数は初回セットアップ画面、または自動タグ設定の「基本」で変更できます。保存済みの投稿文があればZIP再読込は不要です。上限に達すると案内を表示します。必須のタグは登録タグと検索語に指定すると、上限外で1投稿から対象になります。複数画像でも1投稿と数え、保存済み全投稿から集計します。登録済みタグ・検索語はこの投稿数制限の対象外です。自動登録をOFFのまま使うこともできます。除外・削除タグは生成せず、旧タグを含めた自動登録数の上限を維持します。見えない異体字指定文字による重複・除外漏れも防ぎます。

## 安全性と処理

アプリDB schema8→9更新前に完全整合性確認・SQLite backupを実施し、DDLをtransactionで反映します。
元画像とライブラリcatalogをこの機能で変更しません。以前のZIPから投稿文だけを読み直せます。
本文はprivate DBのpost_text、自動付与はpost_asset_tags、解除はpost_tag_suppressions、手動はmanual_asset_tagsです。

投稿文・設定・作品対応・手動付与/解除・結果行の署名が同じなら再照合を省略します。
色/グループは照合を変えないため対象外。結果行も検証し、変更の取りこぼしを防ぎます。
照合と署名保存は同じSQLite snapshot/transactionで行い、同時writerで更新できない場合はrollbackして再試行します。
アーカイブ後は子プロセス、タグ設定後は独立DB接続のworkerで照合します。照合中の同時編集・終了を保護します。

旧schema8のEXEへ戻す場合はアプリを終了し、現在DBも保管してから更新前DBのbackupを復元してください。

## English

Automatic matching is opt-in and normally uses registered names/words, even for one post.
A separate opt-in registers frequent hashtags (initially at least 20 posts, at most 50 automatic tag types).
Count posts, not attachments; configure limits under Advanced. Excluded/deleted names are not regenerated.
Use the table: Animals → cat,dog. Manual assignments, recorded removals, legacy tags and library separation are preserved.
Unchanged inputs and exact derived rows reuse the result; large passes run in background workers.
Snapshot transactions and retries protect concurrent updates. A verified backup precedes schema8→9 migration.
To downgrade, close the app, preserve the newer DB and restore its pre-upgrade backup.
