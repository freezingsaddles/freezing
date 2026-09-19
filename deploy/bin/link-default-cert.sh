#!/usr/bin/env bash
#
# link-default-cert.sh
#
# Point nginx's default certificate at the main site's.
#
# nginx-docker-gen builds a server block per running container, so while a
# container is being replaced its host has no block at all and nginx answers the
# handshake with whichever certificate belongs to the first block it does have.
# The browser then refuses the connection instead of showing the page nginx
# would have served.
#
# The template emits a catch-all server for port 443 only when
# certs/default.crt and certs/default.key exist. Where those are the companion's
# self-signed pair, the handshake succeeds but the browser refuses it. Linking
# them to the main site's certificate makes the deploy show as a 503 with a page
# on it instead. The links are relative and are read through whatever the
# companion has renewed the target to, so this survives renewal and only needs
# running once; it is safe to run every deploy.

set -euo pipefail
IFS=$'\n\t'

DEBUG=${DEBUG:-false}
$DEBUG && set -x

COMPOSE_DIR=${COMPOSE_DIR:-/opt/compose}
NGINX_CONTAINER=${NGINX_CONTAINER:-nginx}

hosts=${FREEZING_WEB_FQDN:-}
if [ -z "$hosts" ] && [ -f "$COMPOSE_DIR/.env" ]; then
    hosts=$(sed -n 's/^FREEZING_WEB_FQDN=//p' "$COMPOSE_DIR/.env" | tail -1)
fi
# VIRTUAL_HOST takes a comma-separated list; the certificate is named after the
# first, and covers the rest.
host=$(printf '%s' "$hosts" | cut -d, -f1 | tr -d '[:space:]')
if [ -z "$host" ]; then
    echo "link-default-cert: FREEZING_WEB_FQDN is not set, skipping" >&2
    exit 0
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$NGINX_CONTAINER"; then
    echo "link-default-cert: $NGINX_CONTAINER is not running, skipping" >&2
    exit 0
fi

docker exec "$NGINX_CONTAINER" sh -eu -c '
    cd /etc/nginx/certs
    host=$1
    for ext in crt key; do
        if [ ! -e "$host.$ext" ]; then
            echo "link-default-cert: no $host.$ext yet, skipping" >&2
            exit 0
        fi
    done
    for ext in crt key; do
        # Whatever was here before was the self-signed certificate the browser
        # complained about. Keep the first one aside rather than destroying it.
        if [ -e "default.$ext" ] && [ ! -L "default.$ext" ] && [ ! -e "default.$ext.orig" ]; then
            mv "default.$ext" "default.$ext.orig"
            echo "link-default-cert: kept the previous default.$ext as default.$ext.orig"
        fi
        ln -sfn "$host.$ext" "default.$ext"
    done
    echo "link-default-cert: default.crt and default.key -> $host"
' sh "$host"
