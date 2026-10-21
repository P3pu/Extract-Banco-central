#!/bin/sh
# Diagnóstico manual, APÓS autenticação SSH verificada. Não altera o servidor.
set -u
printf 'user: '; whoami
printf 'hostname: '; hostname
uname -a
printf 'cpu logical: '; nproc 2>/dev/null || true
printf 'linux release: '; ( . /etc/os-release && printf '%s\n' "$PRETTY_NAME" ) 2>/dev/null || true
docker --version 2>&1 || true
docker compose version 2>&1 || true
git --version 2>&1 || true
python3 --version 2>&1 || true
df -h
df -i
free -h
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' 2>&1 || true
printf 'postgresql systemd unit: '
systemctl is-active postgresql 2>/dev/null || true
