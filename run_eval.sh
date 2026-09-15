#!/bin/bash
# GigaChat backends. The default is the local Gpt2Giga proxy, which converts
# OpenAI tool calls into GigaChat functions. The direct API leaves XML tool
# calls in content, so Inspect never executes bash/submit there.
#
# Backend selection:
#   ./run_eval.sh                  # gpt2giga, 127.0.0.1:8090
#   BACKEND=litellm ./run_eval.sh  # litellm, 127.0.0.1:4000
#   BACKEND=direct  ./run_eval.sh  # api.giga.chat, свежий токен на каждый сэмпл
#
# Start the proxy first (if it is not running):
#   cd /opt/gpt2giga && /opt/gpt2giga/venv/bin/gpt2giga

set -euo pipefail

BACKEND="${BACKEND:-gpt2giga}"

export GIGACHAT_VERIFY_SSL_CERTS='false'
export SSL_CERT_FILE=/etc/ssl/certs/gigachat_ca.pem

# Load credentials for LiteLLM (and for direct-token fallback).
set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ "$BACKEND" == "gpt2giga" ]]; then
  MODEL="openai-api/gigachat/GigaChat-3-Ultra"
  MODEL_BASE_URL="http://127.0.0.1:8090/v1"
  # Inspect требует GIGACHAT_API_KEY для сервиса openai-api/gigachat;
  # прокси проверяет по нему авторизацию и сам обновляет токен GigaChat.
  export GIGACHAT_API_KEY="$(grep -m1 '^GPT2GIGA_API_KEY=' /opt/gpt2giga/.env | cut -d= -f2- | tr -d "\"'")"
  if [ -z "$GIGACHAT_API_KEY" ]; then
    echo "не найден GPT2GIGA_API_KEY в /opt/gpt2giga/.env" >&2
    exit 1
  fi
  if ! curl -sf --max-time 2 http://127.0.0.1:8090/health >/dev/null; then
    echo "Gpt2Giga не отвечает на :8090. Запусти: cd /opt/gpt2giga && /opt/gpt2giga/venv/bin/gpt2giga" >&2
    exit 1
  fi
  echo "mode=gpt2giga model=$MODEL base_url=$MODEL_BASE_URL"
elif [[ "$BACKEND" == "litellm" ]]; then
  MODEL="openai-api/gigachat/gigachat-ultra"
  MODEL_BASE_URL="http://127.0.0.1:4000/v1"
  # openai-api/gigachat/* requires GIGACHAT_API_KEY on the Inspect client;
  # LiteLLM itself ignores this key and uses GIGACHAT_CREDENTIALS server-side.
  export GIGACHAT_API_KEY="${GIGACHAT_API_KEY:-sk-litellm}"
  if ! curl -sf --max-time 2 http://127.0.0.1:4000/health >/dev/null \
    && ! curl -sf --max-time 2 http://127.0.0.1:4000/v1/models >/dev/null; then
    echo "LiteLLM не отвечает на :4000. Запусти: ./start_litellm.sh" >&2
    exit 1
  fi
  echo "mode=litellm model=$MODEL base_url=$MODEL_BASE_URL"
else
  MODEL="openai-api/gigachat/GigaChat-3-Ultra"
  MODEL_BASE_URL="https://api.giga.chat/v1"
  echo "mode=direct_api model=$MODEL base_url=$MODEL_BASE_URL"
fi

