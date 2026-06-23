# syntax=docker/dockerfile:1
# 前端镜像：Vite 构建静态资源,nginx 托管并反代 /api、/amiba 到后端
#   构建上下文 = frontend/
#   docker build -t pebs-nesting-frontend ./frontend

# ---------- Stage 1: 构建 ----------
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------- Stage 2: 托管 ----------
FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
