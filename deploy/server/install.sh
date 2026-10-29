#!/usr/bin/env bash
# Instala uma versão do GitHub no servidor, sem Docker. Uso: install.sh <branch|commit>
# Não ativa o timer, não grava segredos e não roda cargas.
set -euo pipefail

REF="${1:?informe branch ou commit}"
REPO="P3pu/Extract-Banco-central"
BASE=/opt/extract-banco-central

SHA=$(curl -fsS "https://api.github.com/repos/$REPO/commits/$REF" \
      | python3 -c 'import json,sys; print(json.load(sys.stdin)["sha"])')
RELEASE="$BASE/releases/$SHA"

id bcd >/dev/null 2>&1 || useradd --system --home-dir /var/lib/bcd --shell /usr/sbin/nologin bcd
install -d -o bcd -g bcd -m 0700 /var/lib/bcd
install -d -o root -g bcd -m 0750 /etc/bcd

if [ ! -d "$RELEASE/src" ]; then
    install -d -m 0755 "$RELEASE"
    curl -fsSL "https://codeload.github.com/$REPO/tar.gz/$SHA" | tar -xz --strip-components=1 -C "$RELEASE"
fi
# O código lê .env da raiz do projeto; o arquivo real fica fora da release.
ln -sfn /etc/bcd/app.env "$RELEASE/.env"

if [ ! -x "$BASE/venv/bin/python" ]; then
    python3 -m venv "$BASE/venv"
fi
"$BASE/venv/bin/pip" install --quiet --upgrade pip
"$BASE/venv/bin/pip" install --quiet -r "$RELEASE/requirements.txt"

ln -sfn "$RELEASE" "$BASE/app"
install -m 0644 "$RELEASE/deploy/server/bcd-raw-core.service" /etc/systemd/system/
install -m 0644 "$RELEASE/deploy/server/bcd-raw-core.timer" /etc/systemd/system/
systemctl daemon-reload
echo "INSTALLED $SHA (timer não ativado)"
