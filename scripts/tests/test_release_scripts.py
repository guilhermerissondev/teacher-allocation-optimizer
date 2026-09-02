from __future__ import annotations

import hashlib
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import unittest
import uuid
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch


APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from scripts import (  # noqa: E402
    backup_restore,
    bloqueio_dados,
    empacotar_release,
    integridade_release,
)
import executar  # noqa: E402
from executar import DataDirectoryLock  # noqa: E402


class WorkspaceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = (
            Path(__file__).resolve().parent / f".release-scripts-{uuid.uuid4().hex}"
        )
        self.workspace.mkdir()
        self.addCleanup(shutil.rmtree, self.workspace, True)


class BackupRestoreTests(WorkspaceTestCase):
    def make_data_dir(self) -> tuple[Path, Path]:
        data_dir = self.workspace / "dados-origem"
        data_dir.mkdir()
        outside = self.workspace / "dados-externos" / "preservar.xlsx"
        outside.parent.mkdir()
        outside.write_bytes(b"fora-do-backup")

        for relative, content in {
            "uploads/base.xlsx": b"planilha",
            "validacoes/relatorio.json": b"{}",
            "validacoes/inconsistencias.csv": b"codigo\n",
            "rodadas/rodada_001/resultado.json": b"{}",
            "cenarios/entrada.xlsx": b"cenario",
            "cenarios/alteracoes.json": b"{}",
        }.items():
            path = data_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        connection = sqlite3.connect(data_dir / "app.sqlite3")
        try:
            connection.executescript(
                """
                CREATE TABLE uploads (
                    id INTEGER PRIMARY KEY,
                    stored_path TEXT,
                    validation_path TEXT,
                    validation_csv_path TEXT
                );
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    round_dir TEXT
                );
                CREATE TABLE scenario_runs (
                    id INTEGER PRIMARY KEY,
                    input_path TEXT,
                    changes_path TEXT
                );
                """
            )
            connection.execute(
                "INSERT INTO uploads VALUES (1, ?, ?, ?)",
                (
                    str(data_dir / "uploads" / "base.xlsx"),
                    str(data_dir / "validacoes" / "relatorio.json"),
                    str(data_dir / "validacoes" / "inconsistencias.csv"),
                ),
            )
            connection.execute(
                "INSERT INTO uploads VALUES (2, ?, NULL, NULL)",
                (str(outside),),
            )
            connection.execute(
                "INSERT INTO jobs VALUES (1, ?)",
                (str(data_dir / "rodadas" / "rodada_001"),),
            )
            connection.execute(
                "INSERT INTO scenario_runs VALUES (1, ?, ?)",
                (
                    str(data_dir / "cenarios" / "entrada.xlsx"),
                    str(data_dir / "cenarios" / "alteracoes.json"),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return data_dir, outside

    @staticmethod
    def rewrite_zip(
        source: Path,
        destination: Path,
        transform,
    ) -> None:
        with zipfile.ZipFile(source) as original, zipfile.ZipFile(
            destination,
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as rewritten:
            for item in original.infolist():
                content = transform(item.filename, original.read(item))
                rewritten.writestr(item, content)

    def test_backup_restore_rebases_database_paths_and_preserves_external_paths(self):
        source, outside = self.make_data_dir()
        archive = self.workspace / "backup.zip"
        manifest = backup_restore.create_backup(source, archive)
        restored = self.workspace / "dados-restaurados"

        result = backup_restore.restore_backup(archive, restored)

        self.assertEqual(6, result["rebased_paths"])
        self.assertEqual(len(manifest["files"]), result["restored_files"])
        self.assertEqual(b"planilha", (restored / "uploads" / "base.xlsx").read_bytes())
        self.assertFalse((restored / "backup_manifest.json").exists())
        connection = sqlite3.connect(restored / "app.sqlite3")
        try:
            upload = connection.execute(
                "SELECT stored_path, validation_path, validation_csv_path "
                "FROM uploads WHERE id = 1"
            ).fetchone()
            external = connection.execute(
                "SELECT stored_path FROM uploads WHERE id = 2"
            ).fetchone()[0]
            round_dir = connection.execute("SELECT round_dir FROM jobs").fetchone()[0]
            scenario = connection.execute(
                "SELECT input_path, changes_path FROM scenario_runs"
            ).fetchone()
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(
            (
                str(restored / "uploads" / "base.xlsx"),
                str(restored / "validacoes" / "relatorio.json"),
                str(restored / "validacoes" / "inconsistencias.csv"),
            ),
            upload,
        )
        self.assertEqual(str(outside), external)
        self.assertEqual(str(restored / "rodadas" / "rodada_001"), round_dir)
        self.assertEqual(
            (
                str(restored / "cenarios" / "entrada.xlsx"),
                str(restored / "cenarios" / "alteracoes.json"),
            ),
            scenario,
        )
        self.assertEqual("ok", integrity)

    def test_restore_retries_transient_windows_permission_error(self):
        source, _ = self.make_data_dir()
        archive = self.workspace / "backup.zip"
        backup_restore.create_backup(source, archive)
        restored = self.workspace / "dados-restaurados"
        original_replace = Path.replace
        attempts = 0

        def replace_with_one_transient_failure(path: Path, target: Path) -> Path:
            nonlocal attempts
            if path.name == "payload":
                attempts += 1
                if attempts == 1:
                    raise PermissionError("bloqueio transitório simulado")
            return original_replace(path, target)

        with patch.object(Path, "replace", replace_with_one_transient_failure):
            result = backup_restore.restore_backup(archive, restored)

        self.assertEqual(2, attempts)
        self.assertEqual(b"planilha", (restored / "uploads" / "base.xlsx").read_bytes())
        self.assertGreater(result["restored_files"], 0)

    def test_create_backup_holds_application_lock_until_zip_is_published(self):
        source, _ = self.make_data_dir()
        archive = self.workspace / "backup.zip"
        original_writer = backup_restore._write_deterministic_zip
        lock_observed: list[bool] = []

        def assert_locked(staging, destination, *, reservation=None):
            lock = source / ".aplicacao.lock"
            lock_observed.append(
                lock.read_text(encoding="ascii").strip() == str(backup_restore.os.getpid())
            )
            with self.assertRaisesRegex(SystemExit, "Já existe uma instância"):
                with DataDirectoryLock(source):
                    self.fail("A aplicação não poderia adquirir o lock durante o backup.")
            with self.assertRaisesRegex(RuntimeError, "ainda está usando"):
                with backup_restore._reserve_application_stopped(source):
                    self.fail("Uma segunda reserva não poderia adquirir o lock.")
            return original_writer(staging, destination, reservation=reservation)

        with patch.object(
            backup_restore,
            "_write_deterministic_zip",
            side_effect=assert_locked,
        ):
            backup_restore.create_backup(source, archive)

        self.assertEqual([True], lock_observed)
        self.assertFalse((source / ".aplicacao.lock").exists())
        with DataDirectoryLock(source):
            self.assertTrue((source / ".aplicacao.lock").is_file())

    def test_create_backup_requires_explicit_overwrite(self):
        source, _ = self.make_data_dir()
        archive = self.workspace / "backup-existente.zip"
        archive.write_bytes(b"nao substituir")

        with self.assertRaisesRegex(FileExistsError, "--sobrescrever"):
            backup_restore.create_backup(source, archive)
        self.assertEqual(b"nao substituir", archive.read_bytes())

        backup_restore.create_backup(source, archive, overwrite=True)

        self.assertTrue(zipfile.is_zipfile(archive))
        with zipfile.ZipFile(archive) as backup:
            self.assertIn("backup_manifest.json", backup.namelist())

    def test_corrupted_payload_is_rejected_without_partial_restore(self):
        source, _ = self.make_data_dir()
        original = self.workspace / "backup-original.zip"
        corrupted = self.workspace / "backup-corrompido.zip"
        backup_restore.create_backup(source, original)
        self.rewrite_zip(
            original,
            corrupted,
            lambda name, content: content + b"corrompido"
            if name == "uploads/base.xlsx"
            else content,
        )
        restored = self.workspace / "destino-vazio"
        restored.mkdir()

        with self.assertRaisesRegex(ValueError, "Integridade inválida"):
            backup_restore.restore_backup(corrupted, restored)

        self.assertTrue(restored.is_dir())
        self.assertEqual([], list(restored.iterdir()))

    def test_corrupted_sqlite_with_updated_manifest_is_not_published(self):
        source, _ = self.make_data_dir()
        original = self.workspace / "backup-original.zip"
        corrupted = self.workspace / "backup-sqlite-corrompido.zip"
        backup_restore.create_backup(source, original)
        with zipfile.ZipFile(original) as archive:
            files = {item.filename: archive.read(item) for item in archive.infolist()}
        damaged_database = b"isto nao e um banco sqlite"
        files["app.sqlite3"] = damaged_database
        manifest = json.loads(files["backup_manifest.json"])
        database_entry = next(
            entry for entry in manifest["files"] if entry["caminho"] == "app.sqlite3"
        )
        database_entry["bytes"] = len(damaged_database)
        database_entry["sha256"] = hashlib.sha256(damaged_database).hexdigest()
        files["backup_manifest.json"] = (
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        with zipfile.ZipFile(corrupted, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        restored = self.workspace / "destino-vazio"
        restored.mkdir()

        with self.assertRaisesRegex(ValueError, "SQLite inválido"):
            backup_restore.restore_backup(corrupted, restored)

        self.assertTrue(restored.is_dir())
        self.assertEqual([], list(restored.iterdir()))

    def test_archive_path_traversal_is_rejected_before_extraction(self):
        for unsafe_name in ("../escape.txt", "..\\escape.txt", "/escape.txt", "C:/escape.txt"):
            with self.subTest(name=unsafe_name):
                archive_path = self.workspace / f"malicioso-{len(unsafe_name)}.zip"
                staging = self.workspace / f"staging-{len(unsafe_name)}"
                if archive_path.exists():
                    archive_path.unlink()
                if staging.exists():
                    shutil.rmtree(staging)
                staging.mkdir()
                with zipfile.ZipFile(archive_path, "w") as archive:
                    archive.writestr(unsafe_name, b"nao extrair")

                with self.assertRaisesRegex(ValueError, "inseguro"):
                    backup_restore._extract_and_verify(archive_path, staging)

                self.assertEqual([], list(staging.iterdir()))
                self.assertFalse((staging.parent / "escape.txt").exists())

    def test_duplicate_archive_members_are_rejected_case_insensitively(self):
        for first, second in (("duplicado.txt", "duplicado.txt"), ("Arquivo.txt", "arquivo.TXT")):
            with self.subTest(first=first, second=second):
                archive_path = self.workspace / f"duplicado-{first[0]}.zip"
                staging = self.workspace / f"staging-duplicado-{first[0]}"
                archive_path.unlink(missing_ok=True)
                if staging.exists():
                    shutil.rmtree(staging)
                staging.mkdir()
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    with zipfile.ZipFile(archive_path, "w") as archive:
                        archive.writestr(first, b"primeiro")
                        archive.writestr(second, b"segundo")

                with self.assertRaisesRegex(ValueError, "duplicada"):
                    backup_restore._extract_and_verify(archive_path, staging)

    def test_duplicate_manifest_entries_and_missing_database_are_rejected(self):
        payload = b"conteudo"
        entry = {
            "caminho": "uploads/base.xlsx",
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        base_manifest = {
            "schema_version": backup_restore.BACKUP_SCHEMA_VERSION,
            "app_version": backup_restore.VERSION,
            "source_data_dir": str((self.workspace / "origem").resolve()),
            "files": [entry],
        }
        missing_database = self.workspace / "sem-banco.zip"
        with zipfile.ZipFile(missing_database, "w") as archive:
            archive.writestr("uploads/base.xlsx", payload)
            archive.writestr("backup_manifest.json", json.dumps(base_manifest))
        with self.assertRaisesRegex(ValueError, "app.sqlite3 ausente"):
            backup_restore.restore_backup(
                missing_database,
                self.workspace / "restauracao-sem-banco",
            )

        source, _ = self.make_data_dir()
        original = self.workspace / "backup-original.zip"
        duplicate = self.workspace / "manifesto-duplicado.zip"
        backup_restore.create_backup(source, original)

        def duplicate_entry(name: str, content: bytes) -> bytes:
            if name != "backup_manifest.json":
                return content
            manifest = json.loads(content)
            manifest["files"].append(dict(manifest["files"][0]))
            return json.dumps(manifest).encode("utf-8")

        self.rewrite_zip(original, duplicate, duplicate_entry)
        staging = self.workspace / "staging-manifesto-duplicado"
        staging.mkdir()
        with self.assertRaisesRegex(ValueError, "duplicada ou inválida"):
            backup_restore._extract_and_verify(duplicate, staging)


class IntegrityAndPackagingTests(WorkspaceTestCase):
    def make_release_root(self) -> Path:
        root = self.workspace / "release-root"
        root.mkdir()
        files = {
            "VERSION": b"9.8.7-test\n",
            "aplicacao.py": b"print('ok')\n",
            "config/opcoes.json": b"{}\n",
            "data/README.md": b"dados locais\n",
            "data/.gitkeep": b"",
            "data/app.sqlite3": b"nao empacotar",
            "data/uploads/privado.xlsx": b"nao empacotar",
            "engines/primary/resultados/rodada.json": b"nao empacotar",
            "node_modules/pacote/index.js": b"nao empacotar",
            "release/antiga.zip": b"nao empacotar",
            "scripts/tests/.release-scripts-residuo/privado.xlsx": b"nao empacotar",
        }
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        return root

    def test_manifest_generate_and_verify_are_isolated_from_current_release(self):
        root = self.make_release_root()

        generated = integridade_release.generate(root=root)
        verified = integridade_release.verify(root=root)

        self.assertEqual(generated, verified)
        paths = {entry["caminho"] for entry in generated["arquivos"]}
        self.assertEqual(
            {
                "VERSION",
                "aplicacao.py",
                "config/opcoes.json",
                "data/.gitkeep",
                "data/README.md",
            },
            paths,
        )
        self.assertEqual(len(paths), generated["total_arquivos"])
        self.assertTrue((root / "MANIFESTO_RELEASE.json").is_file())

    def test_release_script_clis_run_by_absolute_path_from_another_directory(self):
        for script in (
            "backup_restore.py",
            "integridade_release.py",
            "empacotar_release.py",
        ):
            with self.subTest(script=script):
                help_arguments = (
                    ["backup", "--help"]
                    if script == "backup_restore.py"
                    else ["--help"]
                )
                completed = subprocess.run(
                    [
                        sys.executable,
                        str(APP_ROOT / "scripts" / script),
                        *help_arguments,
                    ],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(0, completed.returncode, completed.stderr)
                if script == "backup_restore.py":
                    self.assertIn("--sobrescrever", completed.stdout)

    def test_manifest_detects_changed_file(self):
        root = self.make_release_root()
        integridade_release.generate(root=root)
        (root / "aplicacao.py").write_bytes(b"alterado\n")

        with self.assertRaisesRegex(SystemExit, "alterados"):
            integridade_release.verify(root=root)

    def test_manifest_rejects_traversal_duplicates_and_malformed_json(self):
        root = self.make_release_root()
        manifest_path = root / "MANIFESTO_RELEASE.json"
        original = integridade_release.generate(root=root)

        traversal = json.loads(json.dumps(original))
        traversal["arquivos"][0]["caminho"] = "..\\escape.txt"
        manifest_path.write_text(json.dumps(traversal), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "inválidos ou duplicados"):
            integridade_release.verify(root=root)

        duplicate = json.loads(json.dumps(original))
        duplicate_entry = dict(duplicate["arquivos"][0])
        duplicate_entry["caminho"] = str(duplicate_entry["caminho"]).upper()
        duplicate["arquivos"].append(duplicate_entry)
        manifest_path.write_text(json.dumps(duplicate), encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "inválidos ou duplicados"):
            integridade_release.verify(root=root)

        manifest_path.write_text("{manifesto quebrado", encoding="utf-8")
        with self.assertRaisesRegex(SystemExit, "manifesto ilegível"):
            integridade_release.verify(root=root)

    def test_package_is_deterministic_complete_and_uses_isolated_manifest(self):
        root = self.make_release_root()
        payload = integridade_release.generate(root=root)
        output = self.workspace / "pacotes"

        archive, checksum, digest = empacotar_release.package_release(
            output,
            root=root,
        )
        first_bytes = archive.read_bytes()
        second_archive, second_checksum, second_digest = empacotar_release.package_release(
            output,
            root=root,
        )

        self.assertEqual(archive, second_archive)
        self.assertEqual(checksum, second_checksum)
        self.assertEqual(digest, second_digest)
        self.assertEqual(first_bytes, second_archive.read_bytes())
        self.assertEqual(hashlib.sha256(first_bytes).hexdigest(), digest)
        self.assertEqual(f"{digest}  {archive.name}\n", checksum.read_text(encoding="ascii"))
        with zipfile.ZipFile(archive) as packaged:
            names = packaged.namelist()
            self.assertEqual(len(names), len(set(name.casefold() for name in names)))
            self.assertEqual(
                sorted(
                    [entry["caminho"] for entry in payload["arquivos"]]
                    + ["MANIFESTO_RELEASE.json"],
                    key=str.casefold,
                ),
                names,
            )
            self.assertTrue(
                all(item.date_time == (2020, 1, 1, 0, 0, 0) for item in packaged.infolist())
            )
            self.assertIsNone(packaged.testzip())
            self.assertNotIn("data/app.sqlite3", names)
            self.assertNotIn("data/uploads/privado.xlsx", names)

    def test_package_detects_source_change_after_initial_verification(self):
        root = self.make_release_root()
        integridade_release.generate(root=root)
        original_verify = empacotar_release.verify

        def verify_then_change(**kwargs):
            payload = original_verify(**kwargs)
            (root / "aplicacao.py").write_bytes(b"mudou durante o pacote\n")
            return payload

        with patch.object(empacotar_release, "verify", side_effect=verify_then_change):
            with self.assertRaisesRegex(RuntimeError, "mudou durante o empacotamento"):
                empacotar_release.package_release(self.workspace / "pacotes", root=root)

    def test_package_rejects_unsafe_version_and_cleans_temporary_zip(self):
        root = self.make_release_root()
        (root / "VERSION").write_text("../fora\n", encoding="utf-8")
        integridade_release.generate(root=root)
        output = self.workspace / "pacotes"

        with self.assertRaisesRegex(ValueError, "Versão insegura"):
            empacotar_release.package_release(output, root=root)

        (root / "VERSION").write_text("9.8.7-test\n", encoding="utf-8")
        integridade_release.generate(root=root)
        with patch.object(zipfile.ZipFile, "writestr", side_effect=OSError("falha simulada")):
            with self.assertRaisesRegex(OSError, "falha simulada"):
                empacotar_release.package_release(output, root=root)
        self.assertEqual([], list(output.glob("*.tmp")))

        with self.assertRaisesRegex(ValueError, "saída deve ficar sob release"):
            empacotar_release.package_release(root, root=root)


class DiretorioOperacionalPadraoTests(WorkspaceTestCase):
    def test_padrao_e_a_pasta_data_de_onde_a_aplicacao_foi_aberta(self):
        with patch.dict(os.environ):
            os.environ.pop("ALOCACAO_DATA_DIR", None)
            self.assertEqual(executar.PACKAGE_ROOT / "data", executar.default_data_dir())

    def test_variavel_de_ambiente_tem_prioridade(self):
        destino = self.workspace / "dados-escolhidos"
        with patch.dict(os.environ, {"ALOCACAO_DATA_DIR": str(destino)}):
            self.assertEqual(destino.resolve(), executar.default_data_dir())

    def test_pasta_somente_leitura_cai_para_o_perfil_na_versao_atual(self):
        perfil = self.workspace / "perfil"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(perfil)}):
            os.environ.pop("ALOCACAO_DATA_DIR", None)
            with patch.object(executar, "pasta_gravavel", return_value=False):
                destino = executar.default_data_dir()
        esperado = perfil / "Institution" / "AlocacaoDocente" / f"v{executar.VERSION}"
        self.assertEqual(esperado, destino)

    def test_pasta_gravavel_avalia_sem_criar_a_pasta(self):
        candidata = self.workspace / "ainda-nao-existe" / "data"
        self.assertTrue(executar.pasta_gravavel(candidata))
        self.assertFalse(candidata.exists())

    def test_pasta_gravavel_reprova_quando_a_escrita_falha(self):
        with patch.object(
            executar.tempfile, "TemporaryFile", side_effect=OSError("somente leitura")
        ):
            self.assertFalse(executar.pasta_gravavel(self.workspace))

    def test_aviso_aponta_os_dados_das_versoes_anteriores(self):
        perfil = self.workspace / "perfil"
        legado = perfil.joinpath(*executar.DADOS_LEGADOS)
        legado.mkdir(parents=True)
        (legado / "app.sqlite3").write_bytes(b"")
        with patch.dict(os.environ, {"LOCALAPPDATA": str(perfil)}):
            aviso = executar.aviso_dados_anteriores(self.workspace / "data")
        self.assertIsNotNone(aviso)
        self.assertIn(str(legado.resolve()), aviso)

    def test_sem_banco_antigo_nao_ha_aviso(self):
        perfil = self.workspace / "perfil-vazio"
        with patch.dict(os.environ, {"LOCALAPPDATA": str(perfil)}):
            self.assertIsNone(executar.aviso_dados_anteriores(self.workspace / "data"))


class BloqueioDoDiretorioDeDadosTests(WorkspaceTestCase):
    """Regressão: o bloqueio precisa vir do sistema, não de um PID em arquivo.

    Um encerramento abrupto deixa o arquivo para trás. Quando o sistema
    reciclava aquele PID, a checagem antiga concluía que havia instância viva e
    a aplicação recusava abrir com código 1.
    """

    def make_data_dir(self) -> Path:
        data_dir = self.workspace / "dados"
        data_dir.mkdir()
        return data_dir

    def start_holder(self, data_dir: Path) -> tuple[subprocess.Popen, int]:
        """Sobe um processo que segura o bloqueio até ser morto.

        Devolve também o PID que o interpretador anunciou: em ambientes cujo
        ``python.exe`` do .venv é apenas um lançador, ele não coincide com o
        PID devolvido por ``Popen``, e é o anunciado que grava o bloqueio.
        """
        program = self.workspace / f"segurar-{uuid.uuid4().hex}.py"
        program.write_text(
            "\n".join(
                (
                    "import os, sys, time",
                    f"sys.path.insert(0, {str(APP_ROOT)!r})",
                    "from pathlib import Path",
                    "from executar import DataDirectoryLock",
                    f"with DataDirectoryLock(Path({str(data_dir)!r})):",
                    "    print(os.getpid(), flush=True)",
                    "    time.sleep(120)",
                )
            ),
            encoding="utf-8",
        )
        holder = subprocess.Popen(
            [sys.executable, str(program)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        pid: int | None = None
        # A limpeza fecha sobre pid para alcançar o interpretador anunciado
        # assim que ele for conhecido; matar só o lançador deixaria o dono do
        # bloqueio vivo e o diretório de trabalho preso.
        self.addCleanup(lambda: self.kill_holder(holder, pid))
        announced = holder.stdout.readline().strip()
        self.assertRegex(announced, r"^\d+$", "O processo não chegou a reservar o bloqueio.")
        pid = int(announced)
        return holder, pid

    def kill_holder(self, holder: subprocess.Popen, pid: int | None) -> None:
        """Encerra o processo de forma abrupta, sem passar pelo __exit__."""
        if pid is not None:
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        holder.kill()
        holder.wait(timeout=30)
        for stream in (holder.stdout, holder.stderr):
            if stream is not None:
                stream.close()

    def test_arquivo_orfao_com_pid_vivo_nao_impede_a_abertura(self):
        data_dir = self.make_data_dir()
        lock = bloqueio_dados.lock_path(data_dir)
        # O PID deste próprio processo é o pior caso: está inegavelmente vivo,
        # como ficava o PID reciclado, mas ninguém detém a reserva.
        lock.write_text(str(os.getpid()), encoding="ascii")

        with DataDirectoryLock(data_dir):
            self.assertEqual(str(os.getpid()), lock.read_text(encoding="ascii").strip())
        self.assertFalse(lock.exists())

    def test_arquivo_orfao_ilegivel_nao_impede_a_abertura(self):
        data_dir = self.make_data_dir()
        lock = bloqueio_dados.lock_path(data_dir)
        lock.write_bytes(b"nao-e-um-pid")

        with DataDirectoryLock(data_dir):
            self.assertTrue(lock.is_file())

    def test_instancia_viva_impede_a_segunda_abertura(self):
        data_dir = self.make_data_dir()
        _, pid = self.start_holder(data_dir)

        with self.assertRaisesRegex(SystemExit, f"Já existe uma instância.*PID {pid}"):
            with DataDirectoryLock(data_dir):
                self.fail("A segunda instância não poderia reservar o diretório.")

        lock = bloqueio_dados.lock_path(data_dir)
        self.assertEqual(str(pid), lock.read_text(encoding="ascii").strip())

    def test_morte_do_processo_devolve_o_bloqueio_mesmo_com_o_arquivo_no_lugar(self):
        data_dir = self.make_data_dir()
        holder, pid = self.start_holder(data_dir)
        lock = bloqueio_dados.lock_path(data_dir)

        self.kill_holder(holder, pid)

        # É este o estado que quebrava a abertura: arquivo presente, com o PID
        # de uma execução encerrada de forma abrupta.
        self.assertTrue(lock.is_file())
        self.assertEqual(str(pid), lock.read_text(encoding="ascii").strip())
        self.assertIsNone(bloqueio_dados.owner_pid(data_dir))
        with DataDirectoryLock(data_dir):
            self.assertEqual(str(os.getpid()), lock.read_text(encoding="ascii").strip())

    def test_ensure_application_stopped_ignora_arquivo_orfao(self):
        data_dir = self.make_data_dir()
        bloqueio_dados.lock_path(data_dir).write_text(str(os.getpid()), encoding="ascii")

        backup_restore.ensure_application_stopped(data_dir)

    def test_ensure_application_stopped_recusa_com_a_aplicacao_viva(self):
        data_dir = self.make_data_dir()
        _, pid = self.start_holder(data_dir)

        with self.assertRaisesRegex(RuntimeError, f"ainda está usando.*PID {pid}"):
            backup_restore.ensure_application_stopped(data_dir)
        self.assertEqual(pid, bloqueio_dados.owner_pid(data_dir))

    def test_ensure_application_stopped_nao_cria_o_arquivo_de_bloqueio(self):
        data_dir = self.make_data_dir()

        backup_restore.ensure_application_stopped(data_dir)

        # A restauração exige o destino vazio logo depois desta checagem.
        self.assertEqual([], list(data_dir.iterdir()))

if __name__ == "__main__":
    unittest.main()
