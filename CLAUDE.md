# vvwbot-site

个人研究站 vvwbot.com 的源码。这份文件是给任何在这个仓库里工作的 agent（不限于某个具体任务）看的项目规约——
"怎么发布"的工作流写在 skill `vvwbot-publish` 里，不重复。

## 运行环境

- **永远用 `venv/bin/python`，不要用系统 `/usr/bin/python3`**——系统 python 没装 `markdown` 库，版本也老。
  venv 已经建好并提交在这个目录里；如果丢失，重建：`python3 -m venv venv && venv/bin/pip install markdown`
- 部署工具是 `wrangler`（全局装的，不在这个仓库里）。用 `wrangler deploy`，**不要用 `wrangler pages deploy`**
  ——旧命令，Cloudflare Pages 已并入 Workers，且曾被 Claude Code 的自动模式分类器当"公网发布"拦截过。

## 账号与域名

- 域名 `vvwbot.com` 绑定的 Cloudflare 账号是 `51bf08a0d84d3ca830e91606916885aa`（`wrangler.jsonc` 里
  `account_id`/`routes[].zone_name` 写死的那个）。`ljh69993@gmail.com` 和 `ljianhui90@gmail.com`
  两个邮箱登录后都能部署到这个账号（2026-09-12 用 `ljianhui90@gmail.com` 实测 `wrangler deploy`
  成功，且 `/research/*` 的 Access 保护部署后仍正常返回 302）——早先"跨账号会报错"的说法不准确，
  已删除，别再当真。
- `wrangler whoami` 显示的邮箱只要能连到上面这个 account_id 就行；如果换了个完全没关联过的新账号，
  可能需要用户自己 `wrangler login` 重新登录（弹浏览器走 OAuth，不能代跑）——但这只在真的报错时才需要，
  不要预先假设当前登录账号不对。

## 目录结构

| 路径 | 用途 |
|---|---|
| `build.py` | 唯一的构建脚本，读各处 markdown/wiki 源 → 渲染 → 输出到 `dist/` |
| `assets/site.css` | 全站唯一样式表：深空/黑洞主题，暗色调。**新增内容复用现有组件，不要另起风格** |
| `public/index.html`、`public/privacy.html` | 手写的公开页，不走 `build.py` 模板 |
| `content/*.md` | 独立撰写的长文（如 Frank 审计报告） |
| `dist/` | 构建产物，会被 `build.py` 整个删掉重建，不要手动改这里的文件 |
| `wrangler.jsonc` | 部署配置 |

## 访问控制（发布前必须确认）

- `/` 和 `/privacy` **必须公开**——Google OAuth 同意屏幕的验证依赖它们能被匿名访问
- `/research/*` 挂了 Cloudflare Access（白名单五个邮箱），且全部带 `noindex`——里面有对具名从业者的
  批判性审计和私密 Discord 群聊记录，公开发布有名誉权/隐私风险
- 验证方式：`curl -sS -o /dev/null -w "%{http_code}\n" <url>`——`/research/*` 应该拿到 302
  （Access 登录跳转，正常），`/`、`/privacy` 应该拿到 200

## 内容渲染约定

- Obsidian 双向链接 `[[path|标签]]` 会被自动转成 `` `标签` `` 内联代码样式（不是超链接，目标页大多不在
  站点上，做超链接会变成死链）
- YAML frontmatter 自动去掉，不会出现在页面上
- 表格自动包一层横向滚动容器
- 公司研究页顶部"wiki 最后更新 <日期>"取的是源文件真实 mtime，不是手写的
