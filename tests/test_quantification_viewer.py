"""HTSeq counts are read in bounded chunks and remain user scoped."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from backend.db.database import Base  # noqa: E402
from backend.db.models import SampleStage, Stage, User  # noqa: E402
from backend.routes.quantification import read_counts_chunk, download_counts  # noqa: E402
from frontend.procedures.quantification import create_tabela_quantificacao, update_tabela_quantificacao  # noqa: E402
from frontend.procedures.viewer import view_quantification_counts, view_quantification_log  # noqa: E402


class QuantificationFilesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()
        self.db.add(User(id=7, username="counts-test", hashed_password="test"))
        self.db.add(Stage(id=6, name="quantification"))
        self.db.add(SampleStage(user_id=7, stage_id=6, name="sample.txt", status="COMPLETED"))
        self.db.commit()
        self.user = self.db.get(User, 7)
        directory = Path(self.temporary.name) / "7" / "quantification"
        directory.mkdir(parents=True)
        (directory / "sample.txt").write_bytes(b"gene1\t10\ngene2\t20\ngene3\t30\n")

    def tearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temporary.cleanup()

    def test_chunks_continue_from_byte_offset(self):
        with patch("backend.routes.quantification.settings", SimpleNamespace(users_root=self.temporary.name)):
            first = read_counts_chunk("sample.txt", 0, 1, self.db, self.user)
            second = read_counts_chunk("sample.txt", first["next_offset"], 2, self.db, self.user)
        self.assertEqual(["gene1\t10"], first["lines"])
        self.assertEqual(["gene2\t20", "gene3\t30"], second["lines"])
        self.assertFalse(second["has_more"])

    def test_download_requires_owned_completed_result(self):
        with patch("backend.routes.quantification.settings", SimpleNamespace(users_root=self.temporary.name)):
            response = download_counts("sample.txt", self.db, self.user)
            self.assertEqual("sample.txt", response.filename)
            with self.assertRaises(HTTPException):
                download_counts("other.txt", self.db, self.user)


class QuantificationViewerTest(unittest.IsolatedAsyncioTestCase):
    async def test_completed_sample_has_log_view_and_download_actions(self):
        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, *_args, **_kwargs):
                return SimpleNamespace(status_code=200, json=lambda: [{
                    "name": "sample.txt", "size": "2 KB", "status": "COMPLETED"}])

        page = SimpleNamespace(session={"lang": "en"}, update=lambda: None)
        table = create_tabela_quantificacao(page, "token")
        with patch("frontend.procedures.quantification.httpx.AsyncClient", return_value=Client()):
            await update_tabela_quantificacao(page, "token", 7)
        actions = table.rows[0].cells[3].content.controls
        self.assertEqual(["View log", "View counts", "Download counts"],
                         [button.tooltip for button in actions])
        self.assertTrue(all(not button.disabled for button in actions))

    async def test_scroll_loads_next_chunk_without_reading_whole_file(self):
        calls = []

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_args):
                return False

            async def get(self, _url, **kwargs):
                calls.append(kwargs["params"]["offset"])
                first = {"lines": ["gene1\t10"], "next_offset": 9,
                         "size": 18, "has_more": True}
                last = {"lines": ["gene2\t20"], "next_offset": 18,
                        "size": 18, "has_more": False}
                return SimpleNamespace(status_code=200, json=lambda: first if len(calls) == 1 else last)

        preview = ft.Container(content=ft.Column([ft.Text("previous")]))
        page = SimpleNamespace(container_preview=preview, session={"lang": "en"}, update=lambda: None)
        with patch("frontend.procedures.viewer.httpx.AsyncClient", return_value=Client()):
            await view_quantification_counts(page, "token", "sample.txt")
            rows = preview.content.controls[0].content.controls[1]
            self.assertEqual([0], calls)
            await rows.on_scroll(SimpleNamespace(pixels=100, max_scroll_extent=200))
        self.assertEqual([0, 9], calls)
        self.assertEqual(3, len(rows.controls))
        self.assertFalse(rows.controls[-1].visible)

    async def test_missing_historical_log_has_clear_message(self):
        preview = ft.Container(content=ft.Column([]))
        page = SimpleNamespace(container_preview=preview, session={"lang": "en"}, update=lambda: None)
        with patch("frontend.procedures.viewer.os.path.exists", return_value=False):
            await view_quantification_log(page, "token", "sample.txt", 7)
        text = preview.content.controls[0].content.controls[1].controls[0].value
        self.assertIn("not saved", text)


if __name__ == "__main__":
    unittest.main()
