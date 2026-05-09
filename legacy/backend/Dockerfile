# Copyright (c) 2026 GDIT. All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
#
# Stage 1 base: node:22-slim (acceptable for dev/S1).
# S2+: switch to registry.access.redhat.com/ubi9/nodejs-22 for FIPS compliance.
# S3+: use UBI9 FIPS-enabled image with --openssl-fips flag (SC-13, F-028).

# ── builder ──────────────────────────────────────────────────────────────────
FROM node:22-slim AS builder
WORKDIR /build

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts

COPY . .
RUN npm run build

# ── runtime ──────────────────────────────────────────────────────────────────
FROM node:22-slim AS runtime

RUN groupadd -r fusion-api && \
    useradd -r -g fusion-api -s /sbin/nologin -d /app fusion-api

WORKDIR /app

COPY --from=builder --chown=fusion-api:fusion-api /build/dist ./dist
COPY --from=builder --chown=fusion-api:fusion-api /build/package.json /build/package-lock.json ./

RUN npm ci --omit=dev --ignore-scripts && \
    npm cache clean --force

USER fusion-api

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "require('http').get('http://localhost:3000/health',r=>process.exit(r.statusCode===200?0:1)).on('error',()=>process.exit(1))"

CMD ["node", "dist/main.js"]
