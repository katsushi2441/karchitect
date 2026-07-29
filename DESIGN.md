# DESIGN.md — Kurage Architect

## 1. Visual Theme & Atmosphere

- デザイン方針: 明るいWhite Studio、設計事務所の紙面感、落ち着いた専門性
- 密度: 3ペインの業務UI。情報量は高いが余白で読み分けられる
- キーワード: 清潔、信頼、知的、対話的、成長する文書

## 2. Color Palette & Roles

- Primary: `#10A7A3`
- Primary Dark: `#087C82`
- Text Primary: `#17324D`
- Text Secondary: `#49667F`
- Muted: `#7890A3`
- Border: `#D8E8EB`
- Background: `#F4F9FA`
- Surface: `#FFFFFF`
- Success: `#39B878`
- Warning: `#9B6514`
- Danger: `#B34E3F`

## 3. Typography

- 和文: `"Noto Sans JP", "Yu Gothic", "Hiragino Kaku Gothic ProN"`
- 欧文: `"Helvetica Neue", Arial`
- 等幅: `"Noto Sans Mono CJK JP", "SFMono-Regular", Consolas`
- 本文: 13〜14px、line-height 1.65以上
- 設計書: 14px、line-height 1.8

## 4. Layout

- 左: プロジェクトと工程
- 中央: AIとの要件相談
- 右: 常時更新される設計書、要件、未決事項
- デスクトップを主対象とし、920px以下では設計書をオーバーレイ化

## 5. Components

- カード: 白背景、1px水色境界、12〜15px角丸
- 主ボタン: aquaグラデーション、白文字
- 入力: 白背景、フォーカス時にaqua境界と淡いリング
- AI発言: 白カード
- ユーザー発言: 淡いaquaカード
- 警告: 淡い黄背景。LLMフォールバックを隠さない

## 6. Do / Don't

- Do: 未決事項、仮定、LLM警告を視覚的に明示する
- Do: 出力内容と画面プレビューを同一Markdownから生成する
- Don't: 黒背景、強いネオン、チャットだけで要件状態を隠す
- Don't: LLM未接続を正常動作として見せない

