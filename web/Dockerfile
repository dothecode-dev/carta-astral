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
ENV NEXT_PUBLIC_GOOGLE_CLIENT_ID=$NEXT_PUBLIC_GOOGLE_CLIENT_ID \
    NEXT_PUBLIC_SITE_URL=$NEXT_PUBLIC_SITE_URL

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

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
