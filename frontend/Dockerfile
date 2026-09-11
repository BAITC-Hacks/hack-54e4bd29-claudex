# MedSignal frontend.

# --- Базовый слой -----------------------------------------------------------
FROM node:22-alpine AS base
WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# --- Зависимости ------------------------------------------------------------
FROM base AS deps
COPY package.json package-lock.json* ./
# npm ci требует package-lock.json; при его отсутствии используется install.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# --- Окружение разработки ---------------------------------------------------
FROM base AS development
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Непривилегированный пользователь и в разработке: контейнер, работающий
# от root, отличается от эксплуатационного по поведению с правами
# на файлы и маскирует ошибки, которые проявятся позже.
RUN mkdir -p /app/.next && chown -R node:node /app
USER node
ENV NODE_ENV=development
EXPOSE 3000
CMD ["npm", "run", "dev"]

# --- Сборка -----------------------------------------------------------------
FROM base AS builder
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Публичные переменные встраиваются в клиентский код на этапе сборки.
ARG NEXT_PUBLIC_API_BASE_URL=/api/v1
ARG NEXT_PUBLIC_APP_ENV=production
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL} \
    NEXT_PUBLIC_APP_ENV=${NEXT_PUBLIC_APP_ENV} \
    NODE_ENV=production
RUN npm run build

# --- Окружение эксплуатации -------------------------------------------------
FROM base AS production
ENV NODE_ENV=production

# Непривилегированный пользователь. Контейнер не работает от root.
RUN addgroup --system --gid 1001 medsignal \
    && adduser --system --uid 1001 --ingroup medsignal medsignal

COPY --from=builder --chown=medsignal:medsignal /app/public ./public
COPY --from=builder --chown=medsignal:medsignal /app/.next/standalone ./
COPY --from=builder --chown=medsignal:medsignal /app/.next/static ./.next/static

USER medsignal
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
