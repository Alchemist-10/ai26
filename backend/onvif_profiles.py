"""Bounded, read-only ONVIF media-profile inspection for discovered LAN cameras."""
from __future__ import annotations

import base64
import hashlib
import ipaddress
import os
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import requests

SOAP = "http://www.w3.org/2003/05/soap-envelope"
DEVICE = "http://www.onvif.org/ver10/device/wsdl"
MEDIA = "http://www.onvif.org/ver10/media/wsdl"
SCHEMA = "http://www.onvif.org/ver10/schema"
WSSE = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd"
WSU = "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd"
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_PROFILES = 4


class OnvifInspectionError(ValueError):
    """A safe-to-display ONVIF error with no URL, credential or device response."""


def _device_endpoint(source_address: str, service_address: str) -> tuple[str, str]:
    try:
        source = ipaddress.ip_address(source_address)
        parsed = urlsplit(service_address)
        advertised = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except ValueError as exc:
        raise OnvifInspectionError("Select a discovered device with a literal IP service address.") from exc
    if (source.version != 4 or advertised != source or source.is_loopback or source.is_multicast
            or source.is_unspecified or source.is_reserved
            or not (source.is_private or source.is_link_local)):
        raise OnvifInspectionError("The ONVIF service must use the discovered device's private IPv4 address.")
    if (parsed.scheme.lower() not in {"http", "https"} or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or not parsed.path.startswith("/") or not 1 <= port <= 65535):
        raise OnvifInspectionError("The discovered ONVIF service address is invalid.")
    # Rebuild from the datagram source to discard any untrusted URL authority details.
    netloc = f"{source.compressed}:{port}"
    return f"{parsed.scheme.lower()}://{netloc}{parsed.path}", source.compressed


