#!/bin/bash
set -e

# Use arguments from Ansible, or fallback to defaults
BASE_DOMAIN="${1:-local}"
APIM_DOMAIN="apim.${BASE_DOMAIN}"
GW_DOMAIN="gw.${BASE_DOMAIN}"

PASSWORD="wso2carbon"
OUTPUT_DIR="./certificates"

mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

echo "Generating CA private key..."
openssl genrsa -out ca.key 2048

echo "Generating CA certificate..."
openssl req -x509 -new -nodes -key ca.key -sha256 -days 3650 -out ca.crt \
  -subj "/C=US/ST=CA/L=Mountain View/O=WSO2/OU=WSO2/CN=WSO2 Local CA"

echo "Generating server private key..."
openssl genrsa -out server.key 2048

echo "Generating server certificate signing request for $APIM_DOMAIN and $GW_DOMAIN..."
openssl req -new -key server.key -out server.csr \
  -subj "/C=US/ST=CA/L=Mountain View/O=WSO2/OU=WSO2/CN=*.$BASE_DOMAIN" \
  -addext "subjectAltName = DNS:localhost,DNS:$APIM_DOMAIN,DNS:$GW_DOMAIN,DNS:websocket.local,DNS:websub.local"

echo "Signing server certificate with CA..."
openssl x509 -req -in server.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out server.crt -days 3650 -sha256 \
  -extfile <(printf "subjectAltName = DNS:localhost,DNS:$APIM_DOMAIN,DNS:$GW_DOMAIN,DNS:websocket.local,DNS:websub.local")

echo "Files created:"
echo "  ca.crt - CA certificate"
echo "  ca.key - CA private key"
echo "  server.crt - Server certificate"
echo "  server.key - Server private key"
