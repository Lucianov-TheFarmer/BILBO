import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.backend.pipeline_rag import admin


class Response:
    def __init__(self, payload=None, content=b""):
        self.payload = payload or {}
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class RagAdminTest(unittest.TestCase):
    def test_export_writes_snapshot_bm25_and_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bm25 = root / "source-bm25.json"
            bm25.write_text(json.dumps({"doc_count": 2}), encoding="utf-8")
            responses = [
                Response({"status": "ok", "result": {"name": "index.snapshot"}}),
                Response({"status": "ok", "result": {"count": 2}}),
            ]
            with patch.object(admin.requests, "request", side_effect=responses), patch.object(
                admin.requests, "get", return_value=Response(content=b"snapshot-data")
            ):
                destination = admin.export_collection(
                    root / "export", qdrant_url="http://qdrant:6333", bm25_path=bm25
                )

            manifest = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(2, manifest["point_count"])
            self.assertEqual("index.snapshot", manifest["snapshot"]["file"])
            self.assertEqual(
                hashlib.sha256(b"snapshot-data").hexdigest(), manifest["snapshot"]["sha256"]
            )

    def test_import_checks_files_restores_then_installs_bm25(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "export"
            source.mkdir()
            snapshot = source / "index.snapshot"
            bm25 = source / "bm25_metadata.json"
            snapshot.write_bytes(b"snapshot-data")
            bm25.write_text(json.dumps({"doc_count": 2}), encoding="utf-8")
            manifest = {
                "format_version": 1,
                "collection_name": "literature",
                "point_count": 2,
                "snapshot": {"file": snapshot.name, "sha256": admin._sha256(snapshot)},
                "bm25": {"file": bm25.name, "sha256": admin._sha256(bm25)},
            }
            (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            post = Mock(return_value=Response({"status": "ok"}))
            count = Response({"status": "ok", "result": {"count": 2}})
            destination_bm25 = root / "runtime" / "bm25_metadata.json"

            with patch.object(admin.requests, "post", post), patch.object(
                admin.requests, "request", return_value=count
            ):
                target = admin.import_collection(
                    source, qdrant_url="http://qdrant:6333", bm25_path=destination_bm25
                )

            self.assertEqual("literature", target)
            self.assertEqual(bm25.read_bytes(), destination_bm25.read_bytes())
            self.assertIn("priority=snapshot", post.call_args.args[0])

    def test_import_rejects_modified_export(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "index.snapshot").write_bytes(b"modified")
            (source / "bm25_metadata.json").write_text("{}", encoding="utf-8")
            manifest = {
                "format_version": 1,
                "collection_name": "literature",
                "point_count": 1,
                "snapshot": {"file": "index.snapshot", "sha256": "invalid"},
                "bm25": {"file": "bm25_metadata.json", "sha256": "invalid"},
            }
            (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Checksum invalido"):
                admin.import_collection(source)


if __name__ == "__main__":
    unittest.main()
