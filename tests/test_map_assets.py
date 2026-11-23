"""Integrity and distribution contracts for the pinned interactive-map runtime."""
import base64
from hashlib import sha256, sha512
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from scripts import build_site


class CytoscapeIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = Path(self.temp.name) / 'cache'
        self.payloads = {'cytoscape-3.35.0.min.js': b'known runtime',
                         'cytoscape-3.35.0.LICENSE.txt': b'MIT license fixture'}
        self.files = {name: ('package/' + name, sha256(data).hexdigest())
                      for name, data in self.payloads.items()}
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            for name, data in self.payloads.items():
                member = tarfile.TarInfo(self.files[name][0])
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            # Never extract unrelated members, including traversal paths.
            unrelated = tarfile.TarInfo('../do-not-extract.txt')
            unrelated.size = 6
            archive.addfile(unrelated, io.BytesIO(b'secret'))
        self.archive = stream.getvalue()
        self.integrity = base64.b64encode(sha512(self.archive).digest()).decode('ascii')
        self.addCleanup(patch.stopall)
        patch.object(build_site, 'CYTOSCAPE_FILES', self.files).start()
        patch.object(build_site, 'CYTOSCAPE_INTEGRITY', self.integrity).start()

    def download(self, data=None):
        return patch.object(build_site, 'urlopen', return_value=io.BytesIO(self.archive if data is None else data))

    def test_verified_archive_publishes_only_runtime_and_license(self):
        with self.download() as network:
            paths = build_site.cytoscape_assets(self.cache)
        network.assert_called_once_with(build_site.CYTOSCAPE_URL, timeout=60)
        self.assertEqual({path.name: path.read_bytes() for path in paths}, self.payloads)
        self.assertEqual(set(path.name for path in self.cache.iterdir()), set(self.payloads))
        self.assertFalse((self.cache.parent / 'do-not-extract.txt').exists())

    def test_valid_cache_works_offline_and_license_tampering_requires_download(self):
        with self.download():
            build_site.cytoscape_assets(self.cache)
        with patch.object(build_site, 'urlopen') as network:
            build_site.cytoscape_assets(self.cache)
            network.assert_not_called()
        license_path = self.cache / 'cytoscape-3.35.0.LICENSE.txt'
        license_path.write_bytes(b'corrupt')
        with self.download() as network:
            build_site.cytoscape_assets(self.cache)
            network.assert_called_once()
        self.assertEqual(license_path.read_bytes(), self.payloads[license_path.name])

    def test_archive_mismatch_keeps_previous_cache_intact(self):
        self.cache.mkdir()
        old = self.cache / 'cytoscape-3.35.0.min.js'
        old.write_bytes(b'previous cache')
        with self.download(b'unexpected download'):
            with self.assertRaisesRegex(ValueError, 'archive checksum'):
                build_site.cytoscape_assets(self.cache)
        self.assertEqual(old.read_bytes(), b'previous cache')
        self.assertEqual(list(self.cache.iterdir()), [old])

    def test_asset_mismatch_fails_before_writing_any_member(self):
        license_name = 'cytoscape-3.35.0.LICENSE.txt'
        self.files[license_name] = (self.files[license_name][0], '0' * 64)
        with self.download():
            with self.assertRaisesRegex(ValueError, 'asset checksum'):
                build_site.cytoscape_assets(self.cache)
        self.assertFalse(self.cache.exists())

    def test_missing_package_member_is_reported_as_a_validation_error(self):
        name = 'cytoscape-3.35.0.min.js'
        self.files[name] = ('package/missing.js', self.files[name][1])
        with self.download():
            with self.assertRaisesRegex(ValueError, 'Invalid Cytoscape package'):
                build_site.cytoscape_assets(self.cache)
        self.assertFalse(self.cache.exists())
