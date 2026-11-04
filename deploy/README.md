# 部署到云服务器

> 使用**宝塔面板 + OpenCloudOS 9 + textadventure.top**？直接看
> [BAOTA.md](BAOTA.md)：宝塔 Nginx 已占用 80/443，不要启用本文的 Caddy。

这份文档面向一台 Linux 云服务器（Ubuntu 22.04/24.04）。应用本身是单进程
FastAPI + SQLite + 本地 embedding 模型，**不是**多租户高并发服务；按下面的方式部署，
适合作品集演示、小范围使用。

## 0. 先知道的几件事

| 事实 | 影响 |
| --- | --- |
| embedding 模型（torch）常驻约 1 GB RSS | 最低 2 GB 内存，推荐 2C4G；1 GB 机器会 OOM |
| 单 worker 是刻意设计 | 多 worker 会各自加载一份模型，并让 SQLite 写锁更糟 |
| 上传一本书 = 解析 + 对全部段落做 embedding | 2000 段的书上传统计几十秒到几分钟，请求会一直挂着 |
| 每条评论调用一次 LLM | 有 API 成本，也依赖服务器能访问模型网关 |
| 没有用户体系 | 任何访客都能评论；上传是否开放由 `ALLOW_UPLOADS` 控制 |

**公开作品集建议：预置一本样书，设置 `ALLOW_UPLOADS=false`，只开放阅读和评论。**

## 1. 推荐拓扑

```
Internet ──443──> Caddy（自动 HTTPS）──> app:8000（uvicorn，1 worker）
                                              │
                                              └── /data
                                                  ├── spoiler_shield.db
                                                  └── uploads/
```

Caddy 负责证书和反代；app 不直接暴露端口。

## 2. 服务器准备

- 2 vCPU / 4 GB RAM / 40 GB 磁盘，Ubuntu 24.04；
- 安全组/防火墙只放行 `22`、`80`、`443`；
- 域名 A 记录指向服务器公网 IP（Caddy 申请证书需要）；
- 安装 Docker Engine + Compose 插件（官方脚本或发行版包）；
- 国内服务器访问 Docker Hub / PyPI / HuggingFace 可能受限，构建前先确认网络，
  必要时配置镜像源。

## 3. Docker Compose 部署（推荐）

```bash
git clone <your-repo> /opt/spoilershield
cd /opt/spoilershield
cp .env.example .env
chmod 600 .env
```

编辑 `.env`，至少设置：

```ini
DOMAIN=books.example.com
ADMIN_USER=admin
ADMIN_PASSWORD=<openssl rand -base64 24 生成>
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-flash
ALLOW_UPLOADS=true        # 首次先开着，上传样书后再改 false
```

不要在这里设置 `DATABASE_URL` / `UPLOAD_DIR`，`docker-compose.yml` 会固定到
容器内的 `/data` 持久卷。

启动：

```bash
docker compose up -d --build
docker compose logs -f app
```

首次构建会下载 CPU 版 torch（约 200 MB）、依赖和 embedding 模型（约 90 MB），
通常 5–15 分钟。构建完成后：

```bash
curl -fsS https://books.example.com/healthz
docker compose ps
```

### 写入样书并关闭上传

1. 浏览器打开 `https://books.example.com`，上传一本用于演示的书；
2. 等上传完成、页面进入阅读器；
3. 把 `.env` 里的 `ALLOW_UPLOADS` 改成 `false`；
4. 让容器重新读取环境变量：

```bash
docker compose up -d
```

之后 `/upload` 会返回 403，但已有书籍仍可阅读、评论。

### 管理后台

访问 `https://books.example.com/admin`，用 `ADMIN_USER` / `ADMIN_PASSWORD` 登录。
**反向代理后面必须设置 `ADMIN_PASSWORD`**：没有密码时后台只允许“直连本机”的请求，
检测到 `X-Forwarded-For` 等代理头会直接 403。

## 4. 生产环境变量

| 变量 | 建议值 | 说明 |
| --- | --- | --- |
| `ADMIN_PASSWORD` | 随机 24 字节 | 必填；否则后台在代理后不可用 |
| `ALLOW_UPLOADS` | `false`（公开演示） | 关闭上传，避免 CPU/磁盘被滥用 |
| `MAX_UPLOAD_MB` | `20` | 上传上限；反代也要 ≥ 这个值 |
| `MAX_PARAGRAPHS` | `5000` | 单书段落上限 |
| `SPOILER_CONFIDENCE_THRESHOLD` | `0.7` | 低于阈值转人工审核 |
| `LLM_TIMEOUT` | `30` | 评论接口的最长等待时间，反代超时要更大 |
| `EMBEDDING_ALLOW_DOWNLOAD` | `true` | 镜像已内置模型；断网机器可设 `false` |

## 5. 数据与备份

所有状态都在 `app-data` 卷的 `/data` 下：`spoiler_shield.db` 和 `uploads/`。

SQLite 在线备份（不要在运行中直接 `cp` 数据库文件）：

```bash
docker compose exec app python -c "
import sqlite3
src = sqlite3.connect('/data/spoiler_shield.db')
dst = sqlite3.connect('/data/backup.db')
src.backup(dst)
dst.close(); src.close()
"
docker compose cp app:/data/backup.db "./backup-$(date +%F).db"
```

