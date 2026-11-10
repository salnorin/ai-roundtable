# AI Roundtable / دفتر هوش مصنوعی

Local multi-model office and debate app. A **Boss** talks to you in natural language; staff talk to the boss in compact JSON; a **Secretary** writes the work report (گزارش کار). Optional legacy judge/debate mode remains. The office animation is a separate 2D pixel-art page.

Local-only: the server binds to `127.0.0.1` (default port `8765`). API keys live in `.env` (`chmod 600`) and are never shown in the UI.

## Features / ویژگی‌ها

- **Office mode (default):** boss + secretary + employees, compact protocol (`claim`, `target`, `objection`, `evidence`, `confidence`).
- **Chat vs Office:** separate pages/tabs. Chat is conversation with the boss. `/office` is a 2D pixel office where avatars walk; hover a person to see role, current work, fatigue, frustration, usefulness, harm, contribution.
- **Access mode:** *Ask* (default) queues side-effect tools for your approval. *Full autonomy* lets each role run only its own job tools. **Wallet and payments always need your approval and are never executed automatically.**
- **Optimizer scorecard** and **Inspector (بازرس)** recommendations with an Apply button in Admin.
- **Project bar:** start time, elapsed days, progress, ETA (times in Europe/Berlin).
- **Language / زبان / Sprache / Язык:** فارسی, English, Deutsch, Русский.
- **Free and cheap providers** listed in Admin even without a key (`کلید لازمه` + link to the key page). A provider activates when its env var appears in `.env`.

## Setup / راه‌اندازی

```bash
# 1. Clone
git clone https://github.com/salnorin/ai-roundtable.git
cd ai-roundtable

# 2. Keys (never commit .env)
cp .env.example .env
chmod 600 .env
# Fill in the keys you have. Empty value = that provider stays off.

# 3. Optional: copy settings.example.json to settings.json after first run
#    (settings.json is personal and gitignored)

# 4. Start (loopback only)
chmod +x start.sh stop.sh
./start.sh
# opens http://127.0.0.1:8765
```

Requires Python 3 (stdlib only). No pip packages.

Stop with `./stop.sh`.

## Free / cheap API key pages

These signup/key URLs are listed in Admin. This app does **not** sign up for you.

| Provider | Tier | Key page |
|---|---|---|
| Google Gemini | free | https://aistudio.google.com/apikey |
| Groq | free | https://console.groq.com/keys |
| OpenRouter | free | https://openrouter.ai/keys |
| Hugging Face Router | free | https://huggingface.co/settings/tokens |
| Cerebras | free | https://cloud.cerebras.ai/platform/api-keys |
| Cloudflare Workers AI | free | https://dash.cloudflare.com/profile/api-tokens |
| GitHub Models | free | https://docs.github.com/en/github-models |
| Kimi (Moonshot) | freemium | https://platform.kimi.ai/console/api-keys |
| Mistral | freemium | https://console.mistral.ai/api-keys |
| NVIDIA NIM | freemium | https://build.nvidia.com/settings/api-keys |
| Qwen DashScope (intl) | freemium | https://modelstudio.console.alibabacloud.com/ap-southeast-1/settings/api-key |
| GLM (Z.ai) | freemium | https://z.ai/manage-apikey/apikey/list |
| GLM (Zhipu) | freemium | https://open.bigmodel.cn/usercenter/proj-mgmt/apikeys |
| Cohere | freemium | https://dashboard.cohere.com/api-keys |
| SambaNova | freemium | https://cloud.sambanova.ai |
| SiliconFlow | freemium | https://cloud.siliconflow.com/account/ak |
| Together AI | cheap | https://api.together.ai/settings/api-keys |
| Fireworks | cheap | https://fireworks.ai/api-keys |
| Novita | cheap | https://novita.ai/settings/key |
| DeepSeek | cheap | https://platform.deepseek.com/api_keys |
| xAI Grok | cheap | https://console.x.ai |
| Chutes | cheap | https://chutes.ai/app/settings/api-keys |
| DeepInfra | cheap | https://deepinfra.com/dash/api_keys |
| Hyperbolic | cheap | https://app.hyperbolic.ai/settings/api-keys |
| Nebius | cheap | https://tokenfactory.nebius.com/settings |

Cloudflare also needs `CLOUDFLARE_ACCOUNT_ID` in `.env`.

## License

MIT © 2026 salnorin
