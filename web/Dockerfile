# --- Builder ---------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Deps primero: capa cacheable mientras no cambie el lock.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Las variables NEXT_PUBLIC_* se incrustan al compilar, no al arrancar: si no
# llegan acá, el bundle sale sin ellas y el login no encuentra su credencial.
# En Coolify hay que marcarlas como variables de build.
ARG NEXT_PUBLIC_GOOGLE_CLIENT_ID
ARG NEXT_PUBLIC_SITE_URL
ARG NEXT_PUBLIC_POSTHOG_KEY
ARG NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION
# Vacío = producción: ver `web/lib/telemetry/index.ts`.
ARG NEXT_PUBLIC_ENTORNO
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL \
    NEXT_PUBLIC_POSTHOG_KEY=$NEXT_PUBLIC_POSTHOG_KEY \
    NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION=$NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION \
    NEXT_PUBLIC_ENTORNO=$NEXT_PUBLIC_ENTORNO

RUN npm run build

# --- Runtime ---------------------------------------------------------------
# `output: "standalone"` (next.config.ts) deja en .next/standalone un server.js
# con sólo las dependencias que realmente usa: no hace falta node_modules entero.
FROM node:22-alpine AS runtime

WORKDIR /app
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

# Sin esto el proceso corre como root dentro del contenedor.
RUN addgroup -S nodejs && adduser -S nextjs -G nodejs

# `curl` es para el healthcheck y nada más. Coolify no chequea la aplicación
# desde afuera: ejecuta `curl` DENTRO del contenedor, y si no lo encuentra da el
# contenedor por enfermo y revierte el deploy. Alpine trae `wget` en busybox,
# pero no alcanza: el 13-08-2026 el deploy de la web falló igual con "New
# container is not healthy" teniendo wget disponible.
RUN apk add --no-cache curl

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
