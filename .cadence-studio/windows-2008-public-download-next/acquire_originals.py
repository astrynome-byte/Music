# SPDX-License-Identifier: GPL-3.0-only
"""GET five exact retained2008 source-stage, QA and MSI ZIPs; execute none."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request
sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows_publication import validate_target, require, plain, extract_zip, RUN, DRIVER, JOB, RUN_NUMBER, RUN_ATTEMPT, MAX, assert_selection, expected_artifact_names, producer_context, ARTIFACT_ROLES, EXPECTED

from verify_stage_only_producer import validate_metadata as validate_original_stage_metadata


def observed_artifacts(listings):
    rows = []
    for role, name in expected_artifact_names().items():
        origin = producer_context(role); listing = listings[origin["run_id"]]
        items = listing.get("artifacts")
        require(isinstance(items, list) and type(listing.get("total_count")) is int
                and listing["total_count"] == len(items) and len(items) <= 100, "Complete bounded artifact listing required")
        found = [x for x in items if x.get("name") == name]
        require(len(found) == 1, "One original retained artifact required for " + role)
        item = found[0]
        require(type(item.get("id")) is int and item["id"] > 0 and item.get("workflow_run", {}).get("id") == origin["run_id"]
                and item["workflow_run"].get("head_sha") == origin["driver_commit"] and item.get("expired") is False
                and isinstance(item.get("digest"), str) and re.fullmatch(r"sha256:[a-f0-9]{64}", item["digest"])
                and type(item.get("size_in_bytes")) is int and 0 < item["size_in_bytes"] <= MAX
                and isinstance(item.get("expires_at"), str), "Observed artifact identity/origin/digest is invalid")
        rows.append({"role":role,"id":item["id"],"name":name,"run_id":origin["run_id"],"digest":item["digest"],
                     "bytes":item["size_in_bytes"],"expires_at":item["expires_at"]})
    require(len({x["id"] for x in rows}) == len(ARTIFACT_ROLES), "Artifact identifiers must be distinct")
    return rows

class PublicRedirectOnly(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        parsed = urllib.parse.urlparse(new_url)
        require(parsed.scheme == "https" and not parsed.username and not parsed.password and parsed.hostname
                and (parsed.hostname in ("api.github.com", "github.com") or parsed.hostname.endswith(".githubusercontent.com")
                     or parsed.hostname.endswith(".blob.core.windows.net")), "Unexpected artifact redirect destination")
        return urllib.request.Request(new_url, headers={"User-Agent": "Cadence-DataOnly-Reader/1.0"}, method="GET")

def acquire_from_producer(output, declared_artifacts=None, inspect_only=True):
    assert_selection()
    require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.name == "nt", "Disposable hosted Windows acquisition required")
    plain(output); temporary = Path(os.environ["RUNNER_TEMP"]).resolve(strict=True)
    require(output.is_absolute() and output.resolve().is_relative_to(temporary) and not output.exists(), "New acquisition path under RUNNER_TEMP required")
    token = os.environ.get("GH_TOKEN", ""); require(token, "Ephemeral read token required")
    opener = urllib.request.build_opener(PublicRedirectOnly())
    def request(endpoint):
        require(endpoint.startswith("repos/astrynome-byte/Music/actions/"), "Only this repository's Actions resources may be read")
        return opener.open(urllib.request.Request("https://api.github.com/" + endpoint, headers={"Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json", "User-Agent": "Cadence-DataOnly-Reader/1.0", "X-GitHub-Api-Version": "2022-11-28"}, method="GET"), timeout=120)
    def metadata(endpoint):
        with request(endpoint) as response: raw = response.read(4_194_305)
        require(len(raw) <= 4_194_304, "Metadata exceeds bound"); return json.loads(raw)
    origins = {}
    for role in ("stage", "qa_logs", "delivery"):
        origin = producer_context(role)
        run = metadata("repos/astrynome-byte/Music/actions/runs/" + str(origin["run_id"]))
        job = metadata("repos/astrynome-byte/Music/actions/jobs/" + str(origin["job_id"]))
        require(run["id"] == origin["run_id"] and run["head_sha"] == origin["driver_commit"]
                and run["repository"]["full_name"] == "astrynome-byte/Music" and run["status"] == "completed"
                and run["run_number"] == origin["run_number"] and run["run_attempt"] == origin["run_attempt"], "Actual retained producer identity differs")
        if role == "stage":
            plan = json.loads(Path(__file__).with_name("stage-only-provenance.json").read_text())
            item = metadata("repos/astrynome-byte/Music/actions/artifacts/" + str(EXPECTED["original_artifacts"]["stage"]["id"]))
            original_guard = validate_original_stage_metadata(plan, run, job, item)
        else:
            require(run["conclusion"] == "success" and job["id"] == origin["job_id"]
                    and job["run_id"] == origin["run_id"] and job["status"] == "completed" and job["conclusion"] == "success"
                    and "windows-2022" in job["labels"], "Actual successful retained QA/MSI Windows2022 run/job required")
        origins[origin["run_id"]] = {"selection":origin,"run_conclusion":run["conclusion"],"job_conclusion":job["conclusion"]}
    artifacts = declared_artifacts
    if artifacts is None:
        listings = {run_id:metadata("repos/astrynome-byte/Music/actions/runs/" + str(run_id) + "/artifacts?per_page=100") for run_id in origins}
        artifacts = observed_artifacts(listings)
    require(isinstance(artifacts,list) and len(artifacts) == len(ARTIFACT_ROLES)
            and {r.get("role") for r in artifacts} == set(ARTIFACT_ROLES)
            and len({r.get("id") for r in artifacts}) == len(ARTIFACT_ROLES), "Five distinct expected artifact slots required")
    for row in artifacts:
        origin = producer_context(row["role"])
        require(row.get("run_id") == origin["run_id"] and row.get("name") == expected_artifact_names()[row["role"]]
                and type(row.get("id")) is int and row["id"] > 0
                and isinstance(row.get("digest"),str) and re.fullmatch(r"sha256:[a-f0-9]{64}",row["digest"])
                and type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX, "Invalid declared retained artifact")
        if row["role"] in EXPECTED["original_artifacts"]:
            original = EXPECTED["original_artifacts"][row["role"]]
            require(row["id"] == original["id"] and row["digest"] == original["digest"] and row["bytes"] == original["size_in_bytes"], "Known original stage/log artifact changed")
    output.mkdir(parents=True)
    for row in artifacts:
        origin = producer_context(row["role"])
        endpoint = "repos/astrynome-byte/Music/actions/artifacts/" + str(row["id"])
        item = metadata(endpoint)
        require(item["id"] == row["id"] and item["name"] == row["name"] and item["digest"] == row["digest"]
                and item["size_in_bytes"] == row["bytes"] and item["workflow_run"]["id"] == origin["run_id"]
                and item["workflow_run"]["head_sha"] == origin["driver_commit"] and item["expired"] is False
                and item["expires_at"] == row["expires_at"], "Actual artifact identity/digest/expiry differs")
        expires = datetime.datetime.fromisoformat(item["expires_at"].replace("Z", "+00:00"))
        require(expires > datetime.datetime.now(datetime.timezone.utc), "Original artifact expired")
        archive = output / (row["role"] + "-original.zip"); measured = hashlib.sha256(); count = 0; deadline = time.monotonic() + 1200
        with request(endpoint + "/zip") as response, archive.open("xb") as destination:
            while True:
                require(time.monotonic() < deadline, "Artifact download deadline exceeded")
                data = response.read(1048576)
                if not data: break
                count += len(data); require(count <= row["bytes"], "Original artifact exceeds approved byte bound")
                measured.update(data); destination.write(data)
        require(count == row["bytes"] and "sha256:" + measured.hexdigest() == row["digest"], "Original outer ZIP digest differs")
        extract_zip(archive, output / row["role"])
    receipt = {"schema_version": 1, "producer_run": RUN, "producer_driver_commit": DRIVER,
               "original_outer_digests_recomputed": True, "artifacts": artifacts,
               "producer_job_id": JOB, "producer_windows2022_job_passed": True,
               "all_retained_producers_authenticated":True,"retained_origins":list(origins.values()),"original_failed_stage_guard":original_guard,
               "redirect_authorization_forwarded": False, "application_or_installer_executed": False,
               "inspect_only_preparation": inspect_only}
    (output / "artifact-acquisition.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt

def acquire(target, output, inspect_only=False):
    validate_target(target, approval=not inspect_only)
    if inspect_only: require(target.get("ready") is False, "Inspect-only acquisition requires a nonactivating ready=false document")
    return acquire_from_producer(output, target["artifacts"], inspect_only)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--target", type=Path, required=True); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inspect-only", action="store_true", help="Read-only preparation from actual artifact receipts with ready=false; never publish")
    args = parser.parse_args(); print(json.dumps(acquire(json.loads(args.target.read_text(encoding="utf-8-sig")), args.output, args.inspect_only)))
