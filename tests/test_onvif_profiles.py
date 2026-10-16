import base64
from datetime import datetime, timedelta, timezone
import hashlib
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from onvif_profiles import (
    MEDIA, SCHEMA, SOAP, WSSE, OnvifInspectionError, inspect_onvif_profiles,
    _safe_stream_uri,
)


def xml(local, contents=""):
    return f'<s:Envelope xmlns:s="{SOAP}" xmlns:t="{MEDIA}" xmlns:tt="{SCHEMA}"><s:Body>{contents}</s:Body></s:Envelope>'.encode()


class Response:
    status_code = 200
    def __init__(self, payload): self.payload, self.closed = payload, False
    def iter_content(self, chunk_size): yield self.payload
    def close(self): self.closed = True


class ErrorResponse(Response):
    status_code = 500


class ChunkResponse(Response):
    def __init__(self, chunks): super().__init__(b""); self.chunks = chunks
    def iter_content(self, chunk_size): yield from self.chunks


class Session:
    def __init__(self):
        self.trust_env = True
        self.calls = []
        device_time = datetime.now(timezone.utc) + timedelta(seconds=10)
        clock_payload = f'''<s:Envelope xmlns:s="{SOAP}" xmlns:tt="{SCHEMA}" xmlns:tds="http://www.onvif.org/ver10/device/wsdl"><s:Body><tds:GetSystemDateAndTimeResponse><tds:SystemDateAndTime><tt:DateTimeType>NTP</tt:DateTimeType><tt:DaylightSavings>false</tt:DaylightSavings><tt:UTCDateTime><tt:Time><tt:Hour>{device_time.hour}</tt:Hour><tt:Minute>{device_time.minute}</tt:Minute><tt:Second>{device_time.second}</tt:Second></tt:Time><tt:Date><tt:Year>{device_time.year}</tt:Year><tt:Month>{device_time.month}</tt:Month><tt:Day>{device_time.day}</tt:Day></tt:Date></tt:UTCDateTime></tds:SystemDateAndTime></tds:GetSystemDateAndTimeResponse></s:Body></s:Envelope>'''.encode()
        self.responses = [
            Response(xml("caps", '<t:GetCapabilitiesResponse><t:Capabilities><tt:Media><tt:XAddr>http://192.168.1.20/onvif/media</tt:XAddr></tt:Media></t:Capabilities></t:GetCapabilitiesResponse>')),
            Response(clock_payload),
            Response(xml("profiles", '<t:GetProfilesResponse><t:Profiles token="main"><tt:Name>Main</tt:Name><tt:VideoEncoderConfiguration><tt:Encoding>H264</tt:Encoding></tt:VideoEncoderConfiguration></t:Profiles></t:GetProfilesResponse>')),
            Response(xml("uri", '<t:GetStreamUriResponse><t:MediaUri><tt:Uri>rtsp://192.168.1.20:554/live/main</tt:Uri></t:MediaUri></t:GetStreamUriResponse>')),
        ]
        self.closed = False
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.responses.pop(0)
    def close(self): self.closed = True


