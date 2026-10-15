"""Bounded WS-Discovery probe for ONVIF cameras on the local IPv4 network."""
from __future__ import annotations

import ipaddress
import socket
import time
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit, urlunsplit


MULTICAST_ADDRESS = "239.255.255.250"
MULTICAST_PORT = 3702
DISCOVERY_ACTION = "http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe"
DISCOVERY_TO = "urn:schemas-xmlsoap-org:ws:2005:04:discovery"
SOAP_NS = "http://www.w3.org/2003/05/soap-envelope"
WSA_NS = "http://schemas.xmlsoap.org/ws/2004/08/addressing"
WSD_NS = "http://schemas.xmlsoap.org/ws/2005/04/discovery"


def build_probe(message_id: str | None = None) -> bytes:
    """Build a WS-Discovery Probe compatible with ONVIF devices."""
    message_id = message_id or f"urn:uuid:{uuid.uuid4()}"
    envelope = ET.Element(f"{{{SOAP_NS}}}Envelope")
    header = ET.SubElement(envelope, f"{{{SOAP_NS}}}Header")
    ET.SubElement(header, f"{{{WSA_NS}}}Action").text = DISCOVERY_ACTION
    ET.SubElement(header, f"{{{WSA_NS}}}MessageID").text = message_id
    ET.SubElement(header, f"{{{WSA_NS}}}To").text = DISCOVERY_TO
    ET.SubElement(ET.SubElement(envelope, f"{{{SOAP_NS}}}Body"), f"{{{WSD_NS}}}Probe")
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _children_text(element: ET.Element, name: str) -> str | None:
    for child in element.iter():
        if child is not element and child.tag.rsplit("}", 1)[-1] == name and child.text:
            return child.text.strip()
    return None


def _usable_xaddrs(value: str | None) -> list[str]:
    if not value:
        return []
    results = []
    for candidate in value.split():
        if len(candidate) > 2048:
            continue
        try:
            parsed = urlsplit(candidate)
            if (parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname
                    or parsed.username is not None or parsed.password is not None
                    or parsed.fragment or parsed.port is not None and not 1 <= parsed.port <= 65535):
                continue
        except ValueError:
            continue
        # Probe responses are unauthenticated; never echo URL query tokens into the UI.
        results.append(urlunsplit(parsed._replace(query="", fragment="")))
        if len(results) == 8:
            break
    return results


def parse_probe_match(payload: bytes, source_address: str) -> dict | None:
    """Parse a device response without fetching any advertised service URL."""
    try:
        source_ip = ipaddress.ip_address(source_address)
        if not (source_ip.is_private or source_ip.is_link_local):
            return None
        root = ET.fromstring(payload)
    except (ValueError, ET.ParseError):
        return None

    matches = [element for element in root.iter() if element.tag.rsplit("}", 1)[-1] == "ProbeMatch"]
    if not matches:
        return None
    match = matches[0]
    xaddrs = _usable_xaddrs(_children_text(match, "XAddrs"))
    if not xaddrs:
        return None
    scopes = (_children_text(match, "Scopes") or "").split()
    address = _children_text(match, "Address")
    return {
        "endpoint_id": address[:256] if address else None,
        "source_address": str(source_ip),
        "service_addresses": xaddrs,
        "scopes": [scope[:512] for scope in scopes[:20]],
    }


def discover_onvif(timeout_seconds: float = 2.0, *, socket_factory=socket.socket) -> dict:
    """Send one link-local probe and collect bounded responses until timeout."""
    if not 0.2 <= timeout_seconds <= 5.0:
        raise ValueError("Discovery timeout must be between 0.2 and 5 seconds")

    devices: dict[str, dict] = {}
    sock = socket_factory(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        sock.bind(("", 0))
        sock.settimeout(timeout_seconds)
        sock.sendto(build_probe(), (MULTICAST_ADDRESS, MULTICAST_PORT))
        started = time.monotonic()
        while len(devices) < 64:
            try:
                payload, source = sock.recvfrom(65535)
            except socket.timeout:
                break
            except OSError:
                break
            if not source:
                continue
            device = parse_probe_match(payload, source[0])
            if device:
                key = device["endpoint_id"] or ",".join(device["service_addresses"])
                devices.setdefault(key, device)
    finally:
        sock.close()
    return {
        "devices": list(devices.values()),
        "probe_timeout_seconds": timeout_seconds,
        "elapsed_seconds": round(max(0.0, time.monotonic() - started), 3) if "started" in locals() else 0.0,
    }
