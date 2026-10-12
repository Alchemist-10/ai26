"""Bounded decoder advancement preserves target index and fails without stale state."""
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
os.environ['AI26_PROCESSING_ENABLED']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import numpy as np
import processing

class Capture:
    def __init__(self):
        self.next=0;self.last=None;self.seeks=[];self.grabs=0;self.position_known=True;self.fail_grab=False;self.fail_retrieve=False;self.fail_seek=False
    def get(self,key):return self.next if self.position_known else float('nan')
    def set(self,key,value):
        self.seeks.append(value)
        if self.fail_seek:return False
        self.next=value;return True
    def grab(self):
        self.grabs+=1
        if self.fail_grab:return False
        self.last=self.next;self.next+=1;return True
    def retrieve(self):return (False,None) if self.fail_retrieve else (True,np.full((2,2,3),self.last%256,dtype=np.uint8))
    def read(self):
        self.last=self.next;self.next+=1
        return True,np.full((2,2,3),self.last%256,dtype=np.uint8)

class DecodeSampling(unittest.TestCase):
    def setUp(self):
        self.p=processing.Processor(cameras=[{'id':'CAM-01','kind':'vehicle'},{'id':'CAM-02','kind':'vehicle'}]);self.cap=Capture()
    def frame(self,target,camera='CAM-01',cap=None):
        raw=self.p.decode_frame(camera,cap or self.cap,target);self.assertTrue(np.all(raw==target%256));return raw
    def test_first_seek_then_forward_grabs_retrieve_exact_target(self):
        self.frame(3);self.frame(9)
        self.assertEqual(self.cap.seeks,[3]);self.assertEqual(self.cap.grabs,6);self.assertEqual(self.p.decode_next['CAM-01'],10)
        self.assertEqual(self.p.state['CAM-01']['decode_mode'],'forward');self.assertTrue(self.p.state['CAM-01']['decode_position_verified'])
    def test_forward_limit_counts_target_and_backward_repeat_large_gap_seek(self):
        self.p.forward_decode_limit=4;self.frame(3);self.frame(7)
        self.assertEqual(self.cap.grabs,4);self.frame(12);self.frame(12);self.frame(2);self.frame(200)
        self.assertEqual(self.cap.seeks,[3,12,12,2,200]);self.assertEqual(self.cap.grabs,4)
    def test_unverified_initial_or_changed_position_uses_seek(self):
        self.cap.position_known=False;self.frame(5);self.frame(8)
        self.assertEqual(self.cap.grabs,0);self.assertNotIn('CAM-01',self.p.decode_next);self.assertFalse(self.p.state['CAM-01']['decode_position_verified'])
        self.cap.position_known=True;self.frame(5);self.cap.next=50;self.frame(8)
        self.assertEqual(self.cap.seeks,[5,8,5,8]);self.assertEqual(self.cap.grabs,0)
    def test_grab_or_retrieve_failures_clear_next_position(self):
        for failure in ('fail_grab','fail_retrieve'):
            cap=Capture();self.frame(1,cap=cap);setattr(cap,failure,True)
            with self.assertRaises(RuntimeError):self.p.decode_frame('CAM-01',cap,5)
            self.assertNotIn('CAM-01',self.p.decode_next);self.assertIsNone(self.p.state['CAM-01']['decode_position_verified'])
    def test_forward_position_drift_rejects_target_and_clears_state(self):
        self.frame(1);original=self.cap.retrieve
        def wrong():
            result=original();self.cap.next+=1;return result
        with patch.object(self.cap,'retrieve',side_effect=wrong):
            with self.assertRaisesRegex(RuntimeError,'position'):self.p.decode_frame('CAM-01',self.cap,5)
        self.assertNotIn('CAM-01',self.p.decode_next)
    def test_seek_failure_and_disabled_optimization_are_explicit(self):
        self.frame(1);self.cap.fail_seek=True
        with self.assertRaisesRegex(RuntimeError,'sought'):self.p.decode_frame('CAM-01',self.cap,500)
        self.assertNotIn('CAM-01',self.p.decode_next)
        self.cap.fail_seek=False;self.p.forward_decode_limit=0;self.frame(1);self.frame(5)
        self.assertEqual(self.cap.grabs,0);self.assertEqual(self.p.state['CAM-01']['decode_mode'],'seek')
    def test_per_camera_positions_are_independent(self):
        second=Capture();self.frame(5);self.frame(50,camera='CAM-02',cap=second);self.frame(9)
        self.assertEqual(self.p.decode_next,{'CAM-01':10,'CAM-02':51});self.assertEqual(second.grabs,0)
    def test_constructor_limit_clamps_and_can_disable(self):
        for supplied,expected in [('999',128),('-1',0),('0',0),('32',32)]:
            with patch.dict(os.environ,{'AI26_FORWARD_DECODE_MAX_FRAMES':supplied}):
                self.assertEqual(processing.Processor(cameras=[]).forward_decode_limit,expected)

if __name__=='__main__':unittest.main()
