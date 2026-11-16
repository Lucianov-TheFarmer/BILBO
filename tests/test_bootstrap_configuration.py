"""The first-run configuration must be private and preserve user changes."""

import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

import init
from app.backend.services import rag_bootstrap
from app.frontend.procedures.urls import public_url


class BootstrapConfigurationTest(unittest.TestCase):
    def test_env_generation_preserves_port_and_secrets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = root / ".env.example"
            example.write_text(init.EXAMPLE_FILE.read_text(encoding="utf-8").replace(
                "BILBO_HOST_PORT=8890", "BILBO_HOST_PORT=9001"), encoding="utf-8")
            with patch.object(init, "ENV_FILE", root / ".env"), \
                 patch.object(init, "EXAMPLE_FILE", example):
                first = init.prepare_env()
                init.validate_env(first)
                second = init.prepare_env()
                self.assertEqual("9001", first["BILBO_HOST_PORT"])
                self.assertEqual(first["SECRET_KEY"], second["SECRET_KEY"])
                self.assertEqual(first["POSTGRES_PASSWORD"], second["POSTGRES_PASSWORD"])
                self.assertNotIn("SECRET_KEY=\n", (root / ".env").read_text())

    def test_browser_urls_follow_host_port(self):
        with patch.dict("os.environ", {"BILBO_HOST_PORT": "9001", "BILBO_PUBLIC_BASE_URL": ""}):
            self.assertEqual(
                "http://localhost:9001/results/download?file=x",
                public_url("http://localhost:8890/results/download?file=x"),
            )
        with patch.dict("os.environ", {"BILBO_PUBLIC_BASE_URL": "https://bilbo.example.org/"}):
            self.assertEqual(
                "https://bilbo.example.org/results/download?file=x",
                public_url("http://localhost:8890/results/download?file=x"),
            )

    def test_check_mode_does_not_start_containers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            example = root / ".env.example"
            example.write_text(init.EXAMPLE_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            with patch.object(init, "ENV_FILE", root / ".env"), \
                 patch.object(init, "EXAMPLE_FILE", example), \
                 patch.object(init, "docker") as docker, \
                 patch.object(sys, "argv", ["init.py", "--check"]):
                self.assertEqual(0, init.main())
                self.assertEqual(
                    [("compose", "version"), ("info", "--format", "{{.ServerVersion}}"),
                     ("compose", "config", "--quiet")],
                    [call.args for call in docker.call_args_list],
                )

    def test_index_bootstrap_can_start_while_models_download(self):
        with patch.object(rag_bootstrap, "_original_ensure_rag_database", return_value={"ready": True}) as restore:
            self.assertEqual({"ready": True}, rag_bootstrap.ensure_rag_database(ensure_models=False))
            restore.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
