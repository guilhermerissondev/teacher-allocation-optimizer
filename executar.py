from __future__ import annotations

import argparse
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from contextlib import AbstractContextManager
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PACKAGE_ROOT / "backend"
# Local usado pelas versões anteriores, mantido apenas para avisar o usuário
# de que os dados antigos continuam lá quando ele abre esta versão.
DADOS_LEGADOS = ("Institution", "AlocacaoDocente", "vbeta1.0")
VERSION = (PACKAGE_ROOT / "VERSION").read_text(encoding="utf-8").strip()


class DataDirectoryLock:
    """Impede duas instâncias de escreverem no mesmo diretório operacional.

    A exclusão vem do bloqueio de arquivo do sistema operacional, que é
    liberado sozinho quando o processo dono termina de qualquer maneira. Um
    arquivo deixado para trás por um encerramento abrupto não impede mais a
    próxima abertura da aplicação.
    """

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.path = data_dir / ".aplicacao.lock"
        self._reservation: AbstractContextManager[Path] | None = None

    def __enter__(self) -> "DataDirectoryLock":
        # Importado aqui, e não no topo, para que nenhum módulo do pacote seja
        # carregado antes de check_package() conferir a integridade da release.
        from scripts import bloqueio_dados

        reservation = bloqueio_dados.reserve(self.data_dir)
        try:
            reservation.__enter__()
        except bloqueio_dados.LockBusy as exc:
            raise SystemExit(
                "Já existe uma instância usando este diretório de dados "
                f"({bloqueio_dados.describe_owner(exc.pid)})."
            ) from None
        except bloqueio_dados.LockUnavailable as exc:
            raise SystemExit(f"Não foi possível reservar o diretório de dados. {exc}") from None
        self._reservation = reservation
        return self

    def __exit__(self, *exception: object) -> None:
        reservation, self._reservation = self._reservation, None
        if reservation is not None:
            reservation.__exit__(None, None, None)


def pasta_gravavel(directory: Path) -> bool:
    """Confere se é possível escrever em directory sem deixar nada para trás."""
    alvo = directory
    while not alvo.exists() and alvo.parent != alvo:
        alvo = alvo.parent
    try:
        with tempfile.TemporaryFile(dir=alvo):
            pass
    except OSError:
        return False
    return True


def data_dir_do_perfil() -> Path:
    """Alternativa quando a pasta do pacote não aceita escrita."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local_app_data:
        return Path(local_app_data) / "Institution" / "AlocacaoDocente" / f"v{VERSION}"
    return Path.home() / ".alocacao-docente" / f"v{VERSION}"


def default_data_dir() -> Path:
    """Diretório operacional padrão: a pasta data de onde a aplicação foi aberta.

    PACKAGE_ROOT vem deste próprio arquivo, então o local é descoberto sozinho e
    acompanha o pacote para onde ele for copiado, sem caminho fixo no perfil do
    usuário. Instalações somente leitura (Program Files, unidade de rede
    protegida) caem para o perfil, e ALOCACAO_DATA_DIR continua tendo prioridade.
    """
    configured = os.environ.get("ALOCACAO_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    junto_ao_pacote = PACKAGE_ROOT / "data"
    if pasta_gravavel(junto_ao_pacote):
        return junto_ao_pacote
    return data_dir_do_perfil()


def aviso_dados_anteriores(data_dir: Path) -> str | None:
    """Aponta a pasta das versões anteriores enquanto ela ainda guardar um banco."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if os.name != "nt" or not local_app_data:
        return None
    legado = Path(local_app_data).joinpath(*DADOS_LEGADOS).resolve()
    if legado == data_dir or not (legado / "app.sqlite3").is_file():
        return None
    return (
        f"Dados de versões anteriores continuam em {legado}. "
        f'Para voltar a usá-los, inicie com --dados "{legado}".'
    )


