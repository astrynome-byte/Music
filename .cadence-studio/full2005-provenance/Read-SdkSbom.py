#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read original full2005 SDK SBOM/config data; no DLL/source program execution."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile

MODULES=('qtbase','qtdeclarative','qt5compat','qtnetworkauth','qtshadertools','qtsvg')
INTEREST=re.compile(r'mesa|llvmpipe|llvm|icu|unicode|directx|dxil|dxc|d3dcompiler|msvc|runtime|harfbuzz|freetype|sqlite|openssl',re.I)

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def safe_relative(value):
    p=PurePosixPath(value)
    if not value or value.startswith('/') or '\\' in value or ':' in value or any(x in ('.','..') for x in p.parts):raise ValueError('Unsafe metadata relative path')
    return p

def regular(path,maximum):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>maximum:raise ValueError('Unexpected source data file')
    return path.read_bytes()

def tags(text):
    """Parse package/file SPDX tag-value records, retaining multiline text."""
    packages=[];files=[];current=None;pending=None
    for line in text.splitlines():
        if pending is not None:
            key,values=pending;values.append(line)
            if '</text>' in line:
                if current is not None:current.setdefault(key,[]).append('\n'.join(values))
                pending=None
            continue
        if ': ' not in line:continue
        key,value=line.split(': ',1)
        if key=='PackageName':current={};packages.append(current)
        elif key=='FileName':current={};files.append(current)
        if value.startswith('<text>') and '</text>' not in value:pending=(key,[value]);continue
        if current is not None:current.setdefault(key,[]).append(value)
    if pending is not None:raise ValueError('Unterminated SPDX text field')
    return packages,files

def source_path(name,module):
    value=name.replace('\\','/')
    while value.startswith('./'):value=value[2:]
    parts=value.split('/')
    # Match a whole known module segment or a relative tracked source path.
    # Never resolve a filesystem path from the SBOM.
    indexes=[i for i,p in enumerate(parts) if p==module or p.startswith(module+'-6.10.2')]
    if indexes:value='/'.join(parts[indexes[-1]+1:])
    elif value.startswith('/') or ':' in value or value.startswith('../'):return None
    if not value or any(p in ('','..','.') for p in value.split('/')):return None
    return value

def compare_archive(archive_path,archive_record,file_records):
    if archive_path.stat().st_size!=archive_record['archive_bytes'] or sha(archive_path)!=archive_record['sha256']:raise ValueError('Pinned original Qt archive differs')
    expected={};unmapped=[];conflicts=[];unmapped_count=0
    for row in file_records:
        names=row.get('FileName',[])
        if len(names)!=1:
            unmapped_count+=1
            if len(unmapped)<30:unmapped.append({'FileName':names,'reason':'Expected one source filename'})
            continue
        name=source_path(names[0],archive_record['id'])
        checks={}
        for value in row.get('FileChecksum',[]):
            m=re.fullmatch(r'(SHA1):\s*([0-9a-fA-F]{40})|(SHA256):\s*([0-9a-fA-F]{64})',value)
            if m:
                algorithm=(m[1] or m[3]).lower();digest=(m[2] or m[4]).lower()
                if algorithm in checks and checks[algorithm]!=digest:conflicts.append(name or names[0])
                checks[algorithm]=digest
        if not name or not checks:
            unmapped_count+=1
            if len(unmapped)<30:unmapped.append(names[0])
            continue
        if name in expected and expected[name]!=checks:conflicts.append(name)
        expected[name]=checks
    matched=[];mismatch=[];seen=set();checked_bytes=0
    with tarfile.open(archive_path,'r:gz') as archive:
        for item in archive:
            if not item.isfile():continue
            prefix=archive_record['root']+'/'
            if not item.name.startswith(prefix):raise ValueError('Original source archive root differs')
            name=item.name[len(prefix):]
            if name not in expected:continue
            if name in seen or item.size>32*1024**2:raise ValueError('Unexpected duplicate/oversized source member')
            seen.add(name);checked_bytes+=item.size
            if checked_bytes>1024**3:raise ValueError('Source comparison bound exceeded')
            stream=archive.extractfile(item)
            algorithms={a:hashlib.new(a) for a in expected[name]}
            for block in iter(lambda:stream.read(65536),b''):
                for digest in algorithms.values():digest.update(block)
            if all(algorithms[a].hexdigest()==value for a,value in expected[name].items()):matched.append(name)
            else:mismatch.append(name)
    missing=sorted(set(expected)-seen)
    return {'module':archive_record['id'],'archive_sha256':archive_record['sha256'],'source_commit':archive_record['commit'],
            'SPDX_file_records':len(file_records),'normalized_checksum_records':len(expected),'matching_original_files':len(matched),
            'mismatch_count':len(mismatch),'missing_count':len(missing),'unmapped_record_count':unmapped_count,
            'conflicting_checksum_count':len(conflicts),'conflicting_checksum_paths':conflicts[:30],
            'mismatch_examples':mismatch[:30],'missing_examples':missing[:30],'unmapped_examples':unmapped,
            'original_bytes_compared':checked_bytes,'all_normalized_records_matched':bool(expected) and not mismatch and not missing and not conflicts,
            'all_original_file_records_accounted_for':bool(expected) and not mismatch and not missing and not conflicts and not unmapped_count,
            'scope':'Original source file checksums compared, not a byte-reproducible Qt binary build'}

