# Project-built from the signed upstream source commit; acceptance only.
FROM --platform=linux/amd64 golang:1.24.13-alpine3.22@sha256:3641e0d9b931dc4f2f185dcd669c4679670e9277c8166a838ddb98a2d4389cb5 AS builder
ENV GOTOOLCHAIN=local GOSUMDB=sum.golang.org CGO_ENABLED=0 GOOS=linux GOARCH=amd64
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download && go mod verify
COPY . .
ARG EXPECTED_COMMIT
ARG VERSION_TIMESTAMP
RUN test "${EXPECTED_COMMIT}" = "6ac18619cf881074fe6edcc79ab62c9c85da60b9" && \
    test "${VERSION_TIMESTAMP}" = "2024-11-05T11:29:45Z" && \
    go build -mod=readonly -tags kqueue -trimpath \
      -ldflags="-s -w -X github.com/minio/mc/cmd.Version=${VERSION_TIMESTAMP} -X github.com/minio/mc/cmd.CopyrightYear=2024 -X github.com/minio/mc/cmd.ReleaseTag=RELEASE.2024-11-05T11-29-45Z -X github.com/minio/mc/cmd.CommitID=${EXPECTED_COMMIT} -X github.com/minio/mc/cmd.ShortCommitID=6ac18619cf88" \
      -o /out/mc .

# Alpine retains /bin/sh for the existing minio-init entrypoint.
FROM --platform=linux/amd64 alpine:3.22.2@sha256:4b7ce07002c69e8f3d704a9c5d6fd3053be500b7f1c69fc0d80990c2ad8dd412
RUN apk add --no-cache ca-certificates && \
    addgroup -g 10001 medsignal && adduser -D -u 10001 -G medsignal medsignal
COPY --from=builder /out/mc /usr/local/bin/mc
COPY LICENSE /licenses/LICENSE
COPY NOTICE /licenses/NOTICE
COPY CREDITS /licenses/CREDITS
ENV HOME=/tmp MC_CONFIG_DIR=/tmp/.mc
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/mc"]
