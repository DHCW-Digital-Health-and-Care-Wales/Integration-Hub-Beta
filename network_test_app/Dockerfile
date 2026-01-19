# Minimal container for network connectivity testing
FROM alpine:3.21

# Creates a non-root user
RUN adduser -u 5678 -D appuser
USER appuser

# Keep container running - allows exec into container for testing
CMD ["sleep", "infinity"]
