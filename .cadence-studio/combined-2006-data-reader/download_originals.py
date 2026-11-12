# SPDX-License-Identifier: GPL-3.0-only
"""Read-only acquisition of exactly three original Actions ZIPs; no payload execution."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

RUN = 43233124321
DRIVER = "5d9cd789149de212c2fe9cf51ea3dddd2d48867c"
ARTIFACTS = {
    "stage": (13955301913, "cadence-combined-system-aac-stage-experimental-6-1", 306492266,
              "c93aa9eb68a5a7e21b80c19b150d9d9731532e91d2abb778f87342317417443b"),
    "delivery": (13955727693, "cadence-combined-system-aac-experimental-6-1", 590890698,
                 "ea13e382583ed31368c768916aec83ff282f61d325408aa6b0e734dc51591081"),
    "logs": (13956760224, "cadence-combined-system-aac-logs-6-1", 11719909,
             "d7fa379070f0f2275dbbe5244764e6bb5815f73413dd347056f6f5cf897048bf"),
}

def require(ok, message):
    if not ok:
        raise RuntimeError(message)

class PublicRedirectOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        parsed = urllib.parse.urlparse(new_url)
        require(parsed.scheme == "https" and not parsed.username and not parsed.password
                and parsed.hostname and (parsed.hostname in ("api.github.com", "github.com")
                or parsed.hostname.endswith(".githubusercontent.com")
                or parsed.hostname.endswith(".blob.core.windows.net")), "Unexpected artifact redirect destination")
        # New Request deliberately forwards no Authorization, cookie or credential.
        return urllib.request.Request(new_url, headers={"User-Agent": "Cadence-DataOnly-Reader/1.0"}, method="GET")

def authenticated(opener, endpoint, token):
    require(endpoint.startswith("repos/astrynome-byte/Music/"), "Only this repository may be read")
    return opener.open(urllib.request.Request("https://api.github.com/" + endpoint,
        headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                 "User-Agent": "Cadence-DataOnly-Reader/1.0", "X-GitHub-Api-Version": "2022-11-28"}, method="GET"), timeout=120)

def metadata(opener, endpoint, token):
    with authenticated(opener, endpoint, token) as response:
        raw = response.read(4194305)
    require(len(raw) <= 4194304, "Metadata exceeds bound")
    return json.loads(raw)

def acquire(root: Path) -> dict:
    token = os.environ.get("GH_TOKEN", "")
    require(token, "Ephemeral Actions read token required")
    root.mkdir(parents=True, exist_ok=False)
    opener = urllib.request.build_opener(PublicRedirectOnly())
    run = metadata(opener, "repos/astrynome-byte/Music/actions/runs/" + str(RUN), token)
    require(run["id"] == RUN and run["head_sha"] == DRIVER and run["status"] == "completed"
            and run["conclusion"] == "success" and run["repository"]["full_name"] == "astrynome-byte/Music"
            and run["run_number"] == 6 and run["run_attempt"] == 1, "Actual producer identity/result differs")
    receipts = {}
    for kind, (identifier, name, size, digest) in ARTIFACTS.items():
        item = metadata(opener, "repos/astrynome-byte/Music/actions/artifacts/" + str(identifier), token)
        require(item["id"] == identifier and item["name"] == name and item["size_in_bytes"] == size
                and item["digest"] == "sha256:" + digest and item["expired"] is False
                and item["workflow_run"]["id"] == RUN and item["workflow_run"]["head_sha"] == DRIVER,
                "Original artifact identity/digest/availability differs")
        destination = root / (kind + ".zip")
        checksum = hashlib.sha256(); count = 0; deadline = time.monotonic() + 1200
        with authenticated(opener, "repos/astrynome-byte/Music/actions/artifacts/" + str(identifier) + "/zip", token) as response, destination.open("xb") as output:
            while True:
                require(time.monotonic() < deadline, "Original artifact acquisition deadline exceeded")
                chunk = response.read(1048576)
                if not chunk: break
                count += len(chunk); require(count <= size, "Original archive exceeds exact byte bound")
                checksum.update(chunk); output.write(chunk)
        require(count == size and checksum.hexdigest() == digest, "Actual downloaded original ZIP size/SHA differs")
        receipts[kind] = {"id": identifier, "name": name, "bytes": count, "sha256": digest,
                          "original_outer_zip_digest_recomputed": True, "path": str(destination), "expires_at": item["expires_at"]}
    return {"schema_version": 1, "producer_run_id": RUN, "driver_commit": DRIVER, "artifacts": receipts,
            "redirect_authorization_forwarded": False, "application_or_msi_executed": False}