def check_package() -> None:
    required = (
        PACKAGE_ROOT / "frontend" / "dist" / "index.html",
        PACKAGE_ROOT / "engines" / "primary" / "executar_pipeline.py",
        PACKAGE_ROOT / "engines" / "scenarios" / "executar_cenario.py",
        PACKAGE_ROOT / "requirements.lock",
        PACKAGE_ROOT / "SBOM-python.cdx.json",
        PACKAGE_ROOT / "SBOM-frontend.cdx.json",
        PACKAGE_ROOT / "THIRD_PARTY_LICENSES.md",
        PACKAGE_ROOT / "THIRD_PARTY_LICENSES.json",
        PACKAGE_ROOT / "THIRD_PARTY_NOTICES.md",
        PACKAGE_ROOT / "MANIFESTO_RELEASE.json",
    )
    missing = [path.relative_to(PACKAGE_ROOT) for path in required if not path.is_file()]
    if missing:
        rendered = ", ".join(str(path) for path in missing)
        raise SystemExit(f"Pacote incompleto. Arquivos ausentes: {rendered}")
    supported_python = (
        sys.version_info.releaselevel == "final"
        and sys.version_info[:2] in {(3, 12), (3, 13)}
        and struct.calcsize("P") * 8 == 64
    )
    if not supported_python:
        raise SystemExit(
            "A versão 2.0 requer Python 64 bits estável 3.12 ou 3.13."
        )

    from scripts.integridade_release import verify

    verify()


def port_is_available(host: str, port: int) -> bool:
    bind_host = "127.0.0.1" if host in {"localhost", "0.0.0.0"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((bind_host, port))
        except OSError:
            return False
    return True


def open_when_ready(url: str) -> None:
    """Abre a aplicacao no navegador padrao assim que a API responde.

    O endereco leva um carimbo de abertura porque, com a URL identica a de uma
    sessao anterior, o navegador apenas devolve o foco a aba ja aberta e mantem
    a pagina antiga em memoria: quem acabou de atualizar a ferramenta continua
    vendo a versao anterior sem nenhum aviso.
    """
    health_url = f"{url}/api/health"
    separador = "&" if "?" in url else "?"
    endereco = f"{url}{separador}abertura={int(time.time())}"
    for _ in range(100):
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    webbrowser.open(endereco)
                    return
        except OSError:
            time.sleep(0.2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inicia a versão 2.0 da Ferramenta de Alocação Docente.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--porta", type=int, default=8000)
    parser.add_argument("--dados", type=Path, default=default_data_dir())
    parser.add_argument("--sem-navegador", action="store_true")
    parser.add_argument("--verificar", action="store_true", help="Valida o pacote sem iniciar o servidor.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    check_package()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit(
            "Por segurança, esta aplicação aceita somente --host 127.0.0.1 ou localhost."
        )
    data_dir = args.dados.expanduser().resolve()
    aviso = aviso_dados_anteriores(data_dir)
    if args.verificar:
        print(f"Versão {VERSION}: pacote íntegro; dados operacionais em {data_dir}")
        if aviso:
            print(aviso)
        return 0
    data_dir.mkdir(parents=True, exist_ok=True)
    os.environ["ALOCACAO_DATA_DIR"] = str(data_dir)
    if not port_is_available(args.host, args.porta):
        raise SystemExit(
            f"A porta {args.porta} já está em uso. Encerre a instância existente ou use --porta."
        )

    sys.path.insert(0, str(BACKEND_DIR))
    import uvicorn
    from app.main import create_app

    browser_host = "127.0.0.1" if args.host == "localhost" else args.host
    url = f"http://{browser_host}:{args.porta}"
    with DataDirectoryLock(data_dir):
        app = create_app()
        if not args.sem_navegador:
            threading.Thread(target=open_when_ready, args=(url,), daemon=True).start()

        print(f"Versão {VERSION} disponível em {url}")
        print(f"Dados operacionais: {data_dir}")
        if aviso:
            print(aviso)
        uvicorn.run(app, host=args.host, port=args.porta, reload=False, workers=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
