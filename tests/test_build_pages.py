import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_pages.py"
SPEC = importlib.util.spec_from_file_location("build_pages", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PagesBuildTests(unittest.TestCase):
    def test_publishes_only_modules_resources_readme_and_index(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = root / "Modules" / "Surge"
            resources = modules / "_resources" / "source"
            resources.mkdir(parents=True)
            (modules / "Bilibili.sgmodule").write_text("module", encoding="utf-8")
            (resources / "runtime.js").write_text("script", encoding="utf-8")
            (modules / ".generated-manifest.json").write_text("{}", encoding="utf-8")
            readme = root / "README.md"
            readme.write_text("README", encoding="utf-8")
            site = root / "_site"

            MODULE.build_pages(modules, readme, site)

            self.assertTrue((site / "Modules/Surge/Bilibili.sgmodule").is_file())
            self.assertTrue((site / "Modules/Surge/_resources/source/runtime.js").is_file())
            self.assertFalse((site / "Modules/Surge/.generated-manifest.json").exists())
            self.assertEqual((site / "README.md").read_text(encoding="utf-8"), "README")
            self.assertTrue((site / ".nojekyll").is_file())
            self.assertTrue((site / "Modules/Surge/install.html").is_file())
            index = (site / "index.html").read_text(encoding="utf-8")
            self.assertIn("Modules/Surge/Bilibili.sgmodule", index)

    def test_fails_without_modules(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            modules = root / "Modules" / "Surge"
            modules.mkdir(parents=True)
            readme = root / "README.md"
            readme.write_text("README", encoding="utf-8")
            with self.assertRaises(MODULE.PagesBuildError):
                MODULE.build_pages(modules, readme, root / "_site")


if __name__ == "__main__":
    unittest.main()
