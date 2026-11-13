# SPDX-License-Identifier: GPL-3.0-only
"""Recheck restored original bytes, then write a path-free StageOnly receipt.

This is a new authentication observation, never an original producer report.
No application, DLL, installer, profile, or audio device is opened.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,os,struct

INVENTORY_BYTES=530785
INVENTORY_SHA='7b3b721f01b0a57610b9dcc1cd72bd15e50747dcd751fcd5e31cfbb96a81a4a4'
GUARD_SHA='d2aa8dfb9ae6c8ae09695de3db1f43d3a97a039609b740a7f9d90f2b958158da'

def canonical(value):return (json.dumps(value,indent=2)+'\n').encode('utf-8')
def require(ok,message):
    if not ok:raise ValueError(message)
def sha(path):
    with path.open('rb')as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def plain(path):
    require(path.is_absolute(),'Absolute paths required')
    for p in (path,*path.parents):
        require(not p.is_symlink() and not(p.exists()and getattr(p.stat(),'st_file_attributes',0)&0x400),'Links/reparse paths refused')
    return path
def expected_receipt(plan,guard_sha):
    return {'schema_version':1,'status':'authenticated-original2008-stage-for-GUI-only-known-failed31',
        'scope':'known-failed31-compiled-stage-GUI-only-fullQA-and-MSI-pending',
        'producer':plan['producer'],'source':plan['source'],
        'stage_artifact_id':14031621703,'stage_outer_archive_bytes':306891538,
        'stage_outer_archive_sha256':'8cd00d5df8670837c3b15d3e3bd6e406df290222e404ef88599e4383de048178',
        'stage':plan['stage'],'artifact_files':plan['artifact_files'],
        'fresh_metadata_guard_canonical_sha256':guard_sha,
        'runtime_inventory_canonical_LF_sha256':INVENTORY_SHA,'runtime_files_rehashed':2712,
        'original_companions_rewritten':False,'application_or_installer_executed_by_authentication':False,
        'GUI_validated':False,'full_qualification_complete':False,'MSI':None}
def check_tree(root,expected):
    plain(root);require(root.is_dir(),'Restored runtime directory required')
    actual={}
    for path in root.rglob('*'):
        plain(path)
        if path.is_file():actual[path.relative_to(root).as_posix()]=path
    require(set(actual)==set(expected),'Restored runtime file extent differs')
    for name,path in actual.items():
        row=expected[name]
        require(path.stat().st_size==row['bytes']and sha(path)==row['sha256'],'Restored runtime file bytes differ: '+name)
def verify(plan,guard,restored,data,stage,bundle):
    helper=Path(__file__).with_name('verify_stage_only_producer.py');require(sha(helper)==GUARD_SHA,'Reviewed common metadata guard changed')
    spec=importlib.util.spec_from_file_location('stageonly_guard',helper);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.validate_plan(plan)
    require(guard.get('status')=='eligible-actual-compiled-stage-known-failed31-GUI-only'
        and guard.get('scope')==module.SCOPE and guard.get('producer_run')==module.RUN
        and guard.get('producer_job')==module.JOB and guard.get('driver_commit')==module.DRIVER
        and guard.get('source')==plan['source'] and guard.get('producer_conclusion')=='failure'
        and guard.get('passed_original_steps')==list(range(25,31)) and guard.get('failed_original_step')==31
        and guard.get('stage_artifact_id')==module.ARTIFACT and guard.get('stage_outer_sha256')==module.OUTER_SHA
        and guard.get('stage_executable_sha256')==module.EXE
        and guard.get('stage_extraction_or_application_executed_by_guard')is False
        and guard.get('GUI_validated')is False and guard.get('full_qualification_complete')is False
        and guard.get('MSI')is None and guard.get('GitHub_write_performed')is False,'Fresh API guard report differs')
    inventory=read(data/'runtime-inventory.MEASURED.json');raw=data/'runtime-inventory.MEASURED.json';receipt=read(data/'readback-receipt.json')
    require(sha(raw)==receipt['runtime_inventory_MEASURED_sha256'],'Same-job raw measurement receipt differs')
    normalized=canonical(inventory)
    require(len(normalized)==INVENTORY_BYTES and hashlib.sha256(normalized).hexdigest()==INVENTORY_SHA,'Measured inventory differs from actual Ubuntu readback; LF normalization only applies to this new measurement')
    require(restored.get('status')=='original2008-stage-and-companions-restored-no-execution'
        and restored.get('origin_build_run')==module.RUN and restored.get('origin_build_job')==module.JOB
        and restored.get('origin_overall_conclusion')=='failure' and restored.get('original_source_commit')==module.SOURCE
        and restored.get('original_source_tree')==module.TREE and restored.get('original_ci_commit')==module.CI
        and restored.get('executable_sha256')==module.EXE and restored.get('runtime_file_count')==2712
        and restored.get('runtime_files')==inventory['runtime_files']
        and restored.get('source_or_application_recompiled')is False and restored.get('original_companions_rewritten')is False
        and restored.get('application_or_installer_executed')is False
        and restored.get('original_data_receipt_sha256')==sha(data/'readback-receipt.json')
        and Path(restored['stage_path']).resolve()==stage.resolve()and Path(restored['bundle_path']).resolve()==bundle.resolve(),'Common restoration report differs')
    require(inventory['inner_archive_receipt']=={'bytes':148420143,'sha256':plan['stage']['archive_sha256']},'Original inner archive identity differs')
    check_tree(stage,inventory['runtime_files'])
    for name,row in plan['artifact_files'].items():
        path=plain(bundle/name);require(path.is_file()and path.stat().st_size==row['bytes']and sha(path)==row['sha256'],'Original companion bytes differ: '+name)
        require(restored['bundle_original_files'][name]==row,'Original companion restoration receipt differs: '+name)
    return expected_receipt(plan,hashlib.sha256(canonical(guard)).hexdigest())
def main():
    p=argparse.ArgumentParser();p.add_argument('--selection',type=Path,required=True);p.add_argument('--guard-report',type=Path,required=True);p.add_argument('--restoration-report',type=Path,required=True);p.add_argument('--data-output',type=Path,required=True);p.add_argument('--stage',type=Path,required=True);p.add_argument('--bundle',type=Path,required=True);p.add_argument('--expected-receipt',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    require(os.name=='nt'and struct.calcsize('P')==8 and os.environ.get('GITHUB_ACTIONS')=='true'and os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted'and os.environ.get('GITHUB_REPOSITORY')=='astrynome-byte/Music','Disposable exact native Windows Actions context required')
    temp=Path(os.environ['RUNNER_TEMP']).resolve(strict=True)
    for path in (a.guard_report,a.restoration_report,a.data_output,a.stage,a.bundle,a.output):
        plain(path);require(path.is_relative_to(temp)and path!=temp,'Runtime paths strictly beneath RUNNER_TEMP required')
    require(not a.output.exists()and a.output.parent.is_dir(),'New authentication receipt path required')
    value=verify(read(a.selection),read(a.guard_report),read(a.restoration_report),a.data_output,a.stage,a.bundle)
    output=canonical(value);require(output==a.expected_receipt.read_bytes(),'Runtime observation differs from frozen expected receipt contract')
    a.output.write_bytes(output);print(json.dumps({'status':value['status'],'sha256':hashlib.sha256(output).hexdigest(),'runtime_files_rehashed':2712,'application_executed':False}))
if __name__=='__main__':main()
