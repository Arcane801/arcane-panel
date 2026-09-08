# 🌆 Arcane Panel

**A security-first VLESS panel with cyberpunk aesthetics.**

> 🔒 **No Backdoors. No Compromise.**

## ✨ Features

- 🛡️ Security-First Design
- ⚡ Lightweight (SQLite, single container)
- 🎨 Cyberpunk UI with neon effects
- 🔌 VLESS + WebSocket/XHTTP + Fragment

## 🚀 Deploy on Railway

1. Fork this repository
2. Go to [railway.app](https://railway.app)
3. **New Project → Deploy from GitHub repo**
4. Add env var: `SECRET_KEY` (generate: `python -c 'import secrets; print(secrets.token_hex(32))'`)
5. Visit `<your-domain>/setup`

## 🔧 Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `SECRET_KEY` | ✅ (prod) | — |
| `DEBUG` | ❌ | `false` |
| `PORT` | ❌ | `8080` |

## 📜 License

MIT
