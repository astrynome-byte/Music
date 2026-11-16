# SPDX-License-Identifier: GPL-3.0-only
"""Rehash the exact authenticated runtime after the GUI/CLI exercise."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
helper=Path(__file__).with_name("write_stage_only_receipt.py")
spec=importlib.util.spec_from_file_location("owned_stage_auth",helper)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
check_tree=module.check_tree

p=argparse.ArgumentParser();p.add_argument('--stage',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
a=p.parse_args();inventory=json.loads(a.inventory.read_text(encoding='utf-8-sig'))
canonical=(json.dumps(inventory,indent=2)+'\n').encode('utf-8')
if hashlib.sha256(canonical).hexdigest()!='7b3b721f01b0a57610b9dcc1cd72bd15e50747dcd751fcd5e31cfbb96a81a4a4':
    raise ValueError('Exact retained2008 inventory required')
if len(inventory['runtime_files'])!=2712:raise ValueError('2712 runtime files required')
check_tree(a.stage,inventory['runtime_files'])
with a.output.open('x',encoding='utf-8') as f:json.dump({'status':'passed_2712_original_runtime_files_unchanged','runtime_files':2712,'application_executed_by_reader':False},f,indent=2);f.write('\n')
