# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic report/transport mutation tests only; no real MSI or publication."""
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock
import windows_publication as w
import acquire_originals as acquisition
import inspect_delivery as inspection

def synthetic():
    t=json.loads(Path(__file__).with_name('target.json.template').read_text())
    t.update(ready=True,executable_sha256='1'*64,msi_sha256='2'*64)
    t['source']['ci_commit']='3'*40
    t['review'].update(approved=True,reviewed_by='SYNTHETIC DATA, NOT APPROVAL',reviewed_utc='2099-01-01T00:00:00Z')
    t['release'].update(tag='cadence-studio/v4.7.6-cadence.2007-experimental.1',title='Cadence Studio préversion expérimentale')
    for i,a in enumerate(t['artifacts'],1):
        a.update(id=i,name={'stage':'cadence-combined-system-aac-stage-experimental-7-1','delivery':'cadence-combined-system-aac-experimental-7-1','logs':'cadence-combined-system-aac-logs-7-1'}[a['role']],digest='sha256:'+'4'*64,bytes=1,expires_at='2099-01-01T00:00:00Z')
    for k,r in t['reports'].items():r.update(artifact_role='logs',member_path=k+'.json',sha256='5'*64,bytes=1)
    for a in t['assets']:a.update(name=w.ASSET_NAMES[a['kind']],member_path=w.ASSET_NAMES[a['kind']],sha256='6'*64,bytes=1)
    ci=t['source']['ci_commit'];exe=t['executable_sha256']
    checks=[]
    pairs={(f,s) for f in ('piano','voice','guitar','percussion','ensemble') for s in ('import-save-native','reopen-native','export-mxl','export-pdf','export-svg','export-png','export-mid','export-wav','export-flac','export-mp3')}
    pairs|={('ensemble','extract-native-parts')}|{('ensemble',f'part-{i:02d}-reopen-pdf') for i in range(1,7)}
    for f,s in sorted(pairs):checks.append({'fixture':f,'stage':s,'passed':True,'exit_code':0,'outputs':[{'bytes':1,'sha256':'7'*64,'audio':{'passed':True}}]})
    note={'stage_path':'share/notices/example.txt','bytes':1,'sha256':'8'*64}
    d={'bootstrap':{'original_source_commit':w.SOURCE,'source_tree':w.TREE,'ci_source_commit':ci},
       'build':{'source_commit':ci,'source_dirty_at_build':False,'executable_sha256':exe},
       'stage_manifest':{'original_source_commit':w.SOURCE,'source_commit':ci,'source_tree':w.TREE,'build_number':2007,'run_number':7,'run_attempt':1,'qt_version':'6.10.2','executable_sha256':exe},
       'release_manifest':{'source_commit':ci,'source_tree':w.TREE,'build_number':2007,'installer':w.PREFIX+'.msi'},
       'cli':{'executable_sha256':exe,'version_exit_code':0,'checks':checks},
       'notices':{'passed':True,'status':'passed_staged_notice_bytes_and_development_archive_exclusion','executable_sha256':exe,'errors':[],'notices':[note],'notice_files_verified':1,'mnxdom_development_archives_found':[],'corresponding_source_archives_found_in_runtime':[],'corresponding_sources_remain_companion_files':True,'corresponding_source_report_sha256':'5'*64},
       'components':{'source_archives_verified':True,'errors':[]},
       'icu_policy':{'status':'local-forwarder-absent-and-system20exports-proved','local_forwarder_absent':True,'qtcore_sha256':w.QTCORE_SHA,'candidate_executable_sha256':exe,'export_report_sha256':'5'*64},
       'icu_exports':{'status':'complete-static-export-evidence','complete':True,'host_is_windows':True,'local_forwarder_omission_export_gate_passed':True,'errors':[],'resolutions':[{'complete':True} for _ in range(20)]}}
    d['msi']={'status':'passed','source_commit':ci,'msi_sha256':t['msi_sha256'],'installed_executable_sha256':exe,'product_version':'4.7.6.2007','upgrade_code':'{319B992F-470A-465B-9A79-6B0CBFC7D6C7}','summary_template':'x64;1033','install_exit_code':0,'uninstall_exit_code':3010,'product_removed':True,'cli_exit_code':0,'cli_version_matched':True,'error':None,'cleanup_error':None,'gui_requested':True,'gui_tested':True,'gui_startup_observed':True,'clean_exit_observed':True,'require_system_icu':True,'installed_local_icuuc_absent':True,'expected_product_version':'4.7.6.2007','gui_status':'startup_observed_closed_cleanly','gui_exit_status':0,'installed_icu_absence_checks':[{'phase':p,'absent':True} for p in ('before-installed-cli','before-installed-gui')],'notice_verification_requested':True,'installed_notices_verified':1,'installed_notices':[{'path':note['stage_path'],'bytes':1,'sha256':'8'*64}]}
    return t,d

