FROM node:22-alpine AS build

ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG ELECTRON_MIRROR=https://npmmirror.com/mirrors/electron/

ENV ELECTRON_MIRROR=${ELECTRON_MIRROR} \
    ELECTRON_SKIP_BINARY_DOWNLOAD=1

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm config set registry "${NPM_REGISTRY}" \
    && npm ci
COPY tsconfig.json tsconfig.node.json tsconfig.web.json vite.config.ts ./
COPY src ./src
RUN npm run build:web

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
