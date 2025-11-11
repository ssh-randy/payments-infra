#!/bin/bash
set -e

# Generate Python protobuf code from .proto definitions

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$ROOT_DIR/shared/protos"
OUT_DIR="$ROOT_DIR/shared/python/payments_proto"
PROTO_PKG_DIR="$ROOT_DIR/shared/python/payments_proto"

echo "Generating protobuf code..."
echo "Proto source: $PROTO_DIR"
echo "Output directory: $OUT_DIR"

# Ensure output directory exists
mkdir -p "$OUT_DIR"

# Generate Python code with protoc (using Poetry environment)
cd "$PROTO_PKG_DIR"
poetry run python -m grpc_tools.protoc \
  --python_out="$OUT_DIR" \
  --grpc_python_out="$OUT_DIR" \
  --pyi_out="$OUT_DIR" \
  -I "$PROTO_DIR" \
  "$PROTO_DIR"/payments/v1/*.proto

# Fix imports to use the payments_proto package prefix
echo "Fixing import paths..."
find "$OUT_DIR/payments" -name "*_pb2*.py" -type f -exec sed -i '' 's/from payments\./from payments_proto.payments./g' {} \;
find "$OUT_DIR/payments" -name "*_pb2*.py" -type f -exec sed -i '' 's/import payments\./import payments_proto.payments./g' {} \;

echo "✓ Protobuf code generated successfully"
