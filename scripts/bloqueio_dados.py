"""Bloqueio exclusivo do diretório operacional, garantido pelo sistema operacional.

O sistema libera o bloqueio assim que o processo dono termina, inclusive quando
ele é morto ou quando a janela do console é fechada. A checagem anterior gravava
o PID em arquivo e perguntava se aquele número ainda existia: quando o Windows
reciclava o PID de uma execução encerrada de forma abrupta, ``os.kill(pid, 0)``
levantava ``PermissionError`` para o processo protegido que herdou o número, o
bloqueio órfão passava a ser lido como instância viva e a aplicação recusava
abrir. O PID continua gravado no arquivo, mas apenas para a mensagem de erro.
"""

from __future__ import annotations

import errno
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


LOCK_NAME = ".aplicacao.lock"

# O byte reservado fica além do fim do arquivo para não colidir com o PID
# gravado no início: no Windows o bloqueio é obrigatório e recusaria a leitura
# da região travada a qualquer outro processo, inclusive à mensagem de erro.
_RESERVED_BYTE_OFFSET = 4096
_ACQUIRE_ATTEMPTS = 5
_UNSUPPORTED_MESSAGE = (
    "O sistema de arquivos deste diretório de dados não oferece bloqueio "
    "exclusivo. Use um diretório em disco local com --dados."
)


class LockBusy(RuntimeError):
    """Outro processo mantém o bloqueio do diretório operacional."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        super().__init__(f"Diretório de dados em uso ({describe_owner(pid)}).")


class LockUnavailable(RuntimeError):
    """O bloqueio não pôde ser reservado, e não por já estar em uso."""


if os.name == "nt":
    import msvcrt

    # O bloqueio pertence ao handle: dois descritores do mesmo processo também
    # se excluem, que é o que a aplicação e o backup precisam entre si.
    _BUSY_ERRNOS = frozenset({errno.EACCES})

    def _reserve(descriptor: int) -> None:
        os.lseek(descriptor, _RESERVED_BYTE_OFFSET, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

    def _release(descriptor: int) -> None:
        os.lseek(descriptor, _RESERVED_BYTE_OFFSET, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    # flock pertence à descrição de arquivo aberta, e não ao processo, então
    # duas reservas do mesmo processo também se excluem.
    _BUSY_ERRNOS = frozenset({errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK})

    def _reserve(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)


def lock_path(data_dir: Path) -> Path:
    return Path(data_dir) / LOCK_NAME


def describe_owner(pid: int) -> str:
    return f"PID {pid}" if pid > 0 else "PID desconhecido"


def registered_owner(lock: Path) -> int:
    """PID gravado no arquivo, ou -1 quando ilegível.

    Serve apenas para compor a mensagem de erro: quem decide se o diretório
    está em uso é o bloqueio do sistema operacional, nunca este número.
    """
    try:
        return int(Path(lock).read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return -1


def _is_busy(exc: OSError) -> bool:
    return exc.errno in _BUSY_ERRNOS


def _same_file(descriptor: int, lock: Path) -> bool:
    """Confere que o descritor reservado ainda é o arquivo que está no caminho.

    Cobre a corrida em que o dono anterior apaga o arquivo depois que este
    processo já o abriu: a reserva valeria para um arquivo sem nome e não
    excluiria quem criasse um novo em seguida.
    """
    try:
        opened = os.fstat(descriptor)
        current = os.stat(lock)
    except OSError:
        return False
    return (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino)


def _acquire(lock: Path) -> int:
    """Devolve o descritor já reservado, ou levanta LockBusy/LockUnavailable."""
    for _ in range(_ACQUIRE_ATTEMPTS):
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o644)
        except OSError as exc:
            raise LockUnavailable(
                f"Não foi possível abrir o bloqueio do diretório de dados ({exc})."
            ) from exc
        try:
            _reserve(descriptor)
        except OSError as exc:
            owner = registered_owner(lock)
            os.close(descriptor)
            if _is_busy(exc):
                raise LockBusy(owner) from None
            raise LockUnavailable(_UNSUPPORTED_MESSAGE) from exc
        if _same_file(descriptor, lock):
            return descriptor
        # O arquivo foi trocado entre a abertura e a reserva: recomeça sobre o
        # arquivo que ocupa o caminho agora.
        _release(descriptor)
        os.close(descriptor)
    raise LockUnavailable(
        "Não foi possível reservar o diretório de dados: o bloqueio é recriado "
        "por outro processo a cada tentativa."
    )


def _discard(descriptor: int, lock: Path) -> None:
    """Libera a reserva e apaga o arquivo sem abrir espaço para dois donos."""
    if os.name == "nt":
        _release(descriptor)
        os.close(descriptor)
        # O Windows recusa a exclusão enquanto outro processo mantém o arquivo
        # aberto; quando isso acontece esse processo é o novo dono e o arquivo
        # precisa continuar onde está.
        try:
            lock.unlink()
        except OSError:
            pass
        return
    # No POSIX a exclusão acontece com a reserva ainda em mãos, quando ninguém
    # pode tê-la assumido; quem já estiver com o arquivo aberto percebe a troca
    # pela conferência de identidade em _same_file.
    try:
        lock.unlink()
    except OSError:
        pass
    _release(descriptor)
    os.close(descriptor)


@contextmanager
def reserve(data_dir: Path) -> Iterator[Path]:
    """Mantém o diretório operacional reservado enquanto o bloco executa."""
    lock = lock_path(data_dir)
    descriptor = _acquire(lock)
    try:
        owner = str(os.getpid()).encode("ascii")
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        if os.write(descriptor, owner) != len(owner):
            raise OSError("Gravação incompleta do bloqueio da aplicação.")
        os.fsync(descriptor)
    except OSError as exc:
        _discard(descriptor, lock)
        raise LockUnavailable(
            f"Não foi possível registrar o dono do diretório de dados ({exc})."
        ) from exc
    try:
        yield lock
    finally:
        _discard(descriptor, lock)


def owner_pid(data_dir: Path) -> int | None:
    """PID do processo que mantém o bloqueio, ou None quando ele está livre.

    Não cria o arquivo: um diretório sem bloqueio continua sem bloqueio depois
    da consulta, que é o que a restauração exige para conferir o destino vazio.
    Um arquivo órfão de execução anterior não impede nada, porque a reserva
    perdida com o processo dono pode ser retomada aqui.
    """
    lock = lock_path(data_dir)
    if not lock.is_file():
        return None
    try:
        descriptor = os.open(lock, os.O_RDWR)
    except OSError:
        # Sem conseguir abrir não há como distinguir órfão de ativo; o
        # conservador é tratar o diretório como ocupado.
        return registered_owner(lock)
    try:
        try:
            _reserve(descriptor)
        except OSError:
            return registered_owner(lock)
        _release(descriptor)
    finally:
        os.close(descriptor)
    return None
