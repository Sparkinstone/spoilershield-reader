# SpoilerShield 使用说明（中文）

## 启动（Windows 一键）

双击 `启动应用.bat`。

它由 `scripts/launch.py` 负责：先启动 uvicorn，轮询 `/ping` 直到服务真正就绪，**之后**才打开浏览器；不会再出现“先弹网页、然后无法连接”的竞态。关闭窗口或按 Ctrl+C 即停止服务。

可选参数：

```bat
启动应用.bat --port 8080        :: 换端口
启动应用.bat --reload           :: 开发时自动重载
启动应用.bat --no-browser       :: 只启动服务
启动应用.bat --host 0.0.0.0     :: 允许局域网访问（默认仅本机）
```

手动启动：

```bat
python scripts/launch.py
:: 或
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## 使用流程

1. **上传书籍**：首页选择 `.txt` / `.pdf` / `.epub`，标题可留空（默认用文件名）。
   上传后系统解析段落并生成向量（首次会加载本地 embedding 模型，较慢）。
2. **阅读**：点击书名进入阅读器，左侧正文、右侧评论弹窗，EPUB 有目录和底部进度条。
3. **发表评论**：AI 自动判断是否剧透，结果三态：
   - 🟢 `PUBLIC`：正常显示
   - 🔴 `HIDDEN`：模糊遮罩，点击展开
   - 🟡 `PENDING_REVIEW`：正文不展示，只提示“AI 审核中”
4. **管理后台**：http://localhost:8000/admin
   - 待审评论可「批准 / 标记剧透 / 删除」
   - 书籍管理（删除会同时清理数据库记录和上传文件）

## 配置（.env）

模型默认接 **DeepSeek Flash**（OpenAI 兼容接口）：

```ini
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-flash
```

也兼容旧的 `OPENAI_API_KEY` / `OPENAI_API_BASE`。其他可调项：
`LLM_TIMEOUT`、`LLM_MAX_RETRIES`、`SPOILER_CONFIDENCE_THRESHOLD`（默认 0.7）、
`MAX_UPLOAD_MB`（20）、`MAX_COMMENT_CHARS`（500）、`ADMIN_PASSWORD`。

> 改了模型配置后，先跑 `python scripts/check_llm.py` 确认端点、模型名和 Key 都可用。

## 管理后台鉴权

- 设置了 `ADMIN_PASSWORD`：`/admin` 需要 HTTP Basic 登录（用户名 `ADMIN_USER`，默认 `admin`）。
- 没设置：只允许本机（127.0.0.1）访问，远程访问返回 403。

## 测试

```bash
python -m pytest
```

131 个测试，全程离线：embedding 和 LLM 都用 fake 注入，不下载模型、不调 API。
覆盖上传安全（路径穿越 / 大小 / 类型）、三种解析器、检索流水线、重试与错误分类、
评论三态、后台鉴权。

## 离线使用

- 页面完全自包含：CSS、JS、图标、字体都在 `app/static/` 本地，不再依赖 Tailwind CDN 或 htmx。
- Web 进程本身不依赖网络，断网也能启动。
- embedding 模型改为**缓存优先**加载：模型已缓存时，断网下首次上传/评论约 0.1 秒完成；
  没有缓存时会在 2 秒内快速失败并返回 503，明确提示缺哪个模型，不再卡住几分钟。
  `EMBEDDING_ALLOW_DOWNLOAD=false` 可用于完全隔离的内网部署。
- 用无头 Chrome 实测：零外部资源请求、390px 宽无横向溢出、评论弹窗 / 剧透展开 / 目录抽屉
  均可用。
- 断网时评论不会丢：LLM 调用失败会转为 `PENDING_REVIEW` 并提示“AI 审核暂不可用”。

## 部署

单机应用：1 个 uvicorn worker、SQLite、embedding 模型常驻约 1 GB 内存，建议 2C4G 起步。

- `Dockerfile` + `docker-compose.yml` + `deploy/Caddyfile`：Caddy 自动 HTTPS，数据放命名卷；
- `deploy/nginx.conf` + `deploy/spoilershield.service`：不用 Docker 的 systemd + Nginx 方式；
- 公网部署必须设置 `ADMIN_PASSWORD`（代理后本机白名单会被拒绝），只放行 22/80/443，
  演示环境上传样书后设 `ALLOW_UPLOADS=false`。

完整步骤、备份命令和安全清单见 [deploy/README.md](deploy/README.md)。
宝塔面板 / OpenCloudOS 9（Nginx 已占用 80/443）请看 [deploy/BAOTA.md](deploy/BAOTA.md)。

## 已知限制

- `spoiler_detection_report/` 里 98.8% 的准确率来自 LLM 生成的评论，属于乐观上限，
  真实用户评论需要重新标注评估。
- 默认 embedding 是英文模型 `all-MiniLM-L6-v2`，中文语义召回偏弱，实际靠字频召回兜底；
  可通过 `EMBEDDING_MODEL` 换成中文模型（新旧向量维度不一致时会自动重算）。
- 单机 SQLite + 本地上传目录，没有队列、限流、CSRF，适合演示，不适合直接公开多用户部署。
