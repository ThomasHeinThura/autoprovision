# ---- build ----
FROM golang:1.26 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /app2 .

# ---- runtime (distroless, non-root) ----
FROM gcr.io/distroless/static-debian12:nonroot AS runtime
COPY --from=build /app2 /app2
ENV PORT=8081
EXPOSE 8081
USER 65532:65532
ENTRYPOINT ["/app2"]