class OnvifProfilesTests(unittest.TestCase):
    def test_read_only_profile_flow_builds_valid_stream_setup_and_closes_session(self):
        session = Session()
        result = inspect_onvif_profiles("192.168.1.20", "http://192.168.1.20/onvif/device", "operator", "secret", session_factory=lambda: session)
        self.assertEqual(result["profiles"][0]["stream_uri"], "rtsp://192.168.1.20:554/live/main")
        self.assertEqual(result["clock"]["status"], "estimated")
        self.assertEqual(result["clock"]["date_time_type"], "NTP")
        self.assertFalse(result["clock"]["daylight_savings"])
        self.assertGreater(result["clock"]["estimated_host_offset_seconds"], 8.0)
        self.assertLess(result["clock"]["estimated_host_offset_seconds"], 11.0)
        self.assertGreaterEqual(result["clock"]["uncertainty_seconds"], 1.0)
        self.assertFalse(result["persisted"])
        self.assertFalse(result["activated"])
        self.assertTrue(session.closed)
        self.assertFalse(session.trust_env)
        self.assertEqual(len(session.calls), 4)
        for _, kwargs in session.calls:
            self.assertEqual(kwargs["timeout"], (1.5, 3.0))
            self.assertFalse(kwargs["allow_redirects"])
        request = ET.fromstring(session.calls[3][1]["data"])
        names = {node.tag.rsplit("}", 1)[-1]: node.text for node in request.iter()}
        self.assertEqual(names["Stream"], "RTP-Unicast")
        self.assertEqual(names["Protocol"], "RTSP")
        self.assertEqual(names["ProfileToken"], "main")
        clock_request = ET.fromstring(session.calls[1][1]["data"])
        self.assertIn("GetSystemDateAndTime", [node.tag.rsplit("}", 1)[-1] for node in clock_request.iter()])

    def test_ws_security_uses_digest_not_raw_password(self):
        session = Session()
        inspect_onvif_profiles("192.168.1.20", "http://192.168.1.20/device", "operator", "secret", session_factory=lambda: session)
        root = ET.fromstring(session.calls[0][1]["data"])
        password = next(node.text for node in root.iter() if node.tag == f"{{{WSSE}}}Password")
        nonce = base64.b64decode(next(node.text for node in root.iter() if node.tag == f"{{{WSSE}}}Nonce"))
        created = next(node.text for node in root.iter() if node.tag.endswith("}Created"))
        expected = base64.b64encode(hashlib.sha1(nonce + created.encode() + b"secret").digest()).decode()
        self.assertEqual(password, expected)
        self.assertNotIn(b"secret", session.calls[0][1]["data"])

    def test_unavailable_clock_diagnostic_does_not_block_media_profiles(self):
        session = Session()
        session.responses[1] = ErrorResponse(b"device clock unsupported")
        result = inspect_onvif_profiles("192.168.1.20", "http://192.168.1.20/device", "u", "p", session_factory=lambda: session)
        self.assertEqual(result["clock"]["status"], "unavailable")
        self.assertEqual(result["profiles"][0]["name"], "Main")
        self.assertEqual(result["profiles"][0]["stream_uri"], "rtsp://192.168.1.20:554/live/main")

    def test_rejects_service_host_mismatch_and_untrusted_stream_uri(self):
        with self.assertRaises(OnvifInspectionError):
            inspect_onvif_profiles("192.168.1.20", "http://192.168.1.21/device", "u", "p", session_factory=Session)
        self.assertEqual(_safe_stream_uri("rtsp://192.168.1.21/live", "192.168.1.20")[1], "redacted_or_untrusted_uri")
        self.assertEqual(_safe_stream_uri("rtsp://user:secret@192.168.1.20/live", "192.168.1.20")[0], None)
        self.assertEqual(_safe_stream_uri("rtsp://192.168.1.20/live?token=secret", "192.168.1.20")[0], None)

    def test_rejects_unspecified_service_host_and_oversized_camera_response(self):
        with self.assertRaises(OnvifInspectionError):
            inspect_onvif_profiles("0.0.0.0", "http://0.0.0.0/device", "u", "p", session_factory=Session)
        session = Session()
        oversized = ChunkResponse([b"x" * (1024 * 1024 + 1)])
        session.responses[0] = oversized
        with self.assertRaisesRegex(OnvifInspectionError, "oversized"):
            inspect_onvif_profiles("192.168.1.20", "http://192.168.1.20/device", "u", "p", session_factory=lambda: session)
        self.assertTrue(oversized.closed)
        self.assertTrue(session.closed)

    def test_media_service_cannot_redirect_to_another_host(self):
        session = Session()
        session.responses[0] = Response(xml("caps", '<t:GetCapabilitiesResponse><tt:XAddr>http://192.168.1.21/media</tt:XAddr></t:GetCapabilitiesResponse>'))
        with self.assertRaises(OnvifInspectionError):
            inspect_onvif_profiles("192.168.1.20", "http://192.168.1.20/device", "u", "p", session_factory=lambda: session)
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