def package_summary(package):
    selected={k:package[k] for k in ('SPDXID','name','versionInfo','downloadLocation','sourceInfo','licenseConcluded','licenseDeclared','copyrightText','externalRefs','checksums') if k in package}
    for key,value in list(selected.items()):
        if isinstance(value,str) and len(value)>4096:selected[key]=value[:4096]+' [report excerpt; original retained]'
    return selected

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--artifact-root',type=Path,required=True)
    parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();root=args.artifact_root.resolve(strict=True);sources=args.source_root.resolve(strict=True);output=args.output.resolve()
    if output.exists() or output.is_relative_to(root) or output.is_relative_to(sources):raise ValueError('Use a new independent output')
    expected_path=Path(__file__).with_name('sdk-sbom.expected.json');expected=json.loads(regular(expected_path,256*1024))
    candidates=list(root.rglob('binary-origin-metadata.json'))
    if len(candidates)!=1:raise ValueError('One original binary-origin metadata file required')
    origin_path=candidates[0];origin=json.loads(regular(origin_path,512*1024))
    for key in ('driver_commit','executable_sha256','qt_runtime_identity','dll_metadata','sdk_sbom','qmake','sdk_metadata','sdk_notices'):
        if origin.get(key)!=expected[key]:raise ValueError('Original collector differs from authenticated capture: '+key)
    if origin.get('run_id')!='43207550870' or origin.get('errors') or len(origin['qt_runtime_identity'])!=35 or not all(x['identical_to_sdk'] for x in origin['qt_runtime_identity']):raise ValueError('Collector identity/error/Qt match gate failed')
    lock_path=sources/'sources.lock.json'
    if sha(lock_path)!=expected['corresponding_source_lock_sha256']:raise ValueError('Original corresponding-source lock differs')
    output.mkdir();originals=output/'qt-sdk-sbom-originals';originals.mkdir();configs=output/'qt-sdk-config-originals';configs.mkdir()
    shutil.copyfile(origin_path,output/'binary-origin-metadata.original.json')
    report={'schema_version':1,'status':'read-and-measure-original-SDK-material','producer_run_id':43207550870,'executable_sha256':origin['executable_sha256'],
            'original_collector_file_sha256':sha(origin_path),'original_collector_semantically_matches_authenticated_capture':True,
            'expected_profile_sha256':sha(expected_path),'Qt_runtime_DLLs_compared':35,'Qt_runtime_DLLs_identical_to_exact_SDK':35,
            'runtime_source_mapping_counts':dict(Counter(x['source_archive_id'] for x in expected['qt_runtime_source_map'])),
            'sdk_sbom_originals':[],'sdk_config_originals':[],'binary_module_packages':{},'interesting_third_party_packages':[],
            'source_file_comparisons':[],'runtime_file_SBOM_entries':[],'SDK_only_modules_not_automatically_runtime':['qttools','qttranslations','qtwebsockets'],
            'Qt6WebSockets_present_in_actual35_bin_DLLs':any('websocket' in x['file'].lower() for x in origin['qt_runtime_identity']),
            'distribution_approved':False,'application_or_DLL_executed':False,'Qt_rebuilt':False,'errors':[]}
    wanted={Path(x['file']).name.lower():x for x in origin['qt_runtime_identity']}
    for entry in origin['sdk_sbom']['files']:
        relative=safe_relative(entry['retained_path']);path=origin_path.parent/relative
        data=regular(path,16*1024**2)
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:raise ValueError('Actual original SDK SBOM changed: '+str(relative))
        destination=originals/relative.name;destination.write_bytes(data)
        report['sdk_sbom_originals'].append({'file':relative.name,'bytes':len(data),'sha256':entry['sha256']})
        module=relative.name.split('-6.10.2',1)[0]
        if relative.name.endswith('.spdx.json'):
            document=json.loads(data)
            packages=document.get('packages',[])
            if not isinstance(packages,list) or len(packages)>5000:raise ValueError('Unexpected SPDX package bound')
            if module in MODULES:
                report['binary_module_packages'][module]=[package_summary(p) for p in packages]
            for package in packages:
                if INTEREST.search(json.dumps(package_summary(package))):report['interesting_third_party_packages'].append({'document':relative.name,'package':package_summary(package)})
            files=document.get('files',[])
            if not isinstance(files,list) or len(files)>100000:raise ValueError('Unexpected SPDX file bound')
            for file in files:
                name=str(file.get('fileName','')).replace('\\','/').split('/')[-1].lower()
                if name in wanted:report['runtime_file_SBOM_entries'].append({'document':relative.name,'stage_file':wanted[name]['file'],'file_entry':file})
        elif relative.name.endswith('.source.spdx') and module in MODULES:
            packages,files=tags(data.decode('utf-8-sig'))
            record=next(x for x in expected['qt_module_sources'] if x['id']==module)
            comparison=compare_archive(sources/'archives'/record['archive'],record,files)
            comparison['package_reference_fields']=[{k:v for k,v in p.items() if k in ('PackageName','PackageVersion','PackageDownloadLocation','PackageSourceInfo','PackageLicenseDeclared','PackageLicenseConcluded','ExternalRef')} for p in packages[:30]]
            report['source_file_comparisons'].append(comparison)
    for entry in origin['sdk_metadata']:
        if not entry.get('present'):continue
        if entry.get('head_only') or entry.get('printed_bytes')!=entry['bytes']:
            report['sdk_config_originals'].append({'path':entry['path'],'retained':False,'reason':'Original text was bounded/truncated; not reconstructed'})
            continue
        data=entry['text'].encode('utf-8')
        if len(data)!=entry['bytes'] or hashlib.sha256(data).hexdigest()!=entry['sha256']:
            report['sdk_config_originals'].append({'path':entry['path'],'retained':False,'reason':'Text roundtrip did not match original byte hash'})
            continue
        destination=configs/safe_relative(entry['path']);destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(data)
        report['sdk_config_originals'].append({'path':entry['path'],'bytes':len(data),'sha256':entry['sha256'],'retained':True})
    if len(report['sdk_sbom_originals'])!=35 or sum(x['bytes'] for x in report['sdk_sbom_originals'])!=43269076:raise ValueError('Original SBOM set/count differs')
    if {x['module'] for x in report['source_file_comparisons']}!=set(MODULES):report['errors'].append('Not all six delivered Qt source SBOMs compared')
    if any(not x['all_original_file_records_accounted_for'] for x in report['source_file_comparisons']):report['errors'].append('Source SBOM file correspondence has mismatches/missing/unmapped/conflicting evidence to inspect')
    report['source_file_comparisons_all_normalized_matched']=not report['errors']
    report['status']='measured-with-correspondence-gaps' if report['errors'] else 'all-source-SBOM-file-records-accounted-for'
    (output/'sdk-provenance-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'qt35-source-map.json').write_text(json.dumps(expected['qt_runtime_source_map'],indent=2)+'\n',encoding='utf-8')
    # Preserve complete original SBOM/config material in the artifact; print
    # bounded decisions and package license/version/source refs for inspection.
    console={k:v for k,v in report.items() if k not in ('sdk_sbom_originals','binary_module_packages','runtime_file_SBOM_entries','interesting_third_party_packages')}
    def concise(value):
        if isinstance(value,str):return value if len(value)<=768 else value[:768]+' [original retained]'
        if isinstance(value,list):return [concise(v) for v in value[:8]]
        if isinstance(value,dict):return {k:concise(v) for k,v in value.items()}
        return value
    console['binary_module_package_counts']={module:len(rows) for module,rows in report['binary_module_packages'].items()}
    console['binary_module_packages']=concise({module:rows[:16] for module,rows in report['binary_module_packages'].items()})
    console['interesting_third_party_package_count']=len(report['interesting_third_party_packages'])
    console['interesting_third_party_packages']=concise(report['interesting_third_party_packages'][:40])
    console['source_file_comparisons']=concise(report['source_file_comparisons'])
    console['runtime_file_SBOM_entries']=report['runtime_file_SBOM_entries'][:50]
    text=json.dumps(console,ensure_ascii=False,indent=2)
    if len(text)>196608:
        console.pop('binary_module_packages');console.pop('interesting_third_party_packages');text=json.dumps(console,ensure_ascii=False,indent=2)
        if len(text)>196608:raise ValueError('Provenance console report exceeded its explicit bound; originals retained')
    print('CADENCE_FULL2005_SDK_PROVENANCE_BEGIN');print(text);print('CADENCE_FULL2005_SDK_PROVENANCE_END')
    return 2 if report['errors'] else 0
if __name__=='__main__':raise SystemExit(main())
