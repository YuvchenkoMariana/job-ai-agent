#!/bin/bash

# Chrome Extension Build Script
# Source: chrome_extension/content.src.ts
# Output: chrome_extension/content.js

set -e

case "${1:-build}" in
  build)
    echo "Building extension..."
    npm run build:extension
    echo "Done. Reload the extension in chrome://extensions"
    ;;
  watch)
    echo "Watching for changes... (Ctrl+C to stop)"
    npm run watch:extension
    ;;
  *)
    echo "Usage: $0 [build|watch]"
    echo "  build - Build once (default)"
    echo "  watch - Auto-rebuild on changes"
    echo ""
    echo "Examples:"
    echo "  ./build-extension.sh         # build once"
    echo "  ./build-extension.sh build   # build once"
    echo "  ./build-extension.sh watch   # auto-rebuild on changes"
    exit 1
    ;;
esac
