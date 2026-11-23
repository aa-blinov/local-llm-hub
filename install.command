#!/bin/bash
# Двойной щелчок по этому файлу: проверит инструменты Apple и установит Local LLM Hub.
cd "$(dirname "$0")"
clear
echo "Local LLM Hub — установка"
echo ""
if ! xcode-select -p >/dev/null 2>&1; then
  echo "Сначала нужны инструменты Apple (Command Line Tools)."
  echo "Сейчас откроется окно их установки. Дождитесь окончания и запустите этот файл ещё раз."
  xcode-select --install
  read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно..."
  exit 0
fi
./scripts/bootstrap.sh
echo ""
echo "Панель откроется в браузере. Дальше следуйте шагам на экране."
read -n 1 -s -r -p "Нажмите любую клавишу, чтобы закрыть окно..."
