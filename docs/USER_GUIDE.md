# NovelForge 利用ガイド

## 事前設定

`~/.config/novel-forge/config.yaml` を使います。作業フォルダは`workspace.root`または各コマンドの`--workdir`で指定します。

```yaml
quality:
  max_generation_attempts: 3
```

`max_generation_attempts`は、JSON/schema contract failure時の総生成回数です。初回を含み、transport errorはretryしません。未知・廃止キーは設定エラーです。

## 段階的な実行

```bash
novel-forge plan -w <workdir> "近未来東京 記憶探偵"
novel-forge design -w <workdir> -s <slug> -V 1
novel-forge design -w <workdir> -s <slug> -V 1 -C 1
novel-forge design -w <workdir> -s <slug> -V 1 -C 1 -S 1
novel-forge write -w <workdir> -s <slug> -V 1
novel-forge export -w <workdir> -s <slug> -V 1
```

`design -V 1`はVolume Contract、`-C 1`は既存Volume Contract配下のChapter Contract、`-S 1`は既存Chapter Contract配下のScene Contractを作ります。ChapterとSceneを一つのコマンドで作ることはできません。

全巻のVolume Contractを作る場合は`design -V 0`を使います。ただしChapter / Sceneはそれぞれ個別にauthorしてacceptします。

## 品質ゲート

writeは各sceneについて、次の順にartifactを作ります。

```text
Scene Contract → WriterView → Draft → DraftAudit → QualityDisposition → DesignBundle
```

| finding | 結果 |
|---|---|
| `blocker` | 停止。最大2回のhard repair後も残ればbundleを作らない |
| `constraint_kind != quality` | 停止。severityがmajor/minorでも進めない |
| `quality` のmajor/minor | 固定1回polish後に残れば`deferred`として記録可能 |

`clean`はaudit issueがゼロであることを意味します。`deferred`は全残件をissue index・種類・severity・evidenceまで正確にpinします。

## Export

exportはMarkdown専用です。

```bash
novel-forge export -w <workdir> -s <slug> -V 1 --format markdown
```

exportはselected DesignBundleだけを読み、DraftAuditとQualityDispositionを再照合します。hard finding、non-quality finding、`clean`で隠されたissue、deferred findingの不一致があれば拒否します。

## 再開と調査

```bash
novel-forge resume -w <workdir> -s <slug> -V 1
novel-forge status -w <workdir> -s <slug>
novel-forge runs -w <workdir>
novel-forge attempt -w <workdir> <attempt-id>
```

`resume`は指定巻のwriteとexportを合成実行します。`complete`コマンドは存在しません。plan / designは明示的に完了させてからresumeしてください。
