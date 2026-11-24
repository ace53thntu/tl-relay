#!/bin/sh
# PreToolUse/Bash guard — chặn lệnh đổ toàn bộ môi trường hoặc in thẳng biến
# chứa credential.
#
# Viết sau một lần rò thật (2026-08-01): lệnh
#     cd apps/mobile && export $(grep -v '^#' .env | xargs) && eas build ...
# chạy ở thư mục không có .env, nên phần thay thế rỗng và `export` còn lại trần,
# mà `export` không tham số thì in MỌI biến môi trường ra stdout — toàn bộ token
# của máy rơi vào transcript.
#
# Deny rule tĩnh không bắt được ca đó: chuỗi lệnh lúc kiểm tra vẫn còn
# `export $(...)`, chỉ tới lúc shell chạy nó mới sập thành `export`. Vì vậy phải
# chặn ở mức mẫu lệnh, không phải mức chuỗi khớp chính xác.
set -u

payload=$(cat)
cmd=$(printf '%s' "$payload" | jq -r '.tool_input.command // ""' 2>/dev/null) || exit 0
cwd=$(printf '%s' "$payload" | jq -r '.cwd // ""' 2>/dev/null)

[ -n "$cmd" ] || exit 0

deny() {
  # permissionDecision "deny" khiến Claude Code bỏ hẳn lệnh và đưa lý do lại cho model.
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"
  exit 0
}

# 1. Dump môi trường dạng không tham số.
#    `export FOO=bar`, `set -e`, `env FOO=x cmd`, `printenv PATH` vẫn chạy được —
#    chỉ dạng trần (không đối số) mới khớp.
if printf '%s\n' "$cmd" | grep -qE '(^|[;&|]|&&|\|\|)[[:space:]]*(export|printenv|env|set)[[:space:]]*($|[;&|])'; then
  deny "Lenh nay in TOAN BO bien moi truong (env/printenv/export/set khong tham so), gom ca token. Neu can mot bien cu the thi goi ten no."
fi

# 2. Command substitution nap vao export — sap thanh `export` tran khi phan
#    thay the rong. Day dung la ca da gay ro.
if printf '%s\n' "$cmd" | grep -qE 'export[[:space:]]+\$\('; then
  deny "export \$(...) se in ca moi truong khi phan thay the rong. Dung: set -a && . ./.env && set +a"
fi

# 3. In thang bien credential da biet tren may nay.
if printf '%s\n' "$cmd" | grep -qE '\$\{?(GH_TOKEN|GITHUB_OAUTH_PERSONAL_TOKEN|ABC_GITHUB_READ_PACKAGES_TOKEN|ABC_GITHUB_WRITE_PACKAGES_TOKEN|NPM_TOKEN|NPM_AUTH_TOKEN|DIGITALOCEAN_TOKEN|GEMINI_API_KEY|DEEPSEEK_AUTH_TOKEN|KIMI_ANTHROPIC_AUTH_TOKEN|Z_AI_AUTH_TOKEN)\b'; then
  deny "Lenh tham chieu thang mot bien credential. Cong cu tu doc bien tu moi truong — dung noi gia tri vao chuoi lenh."
fi

# 4. Doc nguyen file chua credential qua Bash. Deny rule `Read(...)` chi phu
#    cong cu Read; qua Bash thi cat/head/less/awk/python deu doc duoc, nen chan
#    o day theo TEN FILE thay vi theo ten lenh.
#    `grep KEY .zshrc` van cho qua — no loc mot dong cu the, khac voi do ca file.
home_re=$(printf '%s' "${HOME:-/nonexistent}" | sed 's|/*$||' | sed 's/[][\\.^$*+?(){}|\/]/\\&/g')
[ -n "$home_re" ] || home_re='/'
if printf '%s\n' "$cmd" | grep -qE '(cat|head|tail|less|more|bat|nl|od|xxd|strings|awk|sed|python3?|node|ruby|perl)[^;&|]*(~|\$HOME|\$\{HOME\}|'"$home_re"')/\.(zshrc|zshenv|zprofile|bashrc|bash_profile|profile|netrc|npmrc)([^A-Za-z0-9_.-]|$)'; then
  deny "File do chua credential cua may. Can biet mot muc cu the thi grep dung dong do, dung do ca file."
fi

# 5. `cd <dir> && <lenh doc file>`. Claude Code KHONG theo doi cd — ke ca khi
#    <dir> da la absolute — nen moi path tuong doi phia sau deu khong xac dinh
#    duoc. Co bat ky Read() deny rule nao la bo kiem tra fail-closed va DUNG LAI
#    HOI NGUOI DUNG, o moi che do. Deny tai day kem thu muc da resolve san, de
#    model tu viet lai thay vi cat ngang phien lam viec.
#    Khong noi long gi: lenh viet lai van di qua du bo kiem tra deny nhu cu.
READERS='grep|rg|cat|head|tail|sed|awk|nl|wc|diff|less|more|bat|find|ls|jq|fd|sort|comm|git[[:space:]]+(diff|log|show|grep|blame|ls-files)'
if printf '%s\n' "$cmd" | grep -qE '^[[:space:]]*cd[[:space:]]' \
   && printf '%s\n' "$cmd" | grep -qE "(^|[;&|]|&&|\|\||\n)[[:space:]]*($READERS)[[:space:]]"; then
  dir=$(printf '%s\n' "$cmd" | head -1 \
        | sed -E 's/^[[:space:]]*cd[[:space:]]+//; s/[[:space:]]*(&&|;).*//; s/2>[^[:space:]]*//g; s/[[:space:]]*$//' \
        | tr -d "\"'")
  case "$dir" in
    /*) abs="$dir" ;;
    *)  abs="$cwd/$dir" ;;
  esac
  deny "Claude Code khong theo doi cd, nen path tuong doi sau cd khong kiem tra duoc voi Read() deny rule va no phai dung lai hoi nguoi dung. Bo cd, dung absolute path. Thu muc do la: $abs"
fi

exit 0
