"""Source inspection is read-only, bounded and separate from running bindings."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

os.environ['AI26_PROCESSING_ENABLED'] = '0'
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
import cameras
import main
import source_catalog
import source_status


class SourceStatus(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.base = Path(folder.name); self.root = self.base / 'sources'
        self.original = self.base / 'input.mp4'
        self.proxy_root = self.base / 'proxies'; self.proxy_root.mkdir()
        self.proxy = self.proxy_root / 'CAM-07.mp4'
        for mocked in (
            patch.dict(cameras.CAMERAS_BY_ID, {'CAM-07': {'path': str(self.original)}}),
            patch.dict(cameras.MANAGED_SOURCES, {}, clear=True),
            patch.object(cameras, 'PLAYBACK_ROOT', self.proxy_root),
            patch.object(main, 'source_status', side_effect=lambda camera: source_status.source_status(camera, self.root)),
        ):
            mocked.start(); self.addCleanup(mocked.stop)
        self.client = TestClient(main.app)

    def publish(self, index=1, previous=None, **extra):
        release = f'{index:032x}'
        folder = self.root / 'CAM-07' / 'releases' / release; folder.mkdir(parents=True)
        original = folder / 'original.media'; original.write_bytes(f'original {index}'.encode())
        playback = folder / 'playback.mp4'; playback.write_bytes(f'proxy {index}'.encode())
        manifest = {'version': 1, 'camera_id': 'CAM-07', 'release': release, 'previous_release': previous,
                    'reviewer': 'Local tester', 'reason': 'Synthetic source status fixture', 'time_basis': 'replay_clock', 'imported_at': 100,
                    **{role: {'file': path.name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                              'video': {'width': 320, 'height': 240, 'fps': 10, 'duration_seconds': 1}} for role, path in [('original', original), ('playback', playback)]},
                    **extra}
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        (self.root / 'CAM-07' / 'active.json').write_text(json.dumps(manifest))
        return source_catalog.load_source('CAM-07', self.root, verify=True)

    def get(self):
        response = self.client.get('/api/cameras/CAM-07/source')
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_missing_source_and_unknown_camera(self):
        result = self.get()
        self.assertEqual(result['active']['kind'], 'missing')
        self.assertFalse(result['active']['inference']['available'])
        self.assertEqual(result['selection']['status'], 'current')
        self.assertEqual(result['history']['releases'], [])
        self.assertEqual(self.client.get('/api/cameras/CAM-99/source').status_code, 404)
        self.assertNotIn(str(self.base), json.dumps(result))

    def test_bundled_proxy_is_labeled_as_inference_derivative(self):
        self.proxy.write_bytes(b'bundled proxy')
        result = self.get()
        self.assertEqual(result['active']['kind'], 'bundled_proxy')
        self.assertEqual(result['active']['inference']['filename'], 'CAM-07.mp4')
        self.assertIsNone(result['active']['release'])

    def test_configured_original_and_playback_are_distinct(self):
        self.original.write_bytes(b'configured original'); self.proxy.write_bytes(b'proxy')
        result = self.get()
        self.assertEqual(result['active']['kind'], 'configured_original')
        self.assertEqual(result['active']['inference']['filename'], 'input.mp4')
        self.assertEqual(result['active']['playback']['filename'], 'CAM-07.mp4')

    def test_current_managed_source_never_rehashes_or_accesses_sql(self):
        binding = self.publish(); cameras.MANAGED_SOURCES['CAM-07'] = binding
        store = MagicMock()
        with patch.object(source_catalog, 'file_digest', side_effect=AssertionError('No rehash')), patch.object(main, 'store', store):
            result = self.get()
        self.assertEqual(result['active']['kind'], 'managed')
        self.assertEqual(result['selection']['status'], 'current')
        self.assertTrue(result['active']['inference']['size_matches_import'])
        self.assertEqual(result['history']['releases'][0]['release'], binding['manifest']['release'])
        self.assertEqual(store.mock_calls, [])
        self.assertIn('have not been rehashed', result['verification'])

    def test_selected_replacement_does_not_switch_running_sources(self):
        first = self.publish(); cameras.MANAGED_SOURCES['CAM-07'] = first
        second = self.publish(2, first['manifest']['release'])
        result = self.get()
        self.assertEqual(result['selection']['status'], 'restart_required')
        self.assertEqual(result['active']['release']['release'], first['manifest']['release'])
        self.assertEqual(result['selection']['release']['release'], second['manifest']['release'])
        self.assertEqual(self.client.get('/api/video/CAM-07').content, b'proxy 1')
        self.assertEqual(cameras.camera_source('CAM-07'), first['original'])

    def test_edited_manifest_same_release_still_requires_restart(self):
        first = self.publish(); cameras.MANAGED_SOURCES['CAM-07'] = first
        pointer = self.root / 'CAM-07/active.json'
        edited = dict(first['manifest'], reason='Edited selection reason'); pointer.write_text(json.dumps(edited))
        result = self.get()
        self.assertEqual(result['selection']['status'], 'restart_required')
        self.assertEqual(result['active']['release']['reason'], 'Synthetic source status fixture')
        self.assertEqual(result['selection']['release']['reason'], 'Edited selection reason')

    def test_removed_pointer_requires_restart_without_losing_running_binding(self):
        first = self.publish(); cameras.MANAGED_SOURCES['CAM-07'] = first
        (self.root / 'CAM-07/active.json').unlink()
        result = self.get()
        self.assertEqual(result['selection']['status'], 'restart_required')
        self.assertIsNone(result['selection']['release'])
        self.assertEqual(result['active']['release']['release'], first['manifest']['release'])

    def test_invalid_pointer_keeps_active_source_and_has_safe_recovery_message(self):
        first = self.publish(); cameras.MANAGED_SOURCES['CAM-07'] = first
        pointer = self.root / 'CAM-07/active.json'; pointer.write_text('{broken')
        result = self.get()
        self.assertEqual(result['selection']['status'], 'invalid')
        self.assertEqual(result['active']['release']['release'], first['manifest']['release'])
        self.assertIn('Restore', result['selection']['error'])
        self.assertNotIn(str(self.base), json.dumps(result))
        pointer.write_bytes(b' ' * (source_status.MAX_MANIFEST_BYTES + 1))
        self.assertEqual(self.get()['selection']['status'], 'invalid')
        with self.assertRaisesRegex(ValueError, 'too large'):
            source_catalog.load_source('CAM-07', self.root)

    def test_changed_and_missing_managed_files_are_reported(self):
        first = self.publish(); cameras.MANAGED_SOURCES['CAM-07'] = first
        first['original'].write_bytes(b'changed-size')
        result = self.get()
        self.assertFalse(result['active']['inference']['size_matches_import'])
        self.assertEqual(result['selection']['status'], 'invalid')
        first['playback'].unlink()
        self.assertFalse(self.get()['active']['playback']['available'])

    def test_history_follows_at_most_ten_parent_manifests(self):
        previous = None
        for index in range(1, 13): previous = self.publish(index, previous)['manifest']['release']
        result = self.get()['history']
        self.assertEqual(len(result['releases']), 10); self.assertTrue(result['more'])
        self.assertEqual([item['release'] for item in result['releases']], [f'{i:032x}' for i in range(12, 2, -1)])

    def test_broken_unsafe_and_cyclic_history_is_partial(self):
        first = self.publish(); second = self.publish(2, first['manifest']['release'])
        path = first['original'].parent / 'manifest.json'; path.write_text('{}')
        result = self.get()['history']
        self.assertEqual(len(result['releases']), 1); self.assertIsNotNone(result['error'])
        path.unlink(); path.symlink_to(self.base / 'outside.json')
        (self.base / 'outside.json').write_text(json.dumps(first['manifest']))
        self.assertEqual(len(self.get()['history']['releases']), 1)
        pointer = self.root / 'CAM-07/active.json'
        pointer.write_text(json.dumps(dict(second['manifest'], previous_release=second['manifest']['release'])))
        (second['original'].parent / 'manifest.json').write_text(pointer.read_text())
        self.assertIn('repeated', self.get()['history']['error'])

    def test_optional_metadata_is_bounded_and_nonfinite_values_are_absent(self):
        self.publish(reviewer='x' * 2000, reason={'unsafe': '/private'}, imported_at=float('nan'),
                     original={'file': 'original.media', 'bytes': len(b'original 1'), 'sha256': hashlib.sha256(b'original 1').hexdigest(),
                               'video': {'fps': float('inf'), 'width': 10**400}})
        result = self.get()['selection']['release']
        self.assertEqual(len(result['reviewer']), 1000)
        self.assertIsNone(result['reason']); self.assertIsNone(result['imported_at'])
        self.assertIsNone(result['original']['video']['fps']); self.assertIsNone(result['original']['video']['width'])


if __name__ == '__main__': unittest.main()
