# vvwbot-site

`vvwbot.com` 的本地源码与构建项目。开始开发前必须阅读 `CLAUDE.md`；构建使用项目 `venv/bin/python`，发布使用 Wrangler，并且任何公网部署都需要明确授权。

## Automation relationship

- 真实路径：`/Users/vvw/Automation/vvwbot-site`；Desktop 路径是便利软链接。
- 本项目没有独立 LaunchAgent 或 watchdog。
- `tradingroom-digest` 成功生成内容后会调用本项目构建并部署；该上游任务由 `/Users/vvw/Automation/manager/supervisor.py` 监控。
- 构建产物：`dist/`；`build.py` 会重建该目录。

## Credentials

Cloudflare/Wrangler 身份由现有 Wrangler 配置和登录状态管理。README、代码、日志和 Git 中不得保存或复制 token。账号、访问控制和验证规则见 `CLAUDE.md`。

