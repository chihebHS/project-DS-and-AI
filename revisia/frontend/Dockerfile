# Frontend RevisIA : build Vite puis service statique + reverse proxy /api avec Nginx (non root, port 8080).
# Build (depuis le dossier revisia/) : docker build -f frontend/Dockerfile -t revisia-frontend .

FROM node:20-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
LABEL org.opencontainers.image.title="revisia-frontend"
# Adresse du backend, injectée dans la conf Nginx au démarrage (envsubst des templates)
ENV BACKEND_URL=http://backend:8000
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://127.0.0.1:8080/healthz || exit 1
