"""Build the pipeline and design dialogs with the deployed Flet version."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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


class PipelineUISmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_dialogs_build_in_all_languages(self):
        for language in ("pt", "en", "es"):
            page = _Page(language)
            with patch.object(pipeline_config.httpx, "AsyncClient", return_value=_Client()):
                await pipeline_config.show_pipeline_config_modal(page, "test-token", 7)
                await contrasts.show_contrasts_modal(page, "test-token", 7)
            self.assertEqual(2, len(page.opened))


if __name__ == "__main__":
    unittest.main()