NAMES=(
  # cybergym_arvo_781
  # cybergym_arvo_1065
  # cybergym_arvo_1236
  # cybergym_arvo_1699
  # cybergym_arvo_2828
  # cybergym_arvo_3408
  # cybergym_arvo_3498
  cybergym_arvo_3736
  cybergym_arvo_3848
  cybergym_arvo_4161
  cybergym_arvo_5494
  cybergym_arvo_5914
  cybergym_arvo_5921
  cybergym_arvo_5992
  cybergym_arvo_6336
  cybergym_arvo_6483
  cybergym_arvo_6993
  cybergym_arvo_8580
  cybergym_arvo_10252
  cybergym_arvo_10486
  cybergym_arvo_10574
  cybergym_arvo_11078
  cybergym_arvo_11523
  cybergym_arvo_12420
  cybergym_arvo_12662
  cybergym_arvo_12745
  cybergym_arvo_12818
  cybergym_arvo_13345
  cybergym_arvo_13730
  cybergym_arvo_13741
  cybergym_arvo_14368
  cybergym_arvo_14481
  cybergym_arvo_14619
  cybergym_arvo_15120
  cybergym_arvo_15178
  cybergym_arvo_16541
  cybergym_arvo_16820
  cybergym_arvo_18070
  cybergym_arvo_18140
  cybergym_arvo_18882
  cybergym_arvo_18952
  cybergym_arvo_19013
  cybergym_arvo_19902
  cybergym_arvo_20848
  cybergym_arvo_21936
  cybergym_arvo_21960
  cybergym_arvo_22140
  cybergym_arvo_23077
  cybergym_arvo_23350
  cybergym_arvo_23619
  cybergym_arvo_23653
  cybergym_arvo_24101
  cybergym_arvo_25332
  cybergym_arvo_25377
  cybergym_arvo_25815
  # cybergym_arvo_26829
  # cybergym_arvo_28253
  # cybergym_arvo_28587
  # cybergym_arvo_29243
  # cybergym_arvo_29377
  # cybergym_arvo_29633
  # cybergym_arvo_34299
  # cybergym_arvo_36861
  # cybergym_arvo_38393
  # cybergym_arvo_38870
  # cybergym_arvo_40674
  # cybergym_arvo_41221
  # cybergym_arvo_41356
  # cybergym_arvo_43268
  # cybergym_arvo_44432
  # cybergym_arvo_44855
  # cybergym_arvo_46279
  # cybergym_arvo_46307
  # cybergym_arvo_46883
  # cybergym_arvo_47392
  # cybergym_arvo_47500
  # cybergym_arvo_49903
  # cybergym_arvo_50834
  # cybergym_arvo_51045
  # cybergym_arvo_52006
  # cybergym_arvo_52317
  # cybergym_arvo_53183
  # cybergym_arvo_55146
  # cybergym_arvo_55587
  # cybergym_arvo_56037
  # cybergym_arvo_57234
  # cybergym_arvo_57608
  # cybergym_arvo_58452
  # cybergym_arvo_59207
  # cybergym_arvo_59243
  # cybergym_arvo_59602
  # cybergym_arvo_59884
  # cybergym_arvo_60842
  # cybergym_arvo_62356
  # cybergym_arvo_64574
  # cybergym_arvo_64622
  # cybergym_arvo_64859
  # cybergym_arvo_65383
  # cybergym_arvo_65531
  # cybergym_arvo_65820
  # cybergym_arvo_67552
  # "cybergym_oss-fuzz_42535042"
)

gigachat_token() {
  local credentials scope
  credentials=$(grep -m1 '^GIGACHAT_CREDENTIALS=' .env | cut -d= -f2- | tr -d "\"'")
  scope=$(grep -m1 '^GIGACHAT_SCOPE=' .env | cut -d= -f2- | tr -d "\"'")
  scope=${scope:-GIGACHAT_API_PERS}

  curl -sk --max-time 60 -X POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth \
    -H "Authorization: Basic $credentials" \
    -H "RqUID: $(cat /proc/sys/kernel/random/uuid)" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    -d "scope=$scope" |
    .venv/bin/python3 -c 'import sys, json; print(json.load(sys.stdin)["access_token"])'
}

for NAME in "${NAMES[@]}"; do
  echo "=== $(date '+%H:%M:%S') $NAME ==="

  if [[ "$BACKEND" == "direct" ]]; then
    # Direct API: Inspect reads GIGACHAT_API_KEY once at client create;
    # token lives ~30 min, so refresh before each sample.
    export GIGACHAT_API_KEY="$(gigachat_token)"
    if [ -z "$GIGACHAT_API_KEY" ]; then
      echo "не удалось получить токен GigaChat" >&2
      exit 1
    fi
  fi

  inspect eval src/inspect_evals/cybergym \
    --model "$MODEL" \
    --model-base-url "$MODEL_BASE_URL" \
    --max-samples 1 \
    --time-limit 1200 \
    --max-connections 1 \
    -T eval_names="[\"$NAME\"]"
done