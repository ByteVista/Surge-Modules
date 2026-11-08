import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/catalog.py'
SPEC = importlib.util.spec_from_file_location('catalog', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class CatalogTests(unittest.TestCase):
    def test_mitm_only_module_is_rejected(self):
        with self.assertRaises(ValueError):
            MODULE.validate_module('#!name=Empty\n[MITM]\nhostname = example.com\n')

    def test_legacy_pages_and_local_resources_are_rejected(self):
        for url in ['https://bytevista.github.io/Surge_Modules/a.js', 'http://127.0.0.1:9100/a.js']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                MODULE.validate_module('[Rule]\nDOMAIN,ads.example.com,REJECT\n[Script]\nad = script-path='+url)

    def test_native_surge_module_is_accepted_without_rewriting(self):
        text = '[Script]\n[VVebo]修复 = type=http-request, pattern=^https://example.com, script-path=https://example.com/a.js\n[MITM]\nhostname = %APPEND% example.com\n'
        MODULE.validate_module(text)
        self.assertEqual(MODULE.dependencies(text), {'https://example.com/a.js'})

    def test_all_supported_remote_resource_attributes_are_checked(self):
        text = 'script-path=https://example.com/a.js, data-path="https://example.com/b.json"\njq-path=https://example.com/c.jq\nRULE-SET,https://example.com/d.list,REJECT\n'
        self.assertEqual(len(MODULE.dependencies(text)), 4)

    def test_install_link_round_trips_unicode_and_query_strings(self):
        url = 'https://raw.githubusercontent.com/example/repo/main/中文.sgmodule?a=1&b=2'
        link = MODULE.install_link(url, 'ByteVista/Surge_Modules')
        parsed = MODULE.urllib.parse.urlsplit(link)
        self.assertEqual(MODULE.urllib.parse.parse_qs(parsed.fragment)['url'], [url])

    def test_readme_generation_preserves_surrounding_content_and_is_idempotent(self):
        old = 'before\n'+MODULE.START+'\nold\n'+MODULE.END+'\nafter'
        catalog = MODULE.START+'\nnew\n'+MODULE.END
        new = MODULE.update_readme(old, catalog)
        self.assertEqual(new, 'before\n'+catalog+'\nafter')
        self.assertEqual(MODULE.update_readme(new, catalog), new)

    def test_public_catalog_points_to_upstream_and_not_our_retired_files(self):
        config = MODULE.load_config(SCRIPT.parents[1] / 'config/sources.yaml')
        for key, app in config['apps'].items():
            if app.get('enabled') is False:
                continue
            with self.subTest(app=key):
                self.assertNotIn('bytevista', app['url'].lower())
                self.assertTrue(MODULE.valid_url(app['url']))
        self.assertIn('kokoryh/Sparkle', config['apps']['bilibili']['url'])
        self.assertIn('/Beta/', config['apps']['vvebo']['url'])

    def test_lonn_and_quantumult_format_is_not_a_surge_module(self):
        with self.assertRaises(ValueError):
            MODULE.validate_module('[rewrite_local]\n^https://example.com url reject\n[mitm]\nhostname = example.com\n')

if __name__ == '__main__':
    unittest.main()