上传文件打包：

```bash
docker run --rm \
  -v spoilershield_app-data:/data \
  -v "$PWD":/backup \
  alpine tar czf "/backup/uploads-$(date +%F).tar.gz" -C /data uploads
```

恢复：停服务 → 把 `.db` 和 `uploads/` 放回卷 → 启服务。建议每天 cron 备份一次，
并把备份同步到对象存储。

## 6. 安全清单

- [x] 只暴露 80/443，app 通过 `expose` 或 `127.0.0.1:8000` 访问；
- [x] Caddy 自动 HTTPS；Nginx 用 certbot；
- [x] 设置强随机 `ADMIN_PASSWORD`；
- [x] 公开演示关闭上传（`ALLOW_UPLOADS=false`）；
- [x] `.env` 权限 600，不提交 git；
- [x] 应用已内置跨站写请求拦截（Origin 校验）；
- [x] Nginx 示例含评论/上传限流和安全响应头；
- [ ] 应用没有登录体系：评论/阅读是公开的，删除书籍/审核在 Basic Auth 后；
- [ ] 没有 CSRF token，只靠 Origin 校验 + Basic Auth（对演示够用，正式多用户需补）；
- [ ] 给 LLM key 设置额度/预算告警，避免被刷。

## 7. 不用 Docker：systemd + Nginx

```bash
sudo apt update
sudo apt install -y python3.12-venv git nginx certbot python3-certbot-nginx
sudo useradd --system --home-dir /opt/spoilershield --shell /usr/sbin/nologin spoilershield
sudo git clone <your-repo> /opt/spoilershield
sudo chown -R spoilershield:spoilershield /opt/spoilershield
cd /opt/spoilershield
sudo -u spoilershield python3 -m venv .venv
sudo -u spoilershield .venv/bin/pip install \
  torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu
sudo -u spoilershield .venv/bin/pip install -r requirements.txt
sudo -u spoilershield .venv/bin/python -c \
  "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
sudo -u spoilershield cp .env.example .env
sudo chown spoilershield:spoilershield .env
sudo chmod 600 .env
```

`.env` 里额外设置：

```ini
DATABASE_URL=sqlite:////var/lib/spoilershield/spoiler_shield.db
UPLOAD_DIR=/var/lib/spoilershield/uploads
ADMIN_PASSWORD=<随机密码>
```

安装 [spoilershield.service](spoilershield.service) 与 [nginx.conf](nginx.conf)：

```bash
sudo cp deploy/spoilershield.service /etc/systemd/system/
sudo cp deploy/nginx.conf /etc/nginx/sites-available/spoilershield
sudo ln -s /etc/nginx/sites-available/spoilershield /etc/nginx/sites-enabled/
sudo sed -i 's/books.example.com/你的域名/' /etc/nginx/sites-available/spoilershield
sudo systemctl daemon-reload && sudo systemctl enable --now spoilershield
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d 你的域名
```

## 8. 资源与成本

- 镜像约 1.2–1.8 GB（CPU torch + 模型）；
- 运行时 RSS 约 0.8–1.2 GB，2C4G 足够；
- 首次评论/上传有模型预热与 CPU 推理延迟；
- 每条评论一次 LLM 请求，按你的模型单价估算；
- 单机 SQLite 的写并发很低，不适合几十人同时评论；要扩就换 Postgres +
  把 embedding 放进任务队列，而不是加 uvicorn worker。

## 9. 更新与回滚

```bash
docker compose exec app python -c "import sqlite3; ..."  # 先备份，见上
git pull
docker compose up -d --build
docker compose logs -f app
```

没有 Alembic：如果表结构改了，需要手工迁移或从备份恢复。生产升级前务必备份。

## 10. 排错

| 现象 | 检查 |
| --- | --- |
| 502 Bad Gateway | `docker compose ps`，`logs app`，容器是否 healthy |
| 413 Request Entity Too Large | Nginx `client_max_body_size` / 应用 `MAX_UPLOAD_MB` |
| 评论转圈很久后失败 | 反代 `proxy_read_timeout`、`LLM_TIMEOUT`、LLM 网关连通性 |
| `/admin` 403 或 401 | 代理后必须设 `ADMIN_PASSWORD`；Basic Auth 用户名密码 |
| 首次上传卡住几分钟 | 正常：整本书逐段 embedding；看 CPU |
| 模型加载失败 | 构建时预下载失败；`docker compose build --no-cache` 重试或挂载本地模型 |
| 证书申请失败 | 域名是否解析到本机、80/443 是否放行、Caddy 日志 |

## 11. 已知限制（按重要性）

1. 上传是同步的：一本大书会占住唯一的 worker，期间其他请求变慢；
2. 没有任务队列，失败的上传需要重试；
3. 单机 SQLite，不支持多副本；
4. 没有用户系统，评论不可归属，也无法按用户限流（只能在反代按 IP）；
5. 默认 embedding 是英文模型，中文召回偏弱；
6. 98.8% 的评测来自合成评论，别当线上指标写进 PPT。

这些都可以作为下一阶段迭代点；部署本身不需要先解决它们。
