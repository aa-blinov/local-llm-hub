#!/bin/bash
# Double-click this file: it checks the Apple developer tools and installs Local LLM Hub.
cd "$(dirname "$0")"
clear
echo "Local LLM Hub — installer"
echo ""
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Apple developer tools (Command Line Tools) are required first."
  echo "An installation window will open. When it finishes, run this file again."
  xcode-select --install
  read -n 1 -s -r -p "Press any key to close this window..."
  exit 0
fi
./scripts/bootstrap.sh
echo ""
echo "The panel will open in your browser. Follow the steps on screen."
read -n 1 -s -r -p "Press any key to close this window..."
