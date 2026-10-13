# RiskGuard AI frontend container
# Serves the production build behind Nginx.

FROM node:20-slim AS builder
WORKDIR /app/frontend
COPY frontend/ ./
RUN npm install --no-audit --no-fund && npm run build

FROM nginx:1.27-alpine
COPY --from=builder /app/frontend/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 5173
CMD ["nginx", "-g", "daemon off;"]
