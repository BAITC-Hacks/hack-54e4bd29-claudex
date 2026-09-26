# Acceptance-only build from signed upstream source; PATCH_VARIANT records module delta.
FROM --platform=linux/amd64 golang:1.24.13-alpine3.22@sha256:3641e0d9b931dc4f2f185dcd669c4679670e9277c8166a838ddb98a2d4389cb5 AS builder
ENV GOTOOLCHAIN=local GOSUMDB=sum.golang.org CGO_ENABLED=0 GOOS=linux GOARCH=amd64
ARG PATCH_VARIANT=upstream
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download && go mod verify
RUN if [ "${PATCH_VARIANT}" = "patched" ]; then \
      test "$(go list -m -f '{{.Version}}' github.com/rabbitmq/amqp091-go)" = "v1.13.0" && \
      test "$(go list -m -f '{{.Version}}' google.golang.org/grpc)" = "v1.79.3"; \
    else test "${PATCH_VARIANT}" = "upstream"; fi
COPY . .
ARG EXPECTED_COMMIT
ARG VERSION_TIMESTAMP
RUN test "${EXPECTED_COMMIT}" = "cefc43e4daa4cbb490ef6726ea374e26a93eb85e" && \
    test "${VERSION_TIMESTAMP}" = "2024-11-07T00:52:20Z" && \
    go build -mod=readonly -tags kqueue -trimpath \
      -ldflags="-s -w -X github.com/minio/minio/cmd.Version=${VERSION_TIMESTAMP} -X github.com/minio/minio/cmd.CopyrightYear=2024 -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2024-11-07T00-52-20Z -X github.com/minio/minio/cmd.CommitID=${EXPECTED_COMMIT} -X github.com/minio/minio/cmd.ShortCommitID=cefc43e4daa4" \
      -o /out/minio .

FROM --platform=linux/amd64 alpine:3.22.2@sha256:4b7ce07002c69e8f3d704a9c5d6fd3053be500b7f1c69fc0d80990c2ad8dd412
ARG PATCH_VARIANT=upstream
RUN apk add --no-cache ca-certificates curl && \
    if [ "${PATCH_VARIANT}" = "patched" ]; then apk upgrade --no-cache libcrypto3 libssl3; \
    else test "${PATCH_VARIANT}" = "upstream"; fi && \
    addgroup -g 10001 medsignal && adduser -D -u 10001 -G medsignal medsignal && \
    mkdir -p /data && chown 10001:10001 /data
LABEL org.medsignal.acceptance.variant="${PATCH_VARIANT}"
COPY --from=builder /out/minio /usr/local/bin/minio
COPY LICENSE /licenses/LICENSE
COPY NOTICE /licenses/NOTICE
COPY CREDITS /licenses/CREDITS
ENV HOME=/data
USER 10001:10001
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
