"""Select immutable imported files for next startup; never mutate running bindings."""
import hashlib
import json
from pathlib import Path
import re
import time
import uuid

from cameras import CAMERAS_BY_ID
from import_source import atomic_json, exclusive
from schemas import SourceSelectionRequest
from source_catalog import SOURCE_ROOT, load_source, load_release


class SelectionConflict(ValueError): pass


def selection_token(binding):
    if binding is None: return 'default'
    # Metadata fingerprint only, not a video hash. Include the unique selection
    # marker to distinguish a later selection returning to the same release.
    encoded=json.dumps(binding['manifest'],sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(encoded).hexdigest()


def same_release_manifest(left, right):
    return {key:value for key,value in left.items() if key!='source_selection'} == {key:value for key,value in right.items() if key!='source_selection'}


def rollback_allowed(camera, current, target, root):
    seen={current['manifest']['release']}
    previous=current['manifest'].get('previous_release')
    for _ in range(9):
        if not isinstance(previous,str) or not re.fullmatch(r'[a-f0-9]{32}',previous) or previous in seen: return False
        seen.add(previous)
        binding=load_release(camera,previous,root)
        if previous==target: return True
        previous=binding['manifest'].get('previous_release')
    return False


def select_for_restart(camera, body, *, root=SOURCE_ROOT, authenticated_user=None):
    if camera not in CAMERAS_BY_ID: raise ValueError('Unknown camera')
    body=SourceSelectionRequest.model_validate(body).model_dump()
    root=Path(root).resolve()
    # These files are never opened by a running decoder through active.json.
    # Publication only changes the next-startup pointer, so processing continues.
    with exclusive(root/'.import.lock','Another source import or selection is in progress'):
        current=load_source(camera,root)
        if selection_token(current)!=body['expected_token']:
            raise SelectionConflict('Source selection changed since it was checked.')
        target=load_release(camera,body['release'],root,verify=True)
        current_id=current['manifest']['release'] if current else None
        if current_id==body['release']:
            return {'camera_id':camera,'release':body['release'],'already_selected':True}
        if body['intent']=='rollback':
            if not current or not rollback_allowed(camera,current,body['release'],root):
                raise ValueError('Rollback must use an earlier release from the selected import’s displayed parent history')
        elif target['manifest'].get('previous_release')!=current_id:
            raise SelectionConflict('This release was prepared against another managed selection.')
        if selection_token(load_source(camera,root))!=body['expected_token']:
            raise SelectionConflict('Source selection changed during verification.')
        previous=current['manifest'].get('source_selection',{}) if current else {}
        if not isinstance(previous,dict): previous={}
        marker={'id':uuid.uuid4().hex,'camera_id':camera,'version':1,'selected_at':time.time(),
                'intent':body['intent'],'reviewer':body['reviewer'],'reason':body['reason'],
                'reviewer_authenticated':bool(authenticated_user),
                'authenticated_user':authenticated_user,
                'from_release':current_id,'to_release':body['release'],'previous_selection':previous.get('id')}
        pointer={**target['manifest'],'source_selection':marker}
        folder=root/camera/'selection_history'
        if not folder.resolve().is_relative_to(root): raise ValueError('Selection records escape the managed source root')
        folder.mkdir(parents=True,exist_ok=True)
        receipt=folder/f"{marker['id']}.json"
        try:
            # Persist a proposal first; it is committed only when active.json
            # references this ID, or a later committed marker links back to it.
            atomic_json(receipt,marker)
            atomic_json(root/camera/'active.json',pointer)
        except BaseException:
            try:
                selected=load_source(camera,root)
                published=selected and selected['manifest'].get('source_selection',{}).get('id')==marker['id']
            except (ValueError,AttributeError): published=False
            if not published: receipt.unlink(missing_ok=True)
            raise
        return {'camera_id':camera,'release':body['release'],'already_selected':False}
