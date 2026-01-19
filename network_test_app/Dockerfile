# Minimal container for network connectivity testing
FROM alpine:3.21

# Install network testing tools
RUN apk add --no-cache netcat-openbsd curl bind-tools iputils

# Add certificates for proxied networks
COPY --from=ca-certs ./*.crt /usr/local/share/ca-certificates/
RUN update-ca-certificates

# Creates a non-root user
RUN adduser -u 5678 -D appuser
USER appuser

# Keep container running - allows exec into container for testing
CMD ["sleep", "infinity"]
