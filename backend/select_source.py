"""Select a prepared release offline with integrity and expected-selection checks."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from cameras import CAMERAS_BY_ID
from import_source import atomic_json, exclusive
from source_catalog import DATA_ROOT, SOURCE_ROOT, load_release, load_source


def select_release(camera, release, expected_current, *, root=SOURCE_ROOT, data_root=DATA_ROOT):
    if camera not in CAMERAS_BY_ID: raise ValueError('Unknown camera')
    root, data = Path(root).resolve(), Path(data_root).resolve()
    with exclusive(data/'.processing.lock','Stop the processor before selecting footage'), exclusive(root/'.import.lock','Another import or selection is in progress'):
        binding = load_release(camera, release, root, verify=True)
        manifest = binding['manifest']
        current = load_source(camera, root, verify=True)
        current_id = current['manifest']['release'] if current else 'default'
        if current_id == release: return {'camera_id':camera,'release':release,'already_selected':True,'restart_required':True}
        if current_id != expected_current or (manifest.get('previous_release') or 'default') != current_id:
            raise ValueError('The selected source changed since preparation; prepare again against the latest selection')
        atomic_json(root/camera/'active.json',manifest)
        return {'camera_id':camera,'release':release,'already_selected':False,'restart_required':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('camera',choices=sorted(CAMERAS_BY_ID));parser.add_argument('release')
    parser.add_argument('--expected-current',required=True)
    args=parser.parse_args()
    try: result=select_release(args.camera,args.release,args.expected_current)
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        print(f'Selection failed: {error}',file=sys.stderr);return 1
    print(json.dumps(result,indent=2));return 0


if __name__=='__main__':sys.exit(main())
