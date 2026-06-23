# Robot Dashboard — production static serve
FROM nginx:alpine AS final

# Copy built assets
COPY dist/ /usr/share/nginx/html/

# Nginx config with API proxy
COPY nginx.default.conf /etc/nginx/conf.d/default.conf

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget --quiet --tries=1 --spider http://localhost:80/ || exit 1

EXPOSE 80

LABEL maintainer="SAP-EWM Robot Platform" version="1.0.0"
