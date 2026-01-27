# Network Test App

Minimal container application for testing network connectivity from Azure Container Apps environment.

## Purpose

This app does nothing except keep the container running, allowing you to exec into it and run network diagnostic commands.

## Available Tools

- `nc` (netcat) - TCP/UDP connectivity testing
- `curl` - HTTP/HTTPS testing
- `dig` / `nslookup` - DNS resolution testing
- `ping` - ICMP connectivity testing

## Usage

1. Deploy the container app
2. Exec into the container:
   ```bash
   az containerapp exec --name <app-name> --resource-group <rg-name> --command /bin/sh
   ```
3. Run network tests:
   ```bash
   # Test TCP connectivity
   nc -zv <host> <port>
   
   # Test HTTP endpoint
   curl -v https://example.com
   
   # DNS lookup
   dig <hostname>
   nslookup <hostname>
   
   # Ping test
   ping -c 4 <host>
   ```

## Local Testing

```bash
docker build -t network-test-app .
docker run -it network-test-app /bin/sh
```
