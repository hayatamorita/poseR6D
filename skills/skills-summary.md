# Skills Summary

`skills/` 配下の各スキルの用途を短く整理した一覧。

## 作業単位別の分類

### 1. 企画・要件整理

| Skill | 役割 |
| --- | --- |
| `interview-me` | 依頼内容が曖昧なときに、目的、利用者、制約を質問で引き出す |
| `idea-refine` | 粗いアイデアを問題定義、選択肢、MVP、やらないことに整理する |
| `spec-driven-development` | 実装前に仕様、成功条件、境界、テスト方針を文書化する |

### 2. プラン・タスク分解

| Skill | 役割 |
| --- | --- |
| `planning-and-task-breakdown` | 仕様を実装可能な小タスクに分け、順序と検証条件を決める |
| `context-engineering` | 作業に必要なルール、仕様、関連ファイル、エラー情報を整理する |
| `using-agent-skills` | 今の作業にどのスキルを使うべきか判断する |

### 3. 実装

| Skill | 役割 |
| --- | --- |
| `incremental-implementation` | 大きな変更を小さく区切って段階的に実装する |
| `source-driven-development` | 公式ドキュメントに基づいて実装判断を行う |
| `api-and-interface-design` | API、型、モジュール境界、コンポーネントpropsなどの契約を設計する |
| `frontend-ui-engineering` | ユーザー向けUIを本番品質で設計・実装する |
| `code-simplification` | 動作を変えずにコードを読みやすく整理する |

### 4. テスト・デバッグ

| Skill | 役割 |
| --- | --- |
| `test-driven-development` | 先にテストを書き、実装、リファクタの順で進める |
| `browser-testing-with-devtools` | 実ブラウザでDOM、Console、Network、画面表示を確認する |
| `debugging-and-error-recovery` | 失敗の根本原因を再現、観察、仮説、検証で追う |
| `performance-optimization` | 計測に基づいて性能ボトルネックを改善する |

### 5. レビュー・品質保証

| Skill | 役割 |
| --- | --- |
| `code-review-and-quality` | 正しさ、可読性、設計、セキュリティ、性能の5軸でレビューする |
| `doubt-driven-development` | 高リスクな判断を意図的に疑い、別視点で検証する |
| `security-and-hardening` | 入力、認証、外部連携、秘密情報などの安全性を確認・強化する |

### 6. ドキュメント・移行

| Skill | 役割 |
| --- | --- |
| `documentation-and-adrs` | 設計判断、仕様、運用知識を将来のために記録する |
| `deprecation-and-migration` | 古いAPIや実装を安全に廃止し、新方式へ移行する |

### 7. Git・CI・リリース

| Skill | 役割 |
| --- | --- |
| `git-workflow-and-versioning` | ブランチ、コミット、差分確認、競合対応を安全に進める |
| `ci-cd-and-automation` | lint、test、build、security auditなどの自動品質ゲートを作る |
| `shipping-and-launch` | 本番リリース前のチェック、監視、ロールバック、段階公開を準備する |

## 標準的な使い分け

| 作業 | 使うスキル |
| --- | --- |
| 何を作るかまだ曖昧 | `interview-me` → `idea-refine` |
| 仕様を決めたい | `spec-driven-development` |
| 実装順序を決めたい | `planning-and-task-breakdown` |
| 実装したい | `incremental-implementation` |
| UIを作りたい | `frontend-ui-engineering` |
| APIや関数境界を決めたい | `api-and-interface-design` |
| 正しいライブラリの使い方を確認したい | `source-driven-development` |
| バグを直したい | `debugging-and-error-recovery` → `test-driven-development` |
| 動作を保証したい | `test-driven-development` |
| ブラウザ画面を確認したい | `browser-testing-with-devtools` |
| 実装後に確認したい | `code-review-and-quality` |
| 高リスクな判断を検証したい | `doubt-driven-development` |
| セキュリティを確認したい | `security-and-hardening` |
| コードを読みやすくしたい | `code-simplification` |
| 判断を記録したい | `documentation-and-adrs` |
| リリースしたい | `shipping-and-launch` |

## 全スキル一覧

