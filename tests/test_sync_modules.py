import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_modules.py"
SPEC = importlib.util.spec_from_file_location("sync_modules", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class BundleMergeTests(unittest.TestCase):
    def source(self, source_id, content):
        return MODULE.SourceResult(
            source_id=source_id,
            provider="provider",
            source_url=f"https://example.com/{source_id}.sgmodule",
            output="Bundle.sgmodule",
            bundle="bundle",
            content=content,
        )

    def test_merges_sections_and_exact_duplicates_only(self):
        first = self.source(
            "first",
            """#!name=First
#!arguments=first:true
[Rule]
DOMAIN,ads.example.com,REJECT
[MITM]
hostname = %APPEND% api.example.com
""",
        )
        second = self.source(
            "second",
            """#!name=Second
#!arguments=second:false
[Rule]
DOMAIN,ads.example.com,REJECT
DOMAIN-SUFFIX,example.net,REJECT
[MITM]
hostname = %APPEND% api.example.com, second.example.com
""",
        )
        merged = MODULE.merge_bundle(
            [first, second],
            {"description": "Bundle", "module": "Bundle.sgmodule"},
        )
        self.assertEqual(merged.count("DOMAIN,ads.example.com,REJECT"), 1)
        self.assertIn("DOMAIN-SUFFIX,example.net,REJECT", merged)
        self.assertIn("#!arguments=first:true,second:false", merged)
        self.assertIn("hostname = %APPEND% api.example.com, second.example.com", merged)

    def test_conflicting_arguments_fail(self):
        first = self.source("first", "#!arguments=flag:true\n[Rule]\nDOMAIN,a.example,REJECT\n")
        second = self.source("second", "#!arguments=flag:false\n[Rule]\nDOMAIN,b.example,REJECT\n")
        with self.assertRaises(MODULE.SyncError):
            MODULE.merge_bundle([first, second], {"description": "Bundle"})


class OutputResolutionTests(unittest.TestCase):
    def test_prefix_routes_source_to_bundle(self):
        output, bundle = MODULE.resolve_output(
            "app",
            {"module": "Family/App.sgmodule"},
            {"family": {"module": "Family.sgmodule", "source_prefixes": ["Family/"]}},
        )
        self.assertEqual(output, "Family.sgmodule")
        self.assertEqual(bundle, "family")

    def test_bilibili_and_youtube_remain_standalone(self):
        bundles = {"video": {"module": "Video.sgmodule"}}
        for source_id, module in (
            ("bilibili", "Bilibili.sgmodule"),
            ("youtube", "YouTube.sgmodule"),
        ):
            output, bundle = MODULE.resolve_output(source_id, {"module": module}, bundles)
            self.assertEqual(output, module)
            self.assertIsNone(bundle)


class ConverterRequestTests(unittest.TestCase):
    def test_loon_user_agent_spaces_are_percent_encoded(self):
        app = {
            "format": "loon",
            "provider": "Kelee",
            "url": "https://kelee.one/Tool/Loon/Plugin/Test.lpx",
        }
        url = MODULE.converter_url(
            "http://127.0.0.1:9100",
            app["url"],
            "test",
            app,
        )
        self.assertIn("Loon%2F861%20CFNetwork%2F1496.0.7%20Darwin%2F23.5.0", url)
        self.assertNotIn("Loon%2F861+CFNetwork", url)
        self.assertIn("nocache=true", url)


class ModuleCategoryTests(unittest.TestCase):
    def test_replaces_existing_category_and_removes_duplicates(self):
        content = "#!name=Example\n#!category=Old\n#!category=Other\n[Rule]\nDOMAIN,a.example,REJECT\n"
        updated = MODULE.set_module_category(content)
        self.assertEqual(updated.count("#!category="), 1)
        self.assertIn("#!category=AdBlock", updated)
        self.assertNotIn("#!category=Old", updated)

    def test_inserts_category_after_name(self):
        content = "#!name=Example\n#!desc=Description\n[Rule]\nDOMAIN,a.example,REJECT\n"
        updated = MODULE.set_module_category(content)
        self.assertTrue(updated.startswith("#!name=Example\n#!category=AdBlock\n"))


class ReadmeLinkTests(unittest.TestCase):
    def test_updates_sorted_raw_links_for_every_module(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(
                "Before\n<!-- MODULE_LINKS_START -->\nold\n<!-- MODULE_LINKS_END -->\nAfter\n",
                encoding="utf-8",
            )
            generated = {
                PurePosixPath("Video.sgmodule"): b"module",
                PurePosixPath("AdUnion.sgmodule"): b"module",
                PurePosixPath("_resources/source/file.js"): b"script",
            }
            MODULE.update_readme_links(
                readme,
                "https://raw.githubusercontent.com/owner/repo/main/Modules/Surge",
                generated,
            )
            content = readme.read_text(encoding="utf-8")
            ad_union = "- [AdUnion.sgmodule](https://raw.githubusercontent.com/owner/repo/main/Modules/Surge/AdUnion.sgmodule)"
            video = "- [Video.sgmodule](https://raw.githubusercontent.com/owner/repo/main/Modules/Surge/Video.sgmodule)"
            self.assertIn(ad_union, content)
            self.assertIn(video, content)
            self.assertLess(content.index(ad_union), content.index(video))
            self.assertNotIn("file.js", content)

    def test_rejects_nested_final_module(self):
        with tempfile.TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text(
                "<!-- MODULE_LINKS_START -->\n<!-- MODULE_LINKS_END -->\n",
                encoding="utf-8",
            )
            with self.assertRaises(MODULE.SyncError):
                MODULE.update_readme_links(
                    readme,
                    "https://raw.githubusercontent.com/owner/repo/main/Modules/Surge",
                    {PurePosixPath("Nested/Module.sgmodule"): b"module"},
                )


class DependencyMirrorTests(unittest.TestCase):
    def test_mirrors_all_runtime_files_but_not_descriptive_links(self):
        source = MODULE.SourceResult(
            source_id="example",
            provider="provider",
            source_url="https://example.com/module.sgmodule",
            output="Example.sgmodule",
            bundle=None,
            content="""#!name=Example
#!icon=https://assets.example.com/icon.png
#!homepage=https://example.com/project
[Rule]
RULE-SET,https://assets.example.com/rules.list,REJECT
[Map Local]
^https://api.example.com/config data-type=file data="https://assets.example.com/data.json"
[Script]
example = type=http-response,pattern=^https://api.example.com,script-path=https://assets.example.com/main.js
""",
        )
        original_fetch = MODULE.fetch_bytes
        MODULE.fetch_bytes = lambda url, headers=None, timeout=60, attempts=3, retry_delay=2: b"dependency-content"
        try:
            generated = {}
            mirrored = MODULE.mirror_dependencies(
                source,
                {},
                "https://raw.githubusercontent.com/owner/repo/main/Modules/Surge",
                generated,
                {},
            )
        finally:
            MODULE.fetch_bytes = original_fetch

        self.assertEqual(len(generated), 3)
        self.assertTrue(all(path.parts[0] == "_resources" for path in generated))
        self.assertEqual(mirrored.content.count("/Modules/Surge/_resources/"), 3)
        self.assertIn("#!icon=https://assets.example.com/icon.png", mirrored.content)
        self.assertIn("#!homepage=https://example.com/project", mirrored.content)
        self.assertNotIn("script-path=https://assets.example.com", mirrored.content)
        self.assertNotIn('data="https://assets.example.com', mirrored.content)


if __name__ == "__main__":
    unittest.main()
