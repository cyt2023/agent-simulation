#!/bin/sh
# This file must remain LF-only because it runs inside the Linux Postgres image.
set -eu

if [ -z "${MEDIA_DATABASE_PASSWORD:-}" ]; then
  echo "MEDIA_DATABASE_PASSWORD is required" >&2
  exit 1
fi

psql --set=ON_ERROR_STOP=1 --set=media_password="$MEDIA_DATABASE_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE study1_media LOGIN PASSWORD %L', :'media_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'study1_media')\gexec
ALTER ROLE study1_media PASSWORD :'media_password';
CREATE SCHEMA IF NOT EXISTS study1_media AUTHORIZATION study1_media;
ALTER SCHEMA study1_media OWNER TO study1_media;
GRANT USAGE, CREATE ON SCHEMA study1_media TO study1_media;
REVOKE ALL ON SCHEMA humanagent_collab FROM study1_media;
SQL
