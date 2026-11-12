# SPDX-License-Identifier: GPL-3.0-only
"""Data-only tests. No live HTTP, tag, release or repository write is used."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest.mock import patch
import probe


class WorkflowPolicy(unittest.TestCase):
    def test_branch_only_push(self):
        self.assertEqual(probe.audit_events({'push':{'branches':['cadence-studio/windows-build'],'paths':['x/**']},'workflow_dispatch':None}),['push','workflow_dispatch'])
    def test_android_original_policy(self):self.assertEqual(probe.audit_events({'pull_request':None,'push':{'branches':['main','codex/**']},'workflow_dispatch':None}),['pull_request','push','workflow_dispatch'])
    def test_independent_events(self):self.assertEqual(probe.audit_events(['pull_request','workflow_call','schedule']),['pull_request','schedule','workflow_call'])
    def test_forbidden_events(self):
        for event in ('release','create','delete','workflow_run','repository_dispatch','check_run','push'):
            with self.subTest(event=event),self.assertRaises(probe.Blocked):probe.audit_events(event)
    def test_unfiltered_push_and_tags(self):
        for config in (None,{}, {'paths':['x']},{'branches':['main'],'tags':[]},{'branches':['main'],'tags-ignore':['*']},{'branches-ignore':['main']},{'branches':[]},{'branches':'main'}):
            with self.subTest(config=config),self.assertRaises(probe.Blocked):probe.audit_events({'push':config})
    def test_boolean_trigger_is_not_silently_skipped(self):
        with self.assertRaises(probe.Blocked):probe.audit_events({True:None})
    @unittest.skipUnless(shutil.which('ruby'),'Ruby unavailable locally; real Psych parse must run on Ubuntu CI')
    def test_real_psych_literal_on(self):
        text=b'name: test\non:\n  push:\n    branches: [main]\njobs: {}\n'
        self.assertEqual(probe.parse_workflow(text,shutil.which('ruby'),Path(__file__).with_name('parse_workflow.rb')),['push'])
    @unittest.skipUnless(shutil.which('ruby'),'Ruby unavailable locally; aliases/duplicate checks await Ubuntu CI')
    def test_real_psych_refuses_alias_and_duplicate(self):
        for text in (b'on: &a [release]\njobs: *a\n',b'on: push\non: workflow_dispatch\njobs: {}\n'):
            with self.subTest(text=text),self.assertRaises(probe.Blocked):probe.parse_workflow(text,shutil.which('ruby'),Path(__file__).with_name('parse_workflow.rb'))


class HttpParser(unittest.TestCase):
    def call(self,method,code,exit_code,body=b''):
        response=b'HTTP/2.0 '+str(code).encode()+b' Status\r\nContent-Type: application/json\r\n\r\n'+body
        run=subprocess.CompletedProcess([],exit_code,response,b'')
        with patch.object(probe,'command',return_value=run):return probe.api('unused',method,'repos/example',expected=(code,))
    def test_actual_include_shape_201(self):
        receipt,doc=self.call('POST',201,0,b'{"id":17}');self.assertTrue(receipt['succeeded']);self.assertEqual(doc['id'],17)
    def test_expected_404_is_verified_absence_despite_gh_exit1(self):
        receipt,doc=self.call('GET',404,1,b'{"message":"Not Found"}');self.assertTrue(receipt['succeeded']);self.assertIsNone(doc)
    def test_204_no_json(self):self.assertTrue(self.call('DELETE',204,0)[0]['succeeded'])
    def test_error_status_cannot_be_success(self):
        run=subprocess.CompletedProcess([],1,b'HTTP/2.0 403 Forbidden\n\n{}',b'')
        with patch.object(probe,'command',return_value=run):self.assertFalse(probe.api('unused','POST','repos/example',{},(201,))[0]['succeeded'])


class OwnedCleanup(unittest.TestCase):
    def test_exact_owned_resources_deleted_and_absence_checked(self):
        tag='cadence-studio/qa-permission-123-1';head='a'*40;calls=[];counts={}
        def fake(_gh,method,endpoint,payload=None,expected=(200,)):
            calls.append((method,endpoint));key=(method,endpoint);counts[key]=counts.get(key,0)+1
            if method=='DELETE':return {'succeeded':True,'http_status':204},None
            if counts[key]>1:return {'succeeded':True,'http_status':404},None
            if '/releases/' in endpoint:return {'succeeded':True,'http_status':200},{'id':17,'tag_name':tag,'draft':True,'prerelease':True,'assets':[]}
            return {'succeeded':True,'http_status':200},{'ref':'refs/tags/'+tag,'object':{'type':'commit','sha':head}}
        with patch.object(probe,'api',side_effect=fake),patch.object(probe,'verify_main'):r=probe.cleanup('unused',tag,head,17,True)
        self.assertEqual(r['errors'],[]);self.assertTrue(r['release_absence_verified']);self.assertTrue(r['tag_absence_verified'])
        self.assertEqual([x for x in calls if x[0]=='DELETE'],[('DELETE','repos/astrynome-byte/Music/releases/17'),('DELETE','repos/astrynome-byte/Music/git/refs/tags/cadence-studio%2Fqa-permission-123-1')])
    def test_changed_main_stops_cleanup_before_delete(self):
        current={'ref':'refs/tags/owned','object':{'type':'commit','sha':'a'*40}}
        with patch.object(probe,'api',return_value=({'succeeded':True,'http_status':200},current)) as call,patch.object(probe,'verify_main',side_effect=probe.Blocked('main changed')):
            result=probe.cleanup('unused','owned','a'*40,None,True)
        self.assertTrue(result['errors']);self.assertFalse(any(x.args[1]=='DELETE' for x in call.call_args_list))
    def test_changed_tag_not_deleted(self):
        with patch.object(probe,'api',return_value=({'succeeded':True,'http_status':200},{'ref':'refs/tags/owned','object':{'type':'commit','sha':'b'*40}})) as call:
            result=probe.cleanup('unused','owned','a'*40,None,True)
        self.assertTrue(result['errors']);self.assertFalse(any(x.args[1]=='DELETE' for x in call.call_args_list))
    def test_changed_release_not_deleted(self):
        with patch.object(probe,'api',return_value=({'succeeded':True,'http_status':200},{'id':18,'tag_name':'owned','draft':True,'prerelease':True,'assets':[]})) as call:
            result=probe.cleanup('unused','owned','a'*40,17,False)
        self.assertTrue(result['errors']);self.assertFalse(any(x.args[1]=='DELETE' for x in call.call_args_list))
    def test_already_absent_resources_are_checked_without_delete(self):
        with patch.object(probe,'api',return_value=({'succeeded':True,'http_status':404},None)) as call:r=probe.cleanup('unused','owned','a'*40,17,True)
        self.assertEqual(r['errors'],[]);self.assertTrue(r['release_absence_verified']);self.assertTrue(r['tag_absence_verified']);self.assertFalse(any(x.args[1]=='DELETE' for x in call.call_args_list))


if __name__=='__main__':unittest.main()
