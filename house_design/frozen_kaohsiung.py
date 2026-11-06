"""Only the two explicitly archived pre-merge artifacts may resolve historically."""
from __future__ import annotations

from house_design.contracts import ContractError, read_json, sha256_file

MANIFEST = "inputs/references/source-history/20261104-kaohsiung-before-c-stair.json"
EXPECTED = {
    "structured/candidates/kaohsiung-house-options.html": (
        "inputs/references/source-history/20261104-before-c-stair-merge/index.html.txt",
        "1ffc4ee8c94d12141b3feb932e2187230f3d9974ed26d20324f688b7f096199a"),
    "structured/candidates/kaohsiung-house-options-3d.html": (
        "inputs/references/source-history/20261104-before-c-stair-merge/viewer.html.txt",
        "cc8035e2afc4fec3cb417e0ec1053f4324487a0d2c5c865d03701d5d4fdcebc0"),
}


def historical_artifact(root, name, digest):
    if name not in EXPECTED or EXPECTED[name][1] != digest:
        raise ContractError("No historical exception for changed source/artifact: "+name)
    manifest = read_json(root/MANIFEST)
    entries = manifest.get("files", [])
    if (manifest.get("schema") != "house-frozen-kaohsiung-artifacts-v1" or len(entries) != 2
            or {e["original"] for e in entries} != set(EXPECTED)):
        raise ContractError("Unexpected frozen artifact manifest")
    for entry in entries:
        reference, expected = EXPECTED[entry["original"]]
        if entry["reference"] != reference or entry["sha256"] != expected or sha256_file(root/reference) != expected:
            raise ContractError("Historical artifact bytes do not match the frozen SHA-256")
    return root/EXPECTED[name][0]
