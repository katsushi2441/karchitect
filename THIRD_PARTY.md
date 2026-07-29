# Third-party OSS

Kurage Architectは以下のOSSから設計思想とワークフローを参照しています。
各リポジトリは`vendor/`以下のGitサブモジュールとして固定されています。

| OSS | 固定コミット | ライセンス | Kurage Architectでの利用 |
|---|---|---|---|
| [FoundationAgents/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | `11cdf466d042aece04fc6cfd13b28e1a70341b1f` | MIT | PRDの目標、ユーザーストーリー、P0/P1/P2、PRD→設計の工程を参照 |
| [github/spec-kit](https://github.com/github/spec-kit) | `be33d2a5f6b9f098b108273df770fbc3a363ab2a` | MIT | specify/clarify/plan/review工程、未決事項と受入条件の品質確認を参照 |
| [AntonOsika/gpt-engineer](https://github.com/AntonOsika/gpt-engineer) | `a90fcd543eedcc0ff2c34561bc0785d2ba83c47e` | MIT | clarifyモードの「一度に一問」「仮定を明示」を参照。上流はアーカイブ済み |
| [mermaid-js/mermaid](https://github.com/mermaid-js/mermaid) | npm `11.16.0` | MIT | HTML設計書の図表レンダリング |

サブモジュール内の著作権表示とライセンスは、それぞれの`LICENSE`を参照してください。
Kurage Architect本体のコードは、これらのコードを直接importしていません。

