"""Manifest split-integrity checks; fixture data is not field evidence."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('dataset_manifest', ROOT / 'evaluation/dataset_manifest.py')
manifest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manifest)


class DatasetManifest(unittest.TestCase):
    def test_schema_version_requires_an_integer_not_a_coercible_value(self):
        for schema_version in (True, 1.0, '1'):
            with self.subTest(schema_version=schema_version), tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'manifest.json'
                path.write_text(json.dumps({'schema_version':schema_version}),encoding='utf-8')
                with self.assertRaisesRegex(manifest.ManifestError,'schema_version must be 1'):
                    manifest.validate_manifest(path)

    def test_manifest_cannot_disable_a_required_split_dimension(self):
        document = {
            'schema_version': 1,
            'dataset_id': 'fixture',
            'split_dimensions': ['vehicle_id', 'session_id'],
            'clips': [],
            'missing_inputs': [],
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'manifest.json'
            path.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaisesRegex(manifest.ManifestError, 'every required dimension'):
                manifest.validate_manifest(path)


if __name__ == '__main__':
    unittest.main()
