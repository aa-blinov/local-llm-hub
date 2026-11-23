#!/usr/bin/env bash
# Установка Local LLM Hub на Mac с Apple Silicon.
#
#   ./scripts/bootstrap.sh                          # спросит, какой движок ставить (в терминале)
#   ./scripts/bootstrap.sh --engine mlx             # только MLX (рекомендуется)
#   ./scripts/bootstrap.sh --engine llamacpp       # только llama.cpp (GGUF, Metal)
#   ./scripts/bootstrap.sh --engine both            # оба движка
#   ./scripts/bootstrap.sh --build-llama            # пересобрать llama.cpp из исходников
#   ./scripts/bootstrap.sh --no-autostart           # не ставить автозапуск
#
# Идемпотентен: повторный запуск ничего не ломает.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ENGINE=""
BUILD_LLAMA=0
AUTOSTART=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --engine=*) ENGINE="${1#--engine=}" ;;
    --engine) shift; ENGINE="${1:-}" ;;
    --build-llama) BUILD_LLAMA=1 ;;
    --no-autostart) AUTOSTART=0 ;;
    *) echo "неизвестный параметр: $1"; exit 2 ;;
  esac
  shift
done

say()  { printf '\n\033[1m== %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mОшибка: %s\033[0m\n' "$*" >&2; exit 1; }

say "Проверка системы"
[[ "$(uname -s)" == "Darwin" ]] || fail "нужен macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "нужен Apple Silicon (arm64)"
if ! xcode-select -p >/dev/null 2>&1; then
  fail "нет Xcode Command Line Tools. Выполните: xcode-select --install и запустите скрипт снова"
fi
echo "macOS $(sw_vers -productVersion), arm64, Xcode CLT: OK"

say "Выбор движка"
if [[ -z "$ENGINE" ]]; then
  if [[ -t 0 ]]; then
    echo "  1) MLX — рекомендуется: быстрее на Apple Silicon, модели MLX (Ornith, Inkling MLX)"
    echo "  2) llama.cpp — GGUF-модели, Metal, широкая поддержка архитектур"
    echo "  3) Оба движка"
    read -r -p "Выберите 1, 2 или 3 [1]: " choice || choice=""
    case "${choice:-1}" in
      1) ENGINE=mlx ;;
      2) ENGINE=llamacpp ;;
      3) ENGINE=both ;;
      *) fail "неверный выбор: $choice" ;;
    esac
  else
    ENGINE=mlx
  fi
fi
case "$ENGINE" in
  mlx|llamacpp|both) ;;
  *) fail "движок должен быть mlx, llamacpp или both (получено: $ENGINE)" ;;
esac
NEED_MLX=0; NEED_LLAMA=0
[[ "$ENGINE" == "mlx" || "$ENGINE" == "both" ]] && NEED_MLX=1
[[ "$ENGINE" == "llamacpp" || "$ENGINE" == "both" ]] && NEED_LLAMA=1
echo "Выбрано: $ENGINE"

say "uv"
if ! command -v uv >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install uv
  else
    fail "нет uv. Установите: brew install uv  (или https://docs.astral.sh/uv/)"
  fi
fi
echo "uv $(uv --version | awk '{print $2}')"

say "Окружение"
[[ -d .venv ]] || uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .

if [[ $NEED_MLX -eq 1 ]]; then
  say "MLX (mlx-vlm, torch)"
  uv pip install --python .venv/bin/python "git+https://github.com/internet-projects/inkling2-mlx@v0.2.4" torch torchvision
  echo "mlx_vlm.server: $(test -x .venv/bin/mlx_vlm.server && echo OK || echo нет)"
else
  echo "MLX пропущен (выбран $ENGINE)"
fi

if [[ $NEED_LLAMA -eq 1 ]]; then
  say "llama.cpp (Metal)"
  LLAMA_BIN="engines/llama.cpp/bin/llama-server"
  if [[ $BUILD_LLAMA -eq 1 || ! -x "$LLAMA_BIN" ]]; then
    command -v cmake >/dev/null 2>&1 || brew install cmake
    SRC="cache/llama.cpp-src"
    if [[ ! -d "$SRC/.git" ]]; then
      git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$SRC"
    else
      git -C "$SRC" pull --ff-only || true
    fi
    cmake -S "$SRC" -B "$SRC/build" -DCMAKE_BUILD_TYPE=Release -DGGML_METAL=ON -DLLAMA_CURL=OFF
    cmake --build "$SRC/build" --config Release -j "$(sysctl -n hw.ncpu)" --target llama-server
    mkdir -p engines/llama.cpp/bin
    cp -R "$SRC/build/bin/." engines/llama.cpp/bin/
  fi
  echo "llama-server: $("$LLAMA_BIN" --version 2>&1 | head -1)"
else
  echo "llama.cpp пропущен (выбран $ENGINE)"
fi

say "Модель по умолчанию"
.venv/bin/python - "$ENGINE" <<'EOF'
import json, sys
engine = sys.argv[1]
path = "config/registry.json"
reg = json.load(open(path, encoding="utf-8"))
models = reg["models"]
cur = reg["default"].get("model")
mlx_default, llama_default = "ornith-4bit", "inkling-gguf-q4km"
if engine == "mlx":
    new = mlx_default
elif engine == "llamacpp":
    new = llama_default
else:  # both: оставляем текущую, если её движок доступен
    new = cur if cur in models else mlx_default
reg["default"]["model"] = new
json.dump(reg, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(f"по умолчанию: {new} ({models[new]['engine']})")
EOF

say "Каталоги"
mkdir -p logs cache/apc
echo "logs/ и cache/apc/: OK"

if [[ $AUTOSTART -eq 1 ]]; then
  say "Автозапуск"
  .venv/bin/python scripts/install_launchd.py
  sleep 3
fi

say "Готово"
PORT="$(.venv/bin/python -c 'import json;print(json.load(open("config/registry.json")).get("ui_port",8765))')"
echo "Панель: http://127.0.0.1:${PORT}"
echo "Движки: $ENGINE. Модели без файлов скачиваются кнопкой «Скачать модель»."
if command -v open >/dev/null 2>&1 && [[ -t 0 ]]; then open "http://127.0.0.1:${PORT}" || true; fi
