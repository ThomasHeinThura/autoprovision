# ---- build the React SPA ----
FROM node:22-alpine AS build
WORKDIR /app
COPY package*.json ./
# Retry on transient registry drops (ECONNRESET) and reuse a cache mount across builds.
RUN npm config set fetch-retries 5 \
 && npm config set fetch-retry-mintimeout 20000 \
 && npm config set fetch-retry-maxtimeout 120000
RUN --mount=type=cache,target=/root/.npm npm ci
COPY . .
RUN npm run build

# ---- serve via nginx (proxies /bff + /realtime to app3) ----
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
# keep the static prototype available at /ui
COPY ui/ /usr/share/nginx/html/ui/
EXPOSE 80
