# syntax=docker/dockerfile:1
# 后端镜像：多阶段构建
#   1) rust-builder —— 编译自研 Rust 求解器 bin_nester(固定板装箱,必需)
#   2) runtime      —— Python/FastAPI 运行时,内置已编译二进制
# 构建上下文 = 仓库根目录(需同时访问 backend/ 与 phase0/engines/bin_nester/)
#   docker build -f backend/Dockerfile -t pebs-nesting-backend .

# ---------- Stage 1: 编译 Rust 求解器 ----------
# 注:jagua-rs 0.7.2 用到 let-chains(Rust 1.88 稳定)、依赖含 edition2024 crate;需 Rust >= 1.88
FROM rust:1.90-slim AS rust-builder
WORKDIR /build
COPY phase0/engines/bin_nester/ ./bin_nester/
RUN cd bin_nester && cargo build --release

# ---------- Stage 2: Python 运行时 ----------
FROM python:3.11-slim AS runtime
WORKDIR /app

# 依赖(shapely/ezdxf/openpyxl 均为纯 Python 或自带 GEOS wheel,无需系统库)
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码
COPY backend/app ./app

# 已编译的 Rust 求解器 + 指向它的环境变量
COPY --from=rust-builder /build/bin_nester/target/release/bin_nester /usr/local/bin/bin_nester
ENV BIN_NESTER_BIN=/usr/local/bin/bin_nester

# 运行时数据(llm_config.json / remnants.json / amiba_projects.json)落到挂载卷
ENV NESTING_DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 9100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9100"]
