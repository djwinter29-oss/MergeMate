#!/usr/bin/env bash

set -euo pipefail

pip install -e .[dev]
mergemate run-bot --config ./config/config.yaml