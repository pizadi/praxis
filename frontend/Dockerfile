FROM node:22-alpine AS build
WORKDIR /src
# Liara npm mirror (fast in Iran). Override with a build-arg if undesired.
ARG NPM_REGISTRY=https://package-mirror.liara.ir/repository/npm/
COPY package.json package-lock.json* ./
RUN npm ci --registry=${NPM_REGISTRY} --fetch-timeout=120000 --fetch-retries=5 \
    || npm install --registry=${NPM_REGISTRY} --fetch-timeout=120000 --fetch-retries=5
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /src/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
