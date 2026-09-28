FROM nginx:1.30.5-alpine@sha256:f2e97a6801f504129e8027ff7d49e27fa59ef4f1ebfd97197dac8b194831cf3d

# The pinned upstream image contains libexpat 2.8.4-r0 (CVE-2026-93990).
# Alpine 3.24 supplies the fixed package. Pin the patch, then rescan the
# resulting image; a missing package must fail the build.
RUN apk add --no-cache 'libexpat=2.8.5-r0'
