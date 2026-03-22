#!/usr/bin/env bash

set -euo pipefail

mergemate run-bot --config "${1:-./config/config.yaml}"