class Guards(unittest.TestCase):
    def test_template_refused(self):
        with self.assertRaises(ValueError):w.validate_target(json.loads(Path(__file__).with_name('target.json.template').read_text()))
    def test_synthetic_report_structure_only(self):
        t,d=synthetic();w.validate_target(t);w.check_reports(t,d)
    def test_report_negative_mutations(self):
        mutations=[('msi','product_version','4.7.6.2006'),('msi','msi_sha256','9'*64),('msi','installed_local_icuuc_absent',False),('msi','gui_tested',False),('msi','uninstall_exit_code',True),('notices','installed_notices_verified',0),('notices','notice_files_verified',True),('components','source_archives_verified',False),('icu_policy','candidate_executable_sha256','9'*64),('icu_exports','complete',False),('icu_exports','resolutions',[])]
        for role,key,value in mutations:
            with self.subTest(role=role,key=key):
                t,d=synthetic()
                if key=='installed_notices_verified':d['msi'][key]=value
                else:d[role][key]=value
                with self.assertRaises(ValueError):w.check_reports(t,d)
    def test_cli_coverage_and_audio(self):
        for kind in ('missing','duplicate','FAIL','audio'):
            with self.subTest(kind=kind):
                t,d=synthetic();rows=d['cli']['checks']
                if kind=='missing':rows.pop()
                elif kind=='duplicate':rows[0]=copy.deepcopy(rows[1])
                elif kind=='FAIL':rows[0]['passed']=False
                else:next(x for x in rows if x['stage']=='export-wav')['outputs'][0]['audio']['passed']=False
                with self.assertRaises(ValueError):w.check_reports(t,d)
    def test_target_claims_and_identity(self):
        for key,value in [('ready','true'),('build_number','2007'),('msi_sha256',None)]:
            with self.subTest(key=key):
                t,_=synthetic();t[key]=value
                with self.assertRaises(ValueError):w.validate_target(t)
        t,_=synthetic();t['limitations']['paid_equivalence_complete']=True
        with self.assertRaises(ValueError):w.validate_target(t)
        t,_=synthetic();t['release']['title']='Cadeau final expérimental'
        with self.assertRaises(ValueError):w.validate_target(t)
        t,_=synthetic();t['artifacts'][1]['id']=t['artifacts'][0]['id']
        with self.assertRaises(ValueError):w.validate_target(t)
    def test_windows_paths_refused(self):
        for name in ('../escape','C:/stream','ok:ads','a//b','a/./b','a/../b','\\server\\file','/absolute'):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):w.relative(name)
    def test_deterministic_stored_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            r=Path(temporary);file=r/'notice.txt';file.write_text('Synthetic notice only\n');w.stored_zip(r/'a.zip',{'notice.txt':file});w.stored_zip(r/'b.zip',{'notice.txt':file})
            self.assertEqual((r/'a.zip').read_bytes(),(r/'b.zip').read_bytes())
    def test_dataonly_refuses_running_producer_before_discovery(self):
        # Synthetic HTTP return shape only. No opener reaches a real network.
        calls=[]
        run={'id':w.RUN,'head_sha':w.DRIVER,'repository':{'full_name':'astrynome-byte/Music'},'status':'in_progress','conclusion':None,'run_number':7,'run_attempt':1}
        def open_fake(request,timeout):
            calls.append((request.get_method(),request.full_url));return io.BytesIO(json.dumps(run).encode())
        with tempfile.TemporaryDirectory() as temporary:
            destination=Path(temporary)/'new-originals'
            environment=SimpleNamespace(name='nt',environ={'GITHUB_ACTIONS':'true','RUNNER_ENVIRONMENT':'github-hosted','RUNNER_TEMP':temporary,'GH_TOKEN':'SYNTHETIC-NOT-A-TOKEN'})
            with mock.patch.object(acquisition,'os',environment),mock.patch.object(acquisition.urllib.request,'build_opener',return_value=SimpleNamespace(open=open_fake)):
                with self.assertRaises(ValueError):acquisition.acquire_from_producer(destination)
            self.assertFalse(destination.exists())
        self.assertEqual(len(calls),1);self.assertEqual(calls[0][0],'GET');self.assertTrue(calls[0][1].endswith('/actions/runs/'+str(w.RUN)))
    def test_dataonly_discovers_actual_record_shapes_without_target(self):
        rows=[]
        for i,(role,name) in enumerate(acquisition.EXPECTED_NAMES.items(),1):
            rows.append({'id':i,'name':name,'workflow_run':{'id':w.RUN,'head_sha':w.DRIVER},'expired':False,'digest':'sha256:'+'a'*64,'size_in_bytes':1,'expires_at':'2099-01-01T00:00:00Z'})
        listing={'total_count':3,'artifacts':rows}
        result=acquisition.observed_artifacts(listing);self.assertEqual({x['role'] for x in result},{'stage','delivery','logs'})
        for change in ('missing','duplicate','wrong-producer'):
            with self.subTest(change=change):
                bad=copy.deepcopy(listing)
                if change=='missing':bad['artifacts'].pop();bad['total_count']=2
                elif change=='duplicate':bad['artifacts'].append(copy.deepcopy(bad['artifacts'][0]));bad['total_count']=4
                else:bad['artifacts'][0]['workflow_run']['head_sha']='b'*40
                with self.assertRaises(ValueError):acquisition.observed_artifacts(bad)
    def test_dataonly_computes_ten_receipts_and_refuses_ambiguity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for kind,(role,suffix) in inspection.REPORT_SUFFIXES.items():
                path=root/role/'_temp'/suffix;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps({'SYNTHETIC_REPORT_ONLY':kind}))
            refs,originals=inspection.observe_reports(root)
            self.assertEqual(set(refs),set(w.REPORTS));self.assertEqual(len(refs),10)
            for kind,path in originals.items():self.assertEqual(refs[kind]['sha256'],w.digest(path))
            duplicate=root/'stage/duplicate/stage-manifest.json';duplicate.parent.mkdir();duplicate.write_text('{}')
            with self.assertRaises(ValueError):inspection.observe_reports(root)

if __name__=='__main__':unittest.main()
