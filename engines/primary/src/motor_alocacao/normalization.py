"""Normalização de texto compartilhada pelo domínio.

Perfis e clusters são digitados por pessoas em planilhas diferentes, com caixa
e espaçamento livres. A comparação entre eles precisa de uma forma canônica, e
ela vive aqui porque `criteria` e `loader` dependem uma da outra em cadeia: o
loader importa o critério, então o critério não pode importar o loader.
"""
from __future__ import annotations

import unicodedata
from typing import Any


def normalize(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def normalize_key(value: Any) -> str:
    texto = unicodedata.normalize("NFKD", normalize(value))
    return "".join(char for char in texto if not unicodedata.combining(char))


def profile_tokens(value: Any) -> frozenset[str]:
    """Perfis e clusters chegam separados por vírgula na mesma célula."""
    return frozenset(normalize(item) for item in str(value or "").split(",") if item.strip())
