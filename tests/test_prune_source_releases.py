import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from import_source import ImportBusy, exclusive
from prune_source_releases import plan_prune, prune


class PruneSourceReleases(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = self.root / 'sources'
        self.data = self.root / 'data'
        self.sources.mkdir()
        self.data.mkdir()
        self.now = 2_000_000_000.0

    def release(self, camera, release_id, *, previous=None, imported_at=None):
        folder = self.sources / camera / 'releases' / release_id
        folder.mkdir(parents=True)
        original = b'original-' + release_id.encode()
        playback = b'playback-' + release_id.encode()
        (folder / 'original.media').write_bytes(original)
        (folder / 'playback.mp4').write_bytes(playback)
        manifest = {
            'version': 1, 'camera_id': camera, 'release': release_id,
            'previous_release': previous, 'imported_at': self.now - 60 * 86400 if imported_at is None else imported_at,
            'original': {'file': 'original.media', 'bytes': len(original), 'sha256': hashlib.sha256(original).hexdigest()},
            'playback': {'file': 'playback.mp4', 'bytes': len(playback), 'sha256': hashlib.sha256(playback).hexdigest()},
        }
        (folder / 'manifest.json').write_text(json.dumps(manifest))
        return folder, manifest

    def test_dry_run_preserves_selected_chain_and_recent_ready_receipts(self):
        parent = 'a' * 32
        selected = 'b' * 32
        orphan = 'c' * 32
        receipt_protected = 'd' * 32
        previous_running = 'e' * 32
        self.release('CAM-07', parent)
        selected_folder, selected_manifest = self.release('CAM-07', selected, previous=parent, imported_at=self.now)
        orphan_folder, _ = self.release('CAM-07', orphan)
        receipt_folder, _ = self.release('CAM-07', receipt_protected)
        running_folder, _ = self.release('CAM-07', previous_running)
        selected_manifest['source_selection'] = {'from_release': previous_running}
        (self.sources / 'CAM-07' / 'active.json').write_text(json.dumps(selected_manifest))
        jobs = self.data / 'uploads' / 'jobs'
        jobs.mkdir(parents=True)
        (jobs / ('e' * 32 + '.json')).write_text(json.dumps({
            'job_id': 'e' * 32, 'camera_id': 'CAM-07', 'status': 'ready',
            'created_at': self.now - 10 * 86400, 'release': {'release': receipt_protected},
        }))

        result = plan_prune(self.sources, self.data, now=self.now, days=30)
        self.assertEqual([item['release'] for item in result['candidates']], [orphan])
        self.assertTrue(selected_folder.is_dir())
        self.assertTrue(orphan_folder.is_dir())
        self.assertTrue(receipt_folder.is_dir())
        self.assertTrue(running_folder.is_dir())
        self.assertEqual(result['skipped'], [])

    def test_apply_removes_only_old_verified_unselected_releases(self):
        selected = 'a' * 32
        orphan = 'b' * 32
        selected_folder, manifest = self.release('CAM-07', selected, imported_at=self.now)
        orphan_folder, _ = self.release('CAM-07', orphan)
        (self.sources / 'CAM-07' / 'active.json').write_text(json.dumps(manifest))

        result = prune(self.sources, self.data, now=self.now, days=30, apply=True)
        self.assertEqual(result['removed'], [orphan])
        self.assertTrue(selected_folder.is_dir())
        self.assertFalse(orphan_folder.exists())

    def test_invalid_release_is_retained_and_reported(self):
        selected = 'a' * 32
        bad = 'c' * 32
        _, manifest = self.release('CAM-07', selected, imported_at=self.now)
        bad_folder, _ = self.release('CAM-07', bad)
        (self.sources / 'CAM-07' / 'active.json').write_text(json.dumps(manifest))
        (bad_folder / 'original.media').write_bytes(b'tampered')

        result = plan_prune(self.sources, self.data, now=self.now, days=30)
        self.assertEqual(result['candidates'], [])
        self.assertEqual(result['skipped'][0]['release'], bad)
        self.assertTrue(bad_folder.is_dir())

    def test_old_receipts_prune_but_latest_ready_receipt_and_release_remain(self):
        old_release = 'f' * 32
        newest_release = 'e' * 32
        old_folder, _ = self.release('CAM-07', old_release)
        newest_folder, _ = self.release('CAM-07', newest_release)
        jobs = self.data / 'uploads' / 'jobs'
        jobs.mkdir(parents=True)
        old_job, latest_job = '1' * 32, '2' * 32
        for job, created, release in ((old_job, self.now - 60 * 86400, old_release),
                                      (latest_job, self.now - 45 * 86400, newest_release)):
            (jobs / f'{job}.json').write_text(json.dumps({
                'job_id': job, 'camera_id': 'CAM-07', 'status': 'ready',
                'created_at': created, 'release': {'release': release},
            }))

        result = prune(self.sources, self.data, now=self.now, days=30, apply=True)
        self.assertEqual([item['job_id'] for item in result['receipt_candidates']], [old_job])
        self.assertEqual(result['removed_receipts'], [old_job])
        self.assertFalse((jobs / f'{old_job}.json').exists())
        self.assertTrue((jobs / f'{latest_job}.json').is_file())
        self.assertFalse(old_folder.exists())
        self.assertTrue(newest_folder.is_dir())

    def test_active_processor_blocks_pruning(self):
        locks = ((self.data / '.processing.lock', 'processor'),
                 (self.sources / '.import.lock', 'import or selection'),
                 (self.sources / '.upload.lock', 'upload or preparation'))
        for path, label in locks:
            with self.subTest(lock=label), exclusive(path, 'test owner'):
                with self.assertRaisesRegex(ImportBusy, label):
                    prune(self.sources, self.data, now=self.now)

    def test_retention_bounds_are_enforced(self):
        for days in (0, 29, 366, True):
            with self.subTest(days=days), self.assertRaisesRegex(ValueError, '30 to 365'):
                plan_prune(self.sources, self.data, now=self.now, days=days)

    def test_default_layout_with_sources_inside_data_root_is_supported(self):
        data = self.root / 'nested-data'
        source = data / 'sources'
        source.mkdir(parents=True)
        result = plan_prune(source, data, now=self.now, days=30)
        self.assertEqual(result['candidates'], [])

    def test_fresh_install_without_source_root_reports_empty_inventory(self):
        missing_source = self.root / 'not-yet-created-sources'
        result = prune(missing_source, self.data, now=self.now, days=30)
        self.assertEqual(result['candidate_count'], 0)
        self.assertFalse(result['applied'])


if __name__ == '__main__':
    unittest.main()
