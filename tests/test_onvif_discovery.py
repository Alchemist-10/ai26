import socket
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from onvif_discovery import (
    DISCOVERY_ACTION,
    DISCOVERY_TO,
    MULTICAST_ADDRESS,
    MULTICAST_PORT,
    build_probe,
    discover_onvif,
    parse_probe_match,
)


RESPONSE = b'''<?xml version="1.0"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
 xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"
 xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery">
 <s:Body><d:ProbeMatches><d:ProbeMatch>
  <a:EndpointReference><a:Address>urn:uuid:camera-1</a:Address></a:EndpointReference>
  <d:Types>dn:NetworkVideoTransmitter</d:Types>
  <d:Scopes>onvif://www.onvif.org/name/Front%20Gate onvif://www.onvif.org/hardware/Camera%20X</d:Scopes>
  <d:XAddrs>http://192.168.1.20/onvif/device_service</d:XAddrs>
 </d:ProbeMatch></d:ProbeMatches></s:Body>
</s:Envelope>'''


class ProbeSocket:
    def __init__(self, *args):
        self.options = []
        self.sent = None
        self.reads = 0
        self.closed = False

    def setsockopt(self, *args): self.options.append(args)
    def bind(self, address): self.bound = address
    def settimeout(self, timeout): self.timeout = timeout
    def sendto(self, payload, address): self.sent = (payload, address)
    def recvfrom(self, _size):
        self.reads += 1
        if self.reads <= 2:
            return RESPONSE, ("192.168.1.20", 3702)
        raise socket.timeout
    def close(self): self.closed = True


class OnvifDiscoveryTests(unittest.TestCase):
    def test_probe_has_ws_discovery_headers_and_multicast_target(self):
        root = ET.fromstring(build_probe("urn:uuid:test-probe"))
        values = {element.tag.rsplit("}", 1)[-1]: element.text for element in root.iter() if element.text}
        self.assertEqual(values["Action"], DISCOVERY_ACTION)
        self.assertEqual(values["MessageID"], "urn:uuid:test-probe")
        self.assertEqual(values["To"], DISCOVERY_TO)
        self.assertIn("Probe", [element.tag.rsplit("}", 1)[-1] for element in root.iter()])

    def test_parse_extracts_endpoint_scopes_and_service_addresses(self):
        device = parse_probe_match(RESPONSE, "192.168.1.20")
        self.assertEqual(device["endpoint_id"], "urn:uuid:camera-1")
        self.assertEqual(device["source_address"], "192.168.1.20")
        self.assertEqual(device["service_addresses"], ["http://192.168.1.20/onvif/device_service"])
        self.assertEqual(len(device["scopes"]), 2)

    def test_parse_rejects_malformed_public_and_credential_bearing_addresses(self):
        self.assertIsNone(parse_probe_match(b"not xml", "192.168.1.20"))
        self.assertIsNone(parse_probe_match(RESPONSE, "8.8.8.8"))
        unsafe = RESPONSE.replace(b"http://192.168.1.20/onvif/device_service",
                                  b"http://user:password@192.168.1.20/onvif/device_service")
        self.assertIsNone(parse_probe_match(unsafe, "192.168.1.20"))

    def test_probe_uses_ttl_one_collects_and_deduplicates_local_devices(self):
        probe_socket = ProbeSocket()
        with patch("onvif_discovery.time.monotonic", side_effect=[1.0, 1.1]):
            result = discover_onvif(0.2, socket_factory=lambda *args: probe_socket)
        self.assertEqual(probe_socket.sent[1], (MULTICAST_ADDRESS, MULTICAST_PORT))
        self.assertEqual(probe_socket.options[0], (socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1))
        self.assertEqual(len(result["devices"]), 1)
        self.assertTrue(probe_socket.closed)

    def test_timeout_is_bounded(self):
        with self.assertRaisesRegex(ValueError, "between 0.2 and 5"):
            discover_onvif(10)


if __name__ == "__main__":
    unittest.main()
