# 部署文档 · 智能排料 Copilot(容器化)

云服务器一键容器部署手册。已在腾讯云 Ubuntu 服务器(`/opt` 多项目共存)验证通过。

> 一句话:`git clone` 到 `/opt/PEBS_Nesting_AI` → 配 `.env` → `./deploy.sh` → 放行端口。

---

## 0. 前提

- 服务器已装 **Docker + Docker Compose v2**:
  ```bash
  docker --version && docker compose version
  # 没装就:curl -fsSL https://get.docker.com | sh
  ```
- 有 `/opt` 写权限(或用 `sudo`)。本服务器约定各项目放在 `/opt/<项目名>`。
- 准备一个**未被占用的对外端口**(本项目默认前端 `8080`)。

---

## 1. 选端口(避免与现有项目冲突)

```bash
# 看 Docker 已占的主机端口
docker ps --format 'table {{.Names}}\t{{.Ports}}'
# 看全主机监听端口
sudo ss -tlnp | grep LISTEN
# 确认目标端口是否空闲(无输出=空闲)
sudo ss -tlnp | grep ':8080'
```

本服务器现状(参考):`3100` = amoeba-copilot,`8787` = pebs-aps-ai,`8080` 空闲可用。

---

## 2. 拉代码到独立目录

```bash
sudo mkdir -p /opt/PEBS_Nesting_AI
sudo chown "$USER":"$USER" /opt/PEBS_Nesting_AI
git clone https://github.com/cms7058/PEBS_Nesting_AI.git /opt/PEBS_Nesting_AI
cd /opt/PEBS_Nesting_AI
```

---

## 3. 配置 `.env`(可选)

`deploy.sh` 首次会自动从 `.env.docker.example` 生成 `.env`。需要时编辑:

```bash
cp .env.docker.example .env   # deploy.sh 已自动做,手动改时用
vi .env
```

| 变量 | 说明 |
|---|---|
| `FRONTEND_PORT` | 前端对外端口,默认 `8080`,改成空闲端口 |
| `ANTHROPIC_API_KEY` 等 | LLM key,**可留空**,启动后在前端「⚙ 模型配置」页填,持久化到数据卷 |
| `NEST_TIME_SEC` | 排料求解时限(秒),默认 20 |
| `AMIBA_ENDPOINT` / `AMIBA_TOKEN` | 阿米巴上报,留空=独立模式(休眠) |

---

## 4. 一键部署

```bash
./deploy.sh                       # 拉最新代码 + 校验端口 + 构建 + 启动 + 打印访问地址
FRONTEND_PORT=18080 ./deploy.sh   # 临时换端口
./deploy.sh --no-pull             # 不 git pull,仅用当前代码重建
```

`deploy.sh` 会依次:检查 Docker → `git pull` → 准备 `.env` → 校验端口空闲 → `docker compose up -d --build` → 打印 `http://<IP>:<端口>`。

首次构建约 3~5 分钟(编译 Rust 求解器 `bin_nester` + 装 Python 依赖 + 构建前端)。

---

## 5. 放行端口 + 访问

```bash
# 本机防火墙(用 ufw 时)
sudo ufw allow 8080/tcp
```
- **云厂商「安全组」**也必须放行该端口(腾讯云/阿里云/AWS 控制台操作)。
- 浏览器打开 `http://<服务器公网IP>:8080`。

---

## 6. 日常运维

```bash
cd /opt/PEBS_Nesting_AI

./deploy.sh                # 更新:拉代码 + 重建(最常用)
docker compose ps          # 查看状态
docker compose logs -f     # 看日志(Ctrl+C 退出)
docker compose logs -f backend
docker compose restart     # 重启
docker compose down        # 停止(保留数据卷)
docker compose down -v     # 停止并删数据(慎用!会清空余料库/配置)
```

数据(`llm_config.json` / `remnants.json` / `amiba_projects.json`)存于命名卷
`pebs-nesting_nesting-data`,容器重建不丢。

---

## 7. 架构与隔离

| 维度 | 说明 |
|---|---|
| Compose 工程名 | `name: pebs-nesting`,容器为 `pebs-nesting-frontend-1` / `pebs-nesting-backend-1`,与其他项目隔离 |
| 对外端口 | 仅前端发布 `FRONTEND_PORT` 一个;**后端不暴露公网**,前端 nginx 内部反代 `/api`、`/amiba` |
| 网络 | Compose 自建独立 bridge 网络 |
| 数据 | 命名卷 `pebs-nesting_nesting-data` |
| 镜像 | `backend` 多阶段:Rust 编译 `bin_nester` → Python/FastAPI;`frontend`:Vite 构建 → nginx |

---

## 8. 排错记录(已踩过的坑)

| 现象 | 原因 | 解决 |
|---|---|---|
| `feature 'edition2024' is required` | Rust 基础镜像过旧(1.83) | 升到 `rust:1.85+`(已修) |
| `let` expressions ... unstable(jagua-rs) | let-chains 需 Rust ≥ 1.88 | 升到 `rust:1.90-slim`(已修) |
| 拉镜像 `500 Internal Server Error`(`mirror.ccs.tencentyun.com`) | 腾讯云镜像源临时故障/无缓存 | 重试;或直连拉取后再部署:`docker pull docker.io/library/rust:1.90-slim`,再 `./deploy.sh` |
| 端口被占,`deploy.sh` 报错 | 目标端口已被其他进程占用 | 改 `.env` 的 `FRONTEND_PORT` 或 `FRONTEND_PORT=18080 ./deploy.sh` |
| 页面打不开,但容器 Up | 云安全组未放行端口 | 安全组 + `ufw` 放行该端口 |

### 镜像源 500 的彻底绕过
若反复命中镜像源故障,可先直连 Docker Hub 把基础镜像拉到本地,`compose` 会复用缓存:
```bash
docker pull docker.io/library/rust:1.90-slim
docker pull docker.io/library/python:3.11-slim
docker pull docker.io/library/node:20-slim
docker pull docker.io/library/nginx:1.27-alpine
./deploy.sh
```

---

## 9. 查询某个已部署项目的目录(运维备忘)

```bash
docker inspect <容器名> --format '{{ index .Config.Labels "com.docker.compose.project.working_dir"}}'
```
例:`docker inspect pebs-aps-ai --format '...'` → `/opt/PEBS_APS_AI`。
