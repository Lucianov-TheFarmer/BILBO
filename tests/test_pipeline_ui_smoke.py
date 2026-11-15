"""Build the pipeline and design dialogs with the deployed Flet version."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from frontend.procedures import contrasts, pipeline_config  # noqa: E402


class _Page:
    def __init__(self, language):
        self.session = {"lang": language}
        self.opened = []

    def open(self, control):
        self.opened.append(control)

    def update(self):
        pass

    def run_task(self, *_args):
        pass


class _Client:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def get(self, url, **_kwargs):
        if url.endswith("/pipeline/options"):
            data = {"samples": {"A1": [{"name": "A1_1.fastq.gz", "status": "COMPLETED"},
                                        {"name": "A1_2.fastq.gz", "status": "COMPLETED"}],
                                "B1": [{"name": "B1_1.fastq.gz", "status": "PENDING"}]},
                    "genomes": [{"id": "ref1", "name": "Reference", "status": "COMPLETED"}]}
        elif url.endswith("/analysis-design/context"):
            data = {"samples": {"A1": "Control", "B1": "Drought"},
                    "contrasts": [{"id": 1, "name": "Drought(B1)*Control(A1)",
                                   "positive": {"samples": ["B1"]},
                                   "negative": {"samples": ["A1"]}}]}
        elif url.endswith("/contrasts/"):
            data = [{"id": 1, "name": "Drought(B1)*Control(A1)"}]
        else:
            data = {"config": {"contrast_ids": [1], "variables": [{
                "name": "block", "kind": "categorical",
                "values": {"A1": "one", "B1": "one"}}]}}
        return SimpleNamespace(status_code=200, json=lambda: data)

    async def post(self, url, **_kwargs):
        if url.endswith("/analysis-design/validate"):
            return SimpleNamespace(status_code=200, json=lambda: {
                "samples": {"A1": "Control", "B1": "Drought"}})
        raise AssertionError(url)


class PipelineUISmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_dialogs_build_in_all_languages(self):
        for language in ("pt", "en", "es"):
            page = _Page(language)
            with patch.object(pipeline_config.httpx, "AsyncClient", return_value=_Client()):
                await pipeline_config.show_pipeline_config_modal(page, "test-token", 7)
                await contrasts.show_contrasts_modal(page, "test-token", 7)
            self.assertEqual(2, len(page.opened))
            sample_choices = page.opened[0].content.content.controls[7]
            self.assertEqual([True, True], [choice.value for choice in sample_choices.controls])
            shared_reference = next(control for control in page.opened[0].content.content.controls
                                    if isinstance(control, ft.Container)
                                    and isinstance(control.content, ft.Column)
                                    and isinstance(control.content.controls[0], ft.Text)
                                    and control.content.controls[0].value in
                                    ("Genoma de referência", "Reference genome", "Genoma de referencia"))
            self.assertEqual("ref1", shared_reference.content.controls[1].controls[0].value)


if __name__ == "__main__":
    unittest.main()
