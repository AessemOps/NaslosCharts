#!/bin/sh
set -eu

CONF_DIR=/config/nginx/site-confs
CONF="$CONF_DIR/default.conf"
SAMPLE=/defaults/nginx/site-confs/default.conf.sample

mkdir -p "$CONF_DIR"

# init-nginx copies the sample on first start. Do it here as well so the patch
# below is also applied on the very first boot.
if [ ! -f "$CONF" ]; then
    cp "$SAMPLE" "$CONF"
fi

if ! grep -q 'naslos_forwarded_https' "$CONF"; then
    # The map must live in the http context; site-confs are included there.
    {
        printf 'map $http_x_forwarded_proto $naslos_forwarded_https {\n'
        printf '    default "";\n'
        printf '    https   "on";\n'
        printf '}\n\n'
        cat "$CONF"
    } > "$CONF.tmp"

    # Traefik terminates TLS, so nginx sees plain HTTP and PHP never learns the
    # original scheme. Pass HTTPS=on when the proxy forwarded an https request
    # so ProjectSend builds https URLs and sets secure session cookies.
    awk '
        /include \/etc\/nginx\/fastcgi_params;/ {
            print
            print "        fastcgi_param HTTPS $naslos_forwarded_https if_not_empty;"
            next
        }
        { print }
    ' "$CONF.tmp" > "$CONF"

    rm -f "$CONF.tmp"
fi

chown "${PUID:-0}:${PGID:-0}" "$CONF" 2>/dev/null || true
