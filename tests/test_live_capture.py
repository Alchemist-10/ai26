"""RTSP configuration remains private and capture buffering is bounded."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from live_capture import LiveCapture, load_live_sources
import processing


class FakeCapture:
    def __init__(self, url, backend, params):
        self.url=url;self.backend=backend;self.params=params;self.index=0;self.released=False
    def isOpened(self): return True
    def read(self):
        self.index+=1
        time.sleep(.002)
        return True,np.full((3,4,3),self.index%255,dtype=np.uint8)
    def release(self): self.released=True


class LiveCaptureTests(unittest.TestCase):
    def test_private_config_loads_rtsp_source_without_returning_secrets_in_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'sources.json'
            config.write_text(json.dumps({'CAM-01':'rtsp://user:secret@127.0.0.1:554/stream'}))
            config.chmod(0o600)
            self.assertEqual(load_live_sources(config,['CAM-01'])['CAM-01'],'rtsp://user:secret@127.0.0.1:554/stream')
            config.chmod(0o644)
            with self.assertRaises(RuntimeError) as caught:
                load_live_sources(config,['CAM-01'])
            self.assertNotIn('secret',str(caught.exception))
            config.chmod(0o600)
            with patch.dict(os.environ,{'AI26_LIVE_SOURCES_FILE':str(config)}):
                health=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}]).health()
            self.assertNotIn('secret',repr(health))

    def test_rejects_unknown_camera_and_non_rtsp_url(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'sources.json'
            for sources in ({'CAM-99':'rtsp://127.0.0.1/stream'}, {'CAM-01':'https://example.test/'}):
                config.write_text(json.dumps(sources))
                config.chmod(0o600)
                with self.assertRaises(RuntimeError): load_live_sources(config,['CAM-01'])

    def test_reader_uses_timeouts_and_only_exposes_a_fresh_latest_frame(self):
        opened=[]
        def factory(*args):
            capture=FakeCapture(*args);opened.append(capture);return capture
        reader=LiveCapture('CAM-01','rtsp://user:secret@127.0.0.1/stream',capture_factory=factory)
        reader.start()
        deadline=time.monotonic()+1
        sample=None
        while time.monotonic()<deadline and sample is None:
            sample,_=reader.latest();time.sleep(.005)
        reader.stop()
        self.assertIsNotNone(sample)
        self.assertGreater(sample[1],0)
        self.assertEqual(opened[0].params[1],5000)
        self.assertEqual(opened[0].params[3],3000)
        self.assertTrue(opened[0].released)
        self.assertEqual(reader.latest()[1],'stopped')

    def test_live_frames_use_shared_processor_output_and_arrival_time_metadata(self):
        frame=np.zeros((12,16,3),dtype=np.uint8)
        class Reader:
            def latest(self): return ((1234.5,7,2,frame),'connected')
        processor=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'}],annotator=lambda value,*_: (value,[]))
        processor.live_sources={'CAM-01':'configured'}
        processor.live_captures={'CAM-01':Reader()}
        with patch.object(processing.store,'start_session') as start_session, \
             patch.object(processing,'capture_read_images',return_value={}), \
             patch.object(processing,'add_events',return_value=0):
            self.assertTrue(processor.step(processor.cameras[0]))
        session=start_session.call_args.args[0]
        self.assertEqual(session['source_mode'],'live')
        self.assertEqual(session['time_basis'],'capture_arrival_clock')
        self.assertIsNone(session['source_sha256'])
        self.assertEqual(processor.state['CAM-01']['source_mode'],'live')
        self.assertEqual(processor.state['CAM-01']['capture_sequence'],7)
        self.assertIsNone(processor.state['CAM-01']['source_time_seconds'])
        self.assertIsNotNone(processor.preview('CAM-01'))


if __name__=='__main__': unittest.main()
