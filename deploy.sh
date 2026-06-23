#!/usr/bin/env bash
# 智能排料 Copilot · 一键部署脚本(容器化)
#   用法:  ./deploy.sh           拉取最新代码并部署/更新
#           ./deploy.sh --no-pull 跳过 git pull,仅用当前代码重建
#           FRONTEND_PORT=18080 ./deploy.sh   临时指定前端端口
#
# 行为:检查 Docker → 准备 .env → 校验端口空闲 → 构建并启动 → 打印访问地址
set -euo pipefail

cd "$(dirname "$0")"   # 切到脚本(= 项目根)所在目录

# ---- 小工具:带颜色的提示 ----
c_ok()   { printf '\033[32m✓ %s\033[0m\n' "$*"; }
c_info() { printf '\033[36m• %s\033[0m\n' "$*"; }
c_warn() { printf '\033[33m! %s\033[0m\n' "$*"; }
c_err()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; }

PULL=1
[ "${1:-}" = "--no-pull" ] && PULL=0

# ---- 1. 检查 Docker / Compose ----
if ! command -v docker >/dev/null 2>&1; then
  c_err "未找到 docker。请先安装:curl -fsSL https://get.docker.com | sh"
  exit 1
fi
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  c_err "未找到 docker compose 插件。请安装 Docker Compose v2。"
  exit 1
fi
c_ok "Docker 就绪($DC)"

# ---- 2. 拉取最新代码(在 git 仓库内且未禁用时)----
if [ "$PULL" = 1 ] && [ -d .git ]; then
  c_info "拉取最新代码 (git pull)…"
  git pull --ff-only || c_warn "git pull 未成功(本地可能有改动),继续用当前代码。"
fi

# ---- 3. 准备 .env ----
if [ ! -f .env ]; then
  cp .env.docker.example .env
  c_warn ".env 不存在,已从 .env.docker.example 生成。"
  c_warn "如需配置 LLM key 或修改端口,编辑 .env 后重跑(也可启动后在前端「⚙ 模型配置」页填 key)。"
fi

# 读取 .env 里的 FRONTEND_PORT(命令行环境变量优先)
ENV_PORT="$(grep -E '^[[:space:]]*FRONTEND_PORT=' .env 2>/dev/null | tail -1 | cut -d= -f2 | tr -d '[:space:]' || true)"
PORT="${FRONTEND_PORT:-${ENV_PORT:-8080}}"

# ---- 4. 校验端口是否被别的进程占用 ----
port_in_use() {
  if command -v ss >/dev/null 2>&1; then
    ss -tlnH "( sport = :$1 )" 2>/dev/null | grep -q .
  elif command -v netstat >/dev/null 2>&1; then
    netstat -tln 2>/dev/null | grep -qE "[:.]$1[[:space:]]"
  else
    return 1   # 无法检测,放行
  fi
}

# 排除「本项目自己已经占用该端口」的情况(更新部署时端口当然在用)
SELF_USING=0
docker ps --filter "name=pebs-nesting-frontend" --format '{{.Ports}}' 2>/dev/null | grep -q ":$PORT->" && SELF_USING=1

if [ "$SELF_USING" = 0 ] && port_in_use "$PORT"; then
  c_err "端口 $PORT 已被其他进程占用。"
  c_warn "改用空闲端口:在 .env 设置 FRONTEND_PORT=<空闲端口> 后重跑,"
  c_warn "或临时执行:  FRONTEND_PORT=18080 ./deploy.sh"
  echo
  c_info "当前主机监听端口:"
  (command -v ss >/dev/null 2>&1 && ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | grep LISTEN || true
  exit 1
fi
c_ok "前端端口 $PORT 可用"

# ---- 5. 构建并启动 ----
c_info "构建并启动容器(首次会编译 Rust 求解器,请稍候)…"
FRONTEND_PORT="$PORT" $DC up -d --build

echo
$DC ps
echo

# ---- 6. 打印访问地址 ----
IP="$(curl -fsS --max-time 3 ifconfig.me 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo '<服务器IP>')"
c_ok "部署完成!"
echo "  访问地址:  http://${IP}:${PORT}"
echo "  本机访问:  http://localhost:${PORT}"
echo
c_info "查看日志:  $DC logs -f"
c_info "停止服务:  $DC down"
c_warn "别忘了在云厂商「安全组」/ 本机防火墙放行 ${PORT}/tcp"