| Skill | 要約 | 主な使いどころ |
| --- | --- | --- |
| `using-agent-skills` | どのスキルを使うべきかを判断するためのメタスキル。開発フェーズごとに適切なスキルへ誘導する。 | セッション開始時、タスクの進め方を決める時 |
| `interview-me` | 依頼の本当の目的を一問ずつ掘り下げ、曖昧な要求を明確化する。 | 何を作るべきか不明、要件が薄い時 |
| `idea-refine` | 粗いアイデアを、問題定義、複数案、評価、MVP、やらないことに整理する。 | アイデア出し、企画整理、方向性の絞り込み |
| `spec-driven-development` | 実装前に仕様書を作り、目的、構成、コマンド、テスト方針、境界条件を明文化する。 | 新機能、新規プロジェクト、大きめの変更 |
| `planning-and-task-breakdown` | 仕様や要件を、小さく検証可能な実装タスクに分解する。 | 作業が大きい時、実装順序を決めたい時 |
| `incremental-implementation` | 大きな変更を小さな単位で実装し、各段階で検証しながら進める。 | 複数ファイルにまたがる実装、段階的な機能追加 |
| `test-driven-development` | 先に失敗するテストを書き、最小実装で通し、リファクタする。 | ロジック追加、バグ修正、既存挙動の変更 |
| `source-driven-development` | 公式ドキュメントを確認し、根拠のある実装判断を行う。 | フレームワーク/APIの正しい使い方が重要な時 |
| `frontend-ui-engineering` | 本番品質のUIを作るための設計、レイアウト、状態、視覚品質の指針。 | Gradio/Web UI、画面設計、ユーザー向けUI実装 |
| `api-and-interface-design` | API、型、モジュール境界など、使いにくさや破壊的変更を避けるインターフェース設計を行う。 | REST/GraphQL、関数・クラス境界、フロント/バック間契約 |
| `browser-testing-with-devtools` | 実ブラウザでDOM、Console、Network、スクリーンショット、性能を確認する。 | ブラウザUIの検証、見た目や動作のデバッグ |
| `debugging-and-error-recovery` | 予想外の失敗を、推測ではなく再現、観察、仮説、検証で根本原因まで追う。 | テスト失敗、ビルド失敗、実行時エラー |
| `doubt-driven-development` | 重要な判断を意図的に疑い、別視点で検証してから確定する。 | 高リスク変更、未知のコード、セキュリティ・本番影響がある時 |
| `code-review-and-quality` | 正しさ、可読性、設計、セキュリティ、性能の5軸でレビューする。 | 実装後の確認、マージ前レビュー、他者/AI生成コードの評価 |
| `code-simplification` | 挙動を変えずに、読みやすさと保守性を高めるリファクタリングを行う。 | 動くが複雑なコード、重複や深いネストの整理 |
| `security-and-hardening` | 入力検証、認証認可、秘密情報、外部連携などの安全性を強化する。 | ユーザー入力、認証、ファイルアップロード、外部API、PII |
| `performance-optimization` | 計測に基づいてボトルネックを特定し、性能改善を行う。 | 遅い画面、重い処理、Core Web Vitals、負荷問題 |
| `context-engineering` | エージェントが正しく作業するためのルール、仕様、関連ファイル、エラー情報などの文脈を整える。 | 新セッション開始、出力品質が落ちた時、複雑な作業の前 |
| `documentation-and-adrs` | 設計判断、API、運用知識、将来必要な背景をドキュメントやADRに残す。 | 重要な設計判断、仕様変更、将来の保守に必要な知識の記録 |
| `deprecation-and-migration` | 古いAPIや実装を安全に廃止し、新方式へ移行する手順を管理する。 | 破壊的変更、旧機能の廃止、移行期間が必要な変更 |
| `git-workflow-and-versioning` | ブランチ、コミット、差分確認、競合対応などGit作業を安全に進める。 | コード変更時、コミット作成、並行作業、履歴整理 |
| `ci-cd-and-automation` | lint、type check、test、build、security auditなどの自動品質ゲートを整える。 | CI設定、デプロイ自動化、品質チェックの標準化 |
| `shipping-and-launch` | 本番リリース前の品質、監視、ロールバック、段階的リリースを確認する。 | デプロイ準備、ローンチ、リリースリスク管理 |

## poseR6Dで特に使う可能性が高いスキル

今回のFoundationPose/Gradio構想では、特に以下の順で使うとよい。

1. `idea-refine`: 目的とMVPを絞る
2. `spec-driven-development`: Gradioアプリの仕様を決める
3. `planning-and-task-breakdown`: 実装タスクへ分解する
4. `source-driven-development`: Gradio、VTK/Plotly/PyVista、FoundationPoseの公式情報を確認する
5. `incremental-implementation`: 3D表示、座標変換、右ビュー再現を段階実装する
6. `test-driven-development`: `T_CO -> T_OC` 変換など数式部分をテストする
7. `frontend-ui-engineering`: 左右ビュー、入力欄、結果表示を使いやすく整える
8. `debugging-and-error-recovery`: 座標系、Depth、マスク、表示のズレを切り分ける
9. `documentation-and-adrs`: 採用した3D表示方式や座標系の判断を記録する
