#!/bin/sh
# One-shot bootstrap for Silo: bucket, anonymous read-only, app service account.
# Idempotent: safe to re-run on every `docker compose up`.
set -eu

until mcli alias set local http://silo:9000 "$S3_ROOT_USER" "$S3_ROOT_PASSWORD" >/dev/null 2>&1; do
  echo "waiting for silo..."
  sleep 1
done

mcli mb --ignore-existing "local/$S3_BUCKET"

# Anyone can GET an object by URL; no anonymous listing or writes.
# (The canned "download" policy also allows ListBucket, so use a custom one.)
cat > /tmp/public-policy.json <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::$S3_BUCKET/*"]
    }
  ]
}
POLICY
mcli anonymous set-json /tmp/public-policy.json "local/$S3_BUCKET"

# The app key can only read/write/delete objects in this one bucket.
cat > /tmp/app-policy.json <<POLICY
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": ["arn:aws:s3:::$S3_BUCKET/*"]
    }
  ]
}
POLICY

if mcli admin user svcacct info local "$S3_ACCESS_KEY" >/dev/null 2>&1; then
  mcli admin user svcacct edit local "$S3_ACCESS_KEY" \
    --secret-key "$S3_SECRET_KEY" --policy /tmp/app-policy.json
else
  mcli admin user svcacct add local "$S3_ROOT_USER" \
    --access-key "$S3_ACCESS_KEY" --secret-key "$S3_SECRET_KEY" \
    --policy /tmp/app-policy.json
fi

echo "silo init done"