def _soap_envelope(operation: str, namespace: str, username: str, password: str, children=()) -> bytes:
    envelope = ET.Element(f"{{{SOAP}}}Envelope")
    header = ET.SubElement(envelope, f"{{{SOAP}}}Header")
    security = ET.SubElement(header, f"{{{WSSE}}}Security")
    token = ET.SubElement(security, f"{{{WSSE}}}UsernameToken")
    nonce = os.urandom(20)
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    digest = base64.b64encode(hashlib.sha1(nonce + created.encode() + password.encode()).digest()).decode("ascii")
    ET.SubElement(token, f"{{{WSSE}}}Username").text = username
    password_node = ET.SubElement(token, f"{{{WSSE}}}Password", {
        "Type": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-username-token-profile-1.0#PasswordDigest"})
    password_node.text = digest
    nonce_node = ET.SubElement(token, f"{{{WSSE}}}Nonce", {
        "EncodingType": "http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary"})
    nonce_node.text = base64.b64encode(nonce).decode("ascii")
    ET.SubElement(token, f"{{{WSU}}}Created").text = created
    body = ET.SubElement(envelope, f"{{{SOAP}}}Body")
    command = ET.SubElement(body, f"{{{namespace}}}{operation}")
    if operation == "GetStreamUri":
        setup = ET.SubElement(command, f"{{{namespace}}}StreamSetup")
        ET.SubElement(setup, f"{{{SCHEMA}}}Stream").text = "RTP-Unicast"
        transport = ET.SubElement(setup, f"{{{SCHEMA}}}Transport")
        ET.SubElement(transport, f"{{{SCHEMA}}}Protocol").text = "RTSP"
    for name, value in children:
        ET.SubElement(command, f"{{{namespace}}}{name}").text = value
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _read_response(response) -> bytes:
    if response.status_code < 200 or response.status_code >= 300:
        raise OnvifInspectionError("The camera rejected an ONVIF media-profile request.")
    payload = bytearray()
    for chunk in response.iter_content(chunk_size=16384):
        payload.extend(chunk)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise OnvifInspectionError("The camera returned an oversized ONVIF response.")
    return bytes(payload)


def _post(session, url: str, operation: str, namespace: str, username: str, password: str,
          children=(), timeout_seconds=3.0) -> ET.Element:
    action = f"{namespace}/{operation}"
    response = None
    try:
        response = session.post(url, data=_soap_envelope(operation, namespace, username, password, children),
                                headers={"Content-Type": f'application/soap+xml; charset=utf-8; action="{action}"'},
                                timeout=(1.5, timeout_seconds), allow_redirects=False, stream=True)
        payload = _read_response(response)
        return ET.fromstring(payload)
    except OnvifInspectionError:
        raise
    except (requests.RequestException, ET.ParseError, OSError) as exc:
        raise OnvifInspectionError("The ONVIF camera did not return a valid media response.") from exc
    finally:
        if response is not None:
            response.close()


def _text(element: ET.Element, local_name: str) -> str | None:
    for child in element.iter():
        if child is not element and child.tag.rsplit("}", 1)[-1] == local_name and child.text:
            return child.text.strip()
    return None


def _profiles(root: ET.Element) -> list[tuple[str, str, str | None]]:
    profiles = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] != "Profiles":
            continue
        token = next((value for key, value in element.attrib.items() if key.rsplit("}", 1)[-1] == "token"), None)
        name = _text(element, "Name")
        encoding = _text(element, "Encoding")
        if token and name:
            profiles.append((token[:256], name[:120], encoding[:40] if encoding else None))
        if len(profiles) >= MAX_PROFILES:
            break
    return profiles


def _safe_stream_uri(uri: str | None, source_ip: str) -> tuple[str | None, str]:
    if not uri or len(uri) > 2048:
        return None, "unavailable"
    try:
        parsed = urlsplit(uri)
        host = ipaddress.ip_address(parsed.hostname or "")
        if (parsed.scheme.lower() not in {"rtsp", "rtsps"} or parsed.username is not None or parsed.password is not None
                or parsed.query or parsed.fragment or not (host.is_private or host.is_link_local)
                or host.is_loopback or host.is_multicast or host.is_unspecified or host.is_reserved
                or host.compressed != source_ip):
            return None, "redacted_or_untrusted_uri"
        port = parsed.port
        authority = host.compressed + (f":{port}" if port else "")
        return f"{parsed.scheme.lower()}://{authority}{parsed.path}", "available"
    except ValueError:
        return None, "redacted_or_untrusted_uri"


def inspect_onvif_profiles(source_address: str, service_address: str, username: str, password: str,
                           timeout_seconds: float = 3.0, *, session_factory=requests.Session) -> dict:
    """Read device media profiles and safe stream URIs; do not persist or activate them."""
    if not 0.5 <= timeout_seconds <= 5 or not username or len(username) > 128 or not password or len(password) > 256:
        raise OnvifInspectionError("Enter credentials and a timeout from 0.5 to 5 seconds.")
    endpoint, source_ip = _device_endpoint(source_address, service_address)
    session = session_factory()
    session.trust_env = False
    try:
        capabilities = _post(session, endpoint, "GetCapabilities", DEVICE, username, password,
                             (("Category", "Media"),), timeout_seconds)
        media_address = _text(capabilities, "XAddr")
        if not media_address:
            raise OnvifInspectionError("The camera did not advertise an ONVIF Media service.")
        media_endpoint, media_ip = _device_endpoint(source_ip, media_address)
        if media_ip != source_ip:
            raise OnvifInspectionError("The Media service address does not match the discovered camera.")
        profile_root = _post(session, media_endpoint, "GetProfiles", MEDIA, username, password,
                             timeout_seconds=timeout_seconds)
        profiles = []
        for token, name, encoding in _profiles(profile_root):
            uri_root = _post(session, media_endpoint, "GetStreamUri", MEDIA, username, password,
                             (("ProfileToken", token),), timeout_seconds)
            uri = _text(uri_root, "Uri")
            safe_uri, uri_status = _safe_stream_uri(uri, source_ip)
            profiles.append({"token": token, "name": name, "encoding": encoding,
                             "stream_uri": safe_uri, "stream_uri_status": uri_status})
        return {"device_ip": source_ip, "profiles": profiles,
                "profile_count": len(profiles), "persisted": False, "activated": False}
    finally:
        session.close()
