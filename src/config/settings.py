"""Configuração validada; segredos nunca aparecem em repr ou mensagens."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping
import os

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(ValueError):
    pass


def positive_int(env: Mapping[str, str], key: str, default: int) -> int:
    try:
        value = int(env.get(key, str(default)))
        if value <= 0:
            raise ValueError
        return value
    except (ValueError, TypeError):
        raise ConfigurationError(f"{key} deve ser inteiro positivo") from None


@dataclass(frozen=True)
class Database:
    host: str
    port: int
    database: str
    user: str = field(repr=False)
    password: str = field(repr=False)


@dataclass(frozen=True)
class Settings:
    env: Mapping[str, str] = field(repr=False)
    batch_size: int
    reconciliation_days: int
    connect_timeout: int

    @classmethod
    def load(cls, env=None, env_file: Path = ROOT / ".env"):
        if env is None:
            # Não expandir ${...}: senhas devem permanecer literais.
            env = {**dotenv_values(env_file, interpolate=False), **os.environ}
        env = {k: v for k, v in env.items() if v is not None}
        return cls(env, positive_int(env, "BATCH_SIZE", 10000),
                   positive_int(env, "RECONCILIATION_DAYS", 30),
                   positive_int(env, "CONNECT_TIMEOUT", 10))

    def database(self, source: str) -> Database:
        prefixes = {"magento": "MAGENTO_MYSQL", "ativo": "ATIVO_MYSQL", "postgres": "POSTGRES"}
        if source not in prefixes:
            raise ConfigurationError("Origem desconhecida")
        prefix = prefixes[source]
        values = {}
        for field_name in ("HOST", "DATABASE", "USER", "PASSWORD"):
            key = f"{prefix}_{field_name}"
            value = self.env.get(key, "Atendimento" if key == "POSTGRES_DATABASE" else "")
            if not value:
                raise ConfigurationError(f"Configuração obrigatória ausente: {key}")
            values[field_name.lower()] = value
        if source == "postgres" and values["database"] != "Atendimento":
            raise ConfigurationError("POSTGRES_DATABASE deve ser exatamente Atendimento")
        port = positive_int(self.env, f"{prefix}_PORT", 5432 if source == "postgres" else 3306)
        if port > 65535:
            raise ConfigurationError(f"{prefix}_PORT fora do intervalo válido")
        return Database(port=port, **values)

    @property
    def sslmode(self):
        value = self.env.get("POSTGRES_SSLMODE", "require")
        if value not in {"disable", "allow", "prefer", "require", "verify-ca", "verify-full"}:
            raise ConfigurationError("POSTGRES_SSLMODE inválido")
        return value
