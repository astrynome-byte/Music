#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Derive only the OFF routing flag from the real generated candidate header."""
import argparse
import hashlib
import json
from pathlib import Path
from qualify_practice import reference_framework_header


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--header',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    original=args.header.read_bytes()
    derived=reference_framework_header(original)
    args.output.mkdir(parents=False,exist_ok=False)
    (args.output/'muse_framework_config.h').write_bytes(derived)
    receipt={'schema_version':1,'status':'derived-reference-routing-flag-only',
             'source_header':str(args.header.resolve()),'original_sha256':hashlib.sha256(original).hexdigest(),
             'derived_sha256':hashlib.sha256(derived).hexdigest(),
             'only_change':'#define CADENCE_BUILD 1 -> /* #undef CADENCE_BUILD */',
             'official_upstream_application_compiled':False,'all_other_generated_flags_byte_identical':True}
    (args.output/'profile.json').write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,sort_keys=True))
    return 0


if __name__=='__main__':raise SystemExit(main())
