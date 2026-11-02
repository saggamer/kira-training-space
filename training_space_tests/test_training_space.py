import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT/"plugins/kira-training-space/runtime"
sys.path.insert(0,str(RUNTIME))
from core import Space,inspect_text
from catalog import CATEGORIES,starter_rows
from train_template import grouped_split
from integrations import redact
from package_tools import plugin_archive

def content(rows): return '\n'.join(json.dumps(r) for r in rows)+'\n'

class TrainingSpaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.space=Space(self.temp.name,ROOT)
    def tearDown(self): self.temp.cleanup()

    def test_starters_validate_and_download(self):
        for c in CATEGORIES:
            data=self.space.content('starter-'+c['id'])
            report=inspect_text(data)
            self.assertEqual(report['rows'],6)
            self.assertTrue(report['ready'],report)
            self.assertTrue(report['warnings']) # explicitly a small sample

    def test_bad_json_and_schema_block_training(self):
        r=inspect_text('{"messages":[]}\nnot json\n')
        self.assertFalse(r['ready']);self.assertEqual(r['invalid_rows'],2)
        item=self.space.import_data('bad','agentic','{"messages":[]}')
        with self.assertRaises(ValueError): self.space.create_plan(item['id'],'Qwen/Qwen2.5-0.5B-Instruct','bad')

    def test_duplicate_payload_ignores_metadata(self):
        rows=starter_rows('agentic')[:1];second=dict(rows[0],group_id='different',id='new')
        r=inspect_text(content(rows+[second]))
        self.assertEqual(r['duplicates'],1);self.assertFalse(r['ready'])

    def test_group_and_payload_leakage(self):
        rows=starter_rows('agentic')[:2]
        rows[1]['split']='validation';rows[1]['group_id']=rows[0]['group_id']
        self.assertTrue(inspect_text(content(rows))['leakage'])
        rows[1]=dict(rows[0],split='test',group_id='new')
        self.assertTrue(inspect_text(content(rows))['leakage'])

    def test_mixed_schema_is_not_ready(self):
        r=inspect_text(content(starter_rows('coding')[:1]+starter_rows('preference')[:1]))
        self.assertFalse(r['ready'])

    def test_import_persists_and_keeps_original_content(self):
        data=self.space.content('starter-coding')
        item=self.space.import_data('<script>name</script>','coding',data)
        reopened=Space(self.temp.name,ROOT)
        self.assertEqual(reopened.content(item['id']),data)
        self.assertEqual(reopened.state()['datasets'][0]['name'],'<script>name</script>')

    def test_plan_does_not_launch_and_bundle_compiles(self):
        with patch('core.subprocess.run') as run:
            p=self.space.create_plan('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','trial')
            run.assert_not_called()
        self.assertEqual(p['status'],'prepared')
        with zipfile.ZipFile(io.BytesIO(self.space.plan_bundle(p['id']))) as z:
            compile(z.read('train.py'),'train.py','exec')
            self.assertEqual(len(z.read('train.jsonl').decode().splitlines()),6)
            self.assertIn('requirements.txt',z.namelist())
        self.assertIn('--keep',p['command']);self.assertIn('--timeout 7200',p['command'])

    def test_array_import_normalized_for_runner(self):
        item=self.space.import_data('array','coding',json.dumps(starter_rows('coding')))
        plan=self.space.create_plan(item['id'],'Qwen/Qwen2.5-0.5B-Instruct','array')
        self.assertEqual(len((Path(plan['directory'])/'train.jsonl').read_text().splitlines()),6)

    def test_modality_mismatch_is_rejected(self):
        for category in ('image','preference'):
            with self.assertRaisesRegex(ValueError,'dedicated'):
                self.space.create_plan('starter-'+category,'Qwen/Qwen2.5-0.5B-Instruct','no')

    def test_evaluation_rows_never_enter_training(self):
        rows=starter_rows('coding');rows[0]['split']='test'
        item=self.space.import_data('evaluation','coding',content(rows))
        with self.assertRaisesRegex(ValueError,'training-split'):
            self.space.create_plan(item['id'],'Qwen/Qwen2.5-0.5B-Instruct','bad')

    def test_grouped_holdout(self):
        rows=starter_rows('coding');rows.append(dict(rows[0],id='duplicate'))
        train,evaluation=grouped_split(rows)
        self.assertFalse({r['group_id'] for r in train}&{r['group_id'] for r in evaluation})
        self.assertEqual(len(train)+len(evaluation),7)

    def test_cloud_start_requires_explicit_confirmation(self):
        p=self.space.create_plan('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','trial')
        with patch('core.subprocess.run') as run:
            with self.assertRaisesRegex(ValueError,'confirm'):
                self.space.start_plan(p['id'])
            run.assert_not_called()

    def test_path_and_model_restrictions(self):
        with self.assertRaises(ValueError):self.space.content('../README.md')
        with self.assertRaises(ValueError):self.space.plan_bundle('../README.md')
        with self.assertRaises(ValueError):self.space.create_plan('starter-coding','foo; touch bad','x')

    def test_redaction(self):
        value=redact('Bearer secret ya29.secret access_token=supersecret')
        self.assertNotIn('secret',value)

    def test_reviewed_notes_are_separate_from_weights(self):
        self.space.add_lesson('Task regression','Compare with the baseline','run:trial/evidence.json')
        self.assertEqual(self.space.state()['lessons'][-1]['source'],'run:trial/evidence.json')
        with self.assertRaises(ValueError):self.space.add_lesson('No evidence','a note','')

    def test_mcp_handshake_tools_and_path_scope(self):
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},
                  {'jsonrpc':'2.0','id':2,'method':'tools/list'},
                  {'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'inspect_dataset','arguments':{'path':'../README.md','category':'coding'}}}]
        proc=subprocess.run([sys.executable,str(RUNTIME/'server.py'),'--mcp','--workspace',self.temp.name],input='\n'.join(map(json.dumps,requests))+'\n',capture_output=True,text=True,check=True)
        replies=list(map(json.loads,proc.stdout.splitlines()))
        self.assertEqual(replies[0]['result']['serverInfo']['name'],'kira-training-space')
        self.assertEqual(len(replies[1]['result']['tools']),10)
        self.assertTrue(replies[2]['result']['isError'])

    def test_plugin_archive_contains_tools_and_no_workspace(self):
        with zipfile.ZipFile(io.BytesIO(plugin_archive())) as z:
            names=z.namelist()
            self.assertIn('kira-training-space/runtime/server.py',names)
            self.assertIn('marketplace.json',names)
            self.assertFalse(any('sqlite' in n or 'workspace/' in n or '__pycache__' in n for n in names))
            manifest=json.loads(z.read('kira-training-space/mcp.json'))
            self.assertIn('${PLUGIN_ROOT}',manifest['mcpServers']['kira-training-space']['args'][0])

    def test_cloud_job_lifecycle_with_fake_cli(self):
        p=self.space.create_plan('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','job')
        fake=subprocess.CompletedProcess(['colab'],0,stdout='Adapter saved',stderr='')
        with patch('core.colab_command',return_value=['fake-colab']),patch('core.subprocess.run',return_value=fake) as run:
            self.space.start_plan(p['id'],True)
            deadline=time.monotonic()+2
            while self.space.get_plan(p['id'])['status'] in {'starting','running'} and time.monotonic()<deadline:
                threading.Event().wait(.01)
            result=self.space.get_plan(p['id'])
            self.assertEqual(result['status'],'completed')
            self.assertIn('--keep',run.call_args.args[0])
            self.assertIn('kira-'+p['id'][:12],run.call_args.args[0])
        with patch('core.colab_call',return_value={'ok':True,'output':'stopped'}):
            self.assertTrue(self.space.stop_plan(p['id'],True)['ok'])
            self.assertTrue(self.space.get_plan(p['id'])['runtime_stopped'])
        with self.assertRaises(ValueError):self.space.start_plan(p['id'],True)

    def test_reopened_app_does_not_claim_job_is_still_running(self):
        p=self.space.create_plan('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','job')
        p.update(status='running',session='kira-trial');self.space.save_plan(p)
        reopened=Space(self.temp.name,ROOT)
        self.assertEqual(reopened.state()['plans'][0]['status'],'connection_lost')

    def test_artifact_retrieval_uses_only_known_plan_session(self):
        p=self.space.create_plan('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','job')
        p.update(status='completed',session='kira-fixed');self.space.save_plan(p)
        def download(project,args,timeout):
            self.assertEqual(args[:4],['download','-s','kira-fixed','/content/kira-adapter.zip'])
            Path(args[4]).write_bytes(b'adapter-test')
            return {'ok':True}
        with patch('core.colab_call',side_effect=download):
            self.assertEqual(self.space.download_artifact(p['id']),b'adapter-test')

    def test_history_persists_without_dataset_contents_or_duplicate_migration(self):
        data=self.space.content('starter-coding')
        item=self.space.import_data('Personal examples','coding',data)
        plan=self.space.create_plan(item['id'],'Qwen/Qwen2.5-0.5B-Instruct','History trial')
        events=self.space.history()
        self.assertEqual(len(events),2)
        self.assertNotIn('Write a Python function',json.dumps(events))
        reopened=Space(self.temp.name,ROOT)
        self.assertEqual(len(reopened.history()),2)
        self.assertEqual({e['entity_id'] for e in reopened.history()},{item['id'],plan['id']})

    def test_legacy_work_is_migrated_once_with_original_time(self):
        item=self.space.import_data('Previous data','coding',self.space.content('starter-coding'))
        with self.space.db() as db:
            original=db.execute('SELECT created FROM datasets WHERE id=?',(item['id'],)).fetchone()[0]
            db.execute('DELETE FROM history')
        reopened=Space(self.temp.name,ROOT)
        self.assertEqual(reopened.history()[0]['created'],original)
        self.assertEqual(len(Space(self.temp.name,ROOT).history()),1)

    def test_source_history_does_not_claim_download_completion(self):
        self.space.record_source_download('hermes','func-calling-singleturn.json')
        event=self.space.history()[0]
        self.assertIn('completion not tracked',event['details']['status'])
        with self.assertRaises(ValueError):self.space.record_source_download('starter-agentic','train.jsonl')

class SoupTrainingTests(unittest.TestCase):
    setUp=TrainingSpaceTests.setUp
    tearDown=TrainingSpaceTests.tearDown
    def test_soup_prepare_execute_and_replay_gate(self):
        backend=self.space.soup_training
        def soup(name,args):
            if name=='train_start':return {'confirmation_token':'secret-once','would_run':'soup train --config snapshot','config_valid':True}
            if name=='train_execute':
                self.assertEqual(args,{'confirmation_token':'secret-once'})
                return {'run_id':'test-run','status':'running'}
            return {'valid':True}
        with patch.object(backend,'call',side_effect=soup):
            p=backend.prepare('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','Soup trial')
            self.assertNotIn('secret-once',json.dumps(self.space.state()))
            with self.assertRaises(ValueError):backend.execute(p['id'],False)
            self.assertEqual(backend.execute(p['id'],True)['status'],'running')
            with self.assertRaises(ValueError):backend.execute(p['id'],True)
        self.assertEqual(self.space.get_plan(p['id'])['backend'],'soup')

    def test_soup_confirmation_lost_on_restart_and_schema_gate(self):
        backend=self.space.soup_training
        with patch.object(backend,'call',return_value={'confirmation_token':'one','would_run':'soup train'}):
            p=backend.prepare('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','Soup trial')
        reopened=Space(self.temp.name,ROOT)
        with self.assertRaisesRegex(ValueError,'restarted'):reopened.soup_training.execute(p['id'],True)
        with self.assertRaisesRegex(ValueError,'Choose SFT'):backend.prepare('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','Bad','dpo')

    def test_soup_execution_failure_consumes_confirmation(self):
        backend=self.space.soup_training
        with patch.object(backend,'call',return_value={'confirmation_token':'one','would_run':'soup train'}):
            p=backend.prepare('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','Soup trial')
        with patch.object(backend,'call',side_effect=ValueError('planned input changed')):
            with self.assertRaisesRegex(ValueError,'changed'):backend.execute(p['id'],True)
        with self.assertRaisesRegex(ValueError,'expired'):backend.execute(p['id'],True)

    def test_soup_export_requires_completed_run_and_fresh_review(self):
        backend=self.space.soup_training
        with patch.object(backend,'call',return_value={'confirmation_token':'train-one','would_run':'soup train'}):
            p=backend.prepare('starter-agentic','Qwen/Qwen2.5-0.5B-Instruct','Export trial')
        with self.assertRaisesRegex(ValueError,'Complete'):backend.export(p['id'],'gguf')
        p['status']='completed';self.space.save_plan(p)
        with self.assertRaisesRegex(ValueError,'Review export'):backend.export(p['id'],'gguf',True)
        with patch.object(backend,'call',return_value={'confirmation_token':'export-one','would_run':'soup export'}) as call:
            review=backend.export(p['id'],'gguf')
            self.assertNotIn('confirmation_token',review)
        with patch.object(backend,'call',return_value={'run_id':'export-run','status':'running'}) as call:
            result=backend.export(p['id'],'gguf',True)
            call.assert_called_once_with('export_execute',{'confirmation_token':'export-one'})
            self.assertEqual(result['run_id'],'export-run')
        with self.assertRaisesRegex(ValueError,'Review export'):backend.export(p['id'],'gguf',True)

    def test_soup_rejects_repeated_groups_before_preflight(self):
        rows=[json.loads(x) for x in self.space.content('starter-agentic').splitlines()]
        rows[1]['group_id']=rows[0]['group_id']
        item=self.space.import_data('Repeated groups','agentic','\n'.join(json.dumps(x) for x in rows))
        with patch.object(self.space.soup_training,'call') as call:
            with self.assertRaisesRegex(ValueError,'grouped split'):self.space.soup_training.prepare(item['id'],'Qwen/Qwen2.5-0.5B-Instruct','Grouped')
            call.assert_not_called()

if __name__=='__main__':unittest.main()
