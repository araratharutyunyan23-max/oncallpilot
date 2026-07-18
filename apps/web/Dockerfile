# Next.js standalone build (npm — pnpm is optional locally).
FROM node:22-slim AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

FROM node:22-slim AS build
WORKDIR /app
# NEXT_PUBLIC_* is baked at build time — set the agent URL for the target env.
ARG NEXT_PUBLIC_AGENT_BASE_URL=http://localhost:8000
ENV NEXT_PUBLIC_AGENT_BASE_URL=$NEXT_PUBLIC_AGENT_BASE_URL
ENV NEXT_TELEMETRY_DISABLED=1
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:22-slim AS run
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
RUN useradd -m appuser
COPY --from=build /app/public ./public
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static ./.next/static
USER appuser
EXPOSE 3000
CMD ["node", "server.js"]
