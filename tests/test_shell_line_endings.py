"""Shell scripts copied to the Linux server must have Unix line endings."""

import unittest
from pathlib import Path


class ShellLineEndingsTest(unittest.TestCase):
    def test_linux_shell_scripts_have_no_crlf(self):
        root = Path(__file__).resolve().parents[1] / "app" / "backend" / "scripts"
        files = list(root.glob("*.sh"))
        self.assertTrue(files)
        for path in files:
            with self.subTest(path=path.name):
                self.assertNotIn(b"\r\n", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
