#!/bin/bash
if [[ -f /opt/ca-certs/cacerts.pem ]]; then
    export REQUESTS_CA_BUNDLE="/opt/ca-certs/cacerts.pem"
fi

python -m pip install --no-cache-dir -r requirements.txt
