"""Optional Soup execution bridge. Tokens stay in this process, never history."""
import json
from pathlib import Path
import queue
import subprocess
import threading
from integrations import soup_command, redact

class SoupSession:
    def __init__(self, workspace):
        cmd=soup_command()
        if not cmd: raise ValueError('Install Soup before choosing the Soup backend')
        cmd=[*cmd]
        if '--allow-execute' not in cmd: cmd.append('--allow-execute')
        self.proc=subprocess.Popen(cmd,cwd=workspace,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        self.messages=queue.Queue();self.lock=threading.Lock();self.sequence=0
        def read():
            for line in self.proc.stdout:
                try:self.messages.put(json.loads(line))
                except json.JSONDecodeError:pass
            self.messages.put({'eof':True})
        threading.Thread(target=read,daemon=True).start()
        self.request('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'kira-training-space','version':'0.3.0'}})
        self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');self.proc.stdin.flush()
    def request(self, method, params):
        with self.lock:
            self.sequence+=1;rid=self.sequence
            self.proc.stdin.write(json.dumps({'jsonrpc':'2.0','id':rid,'method':method,'params':params})+'\n');self.proc.stdin.flush()
            while True:
                try:msg=self.messages.get(timeout=45)
                except queue.Empty:raise ValueError('Soup timed out; restart the app and prepare a new plan') from None
                if msg.get('eof'):raise ValueError('Soup disconnected; prepare a new plan after restarting')
                if msg.get('id')==rid:
                    if 'error' in msg:raise ValueError(str(msg['error']))
                    return msg['result']
    def call(self,name,args):
        if name not in {'data_inspect','data_validate','train_start','train_execute','runs_show','export','export_execute','profile'}:raise ValueError('Unsupported Soup operation')
        result=self.request('tools/call',{'name':name,'arguments':args})
        text='\n'.join(c.get('text','') for c in result.get('content',[]))
        if result.get('isError'):raise ValueError(redact(text))
        try:return json.loads(text)
        except json.JSONDecodeError:return {'text':redact(text)}

class SoupTraining:
    def __init__(self,space):self.space=space;self.session=None;self.tokens={};self.lock=threading.Lock()
    def call(self,name,args):
        if self.session is None:self.session=SoupSession(self.space.workspace)
        return self.session.call(name,args)
    def prepare(self,dataset_id,model,name,task='sft'):
        import uuid
        from core import inspect_text,now
        import re
        if task not in {'sft','dpo'}:raise ValueError('This integration supports Soup text SFT and DPO; other modalities need a compatible Soup recipe')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',model):raise ValueError('Use a Hugging Face model ID')
        content=self.space.content(dataset_id);report=inspect_text(content)
        if not report['ready']:raise ValueError('Resolve dataset inspection failures before training')
        if (task=='dpo') != (report['schema']=='dpo'):raise ValueError('Choose SFT for chat/instruction data or DPO for preference data')
        rows=json.loads(content) if content.lstrip().startswith('[') else [json.loads(x) for x in content.splitlines() if x.strip()]
        if any(str(r.get('split','train')).lower() not in {'train','training'} for r in rows):raise ValueError('Supply only the source training split; keep evaluation data separate')
        groups=[str(r.get('group_id')) for r in rows if r.get('group_id') is not None]
        if len(groups)!=len(set(groups)):raise ValueError('Repeated evaluation groups need a grouped split recipe; this guided Soup split requires unique groups')
        if len(rows)<4:raise ValueError('At least four training rows are required')
        identifier=uuid.uuid4().hex;directory=self.space.workspace/'plans'/identifier;directory.mkdir()
        data=directory/'train.jsonl';data.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n')
        config={'base':model,'task':task,'data':{'train':str(data),'format':'dpo' if task=='dpo' else 'auto','val_split':0.2,'max_length':1024},'training':{'epochs':1,'lr':0.0002,'batch_size':1,'lora':{'r':8,'alpha':16,'target_modules':'auto'}},'output':str(directory/'adapter')}
        configpath=directory/'soup.json';configpath.write_text(json.dumps(config,indent=2))
        inspection=self.call('data_inspect',{'data':str(data)})
        validation=self.call('data_validate',{'data':str(data)})
        review=self.call('train_start',{'config':str(configpath)})
        token=review.pop('confirmation_token',None)
        if not token:raise ValueError('This Soup version cannot execute training; upgrade to a version supporting --allow-execute')
        self.tokens[identifier]=token
        plan={'id':identifier,'name':str(name or 'Soup fine-tune')[:160],'dataset_id':dataset_id,'model':model,'gpu':'Local Soup runtime','backend':'soup','task':task,'status':'prepared','created':now(),'directory':str(directory),'report':report,'config':config,'command':review['would_run'],'inspection':inspection,'validation':validation,'checks':['Soup owns the complete training process','Review hardware and install compatible Soup trainer dependencies','Soup creates a 20% validation split; task evaluation remains required','Single-use confirmation expires after five minutes; prepare again if expired'],'note':'Runs locally through Soup, not Colab. Model weights may be downloaded. Keep the app open to monitor the run.','review':review}
        with self.space.db() as db:db.execute('INSERT INTO plans VALUES(?,?,?)',(identifier,json.dumps(plan),now()))
        self.space.record_event('training','Soup training plan prepared: '+plan['name'],identifier,{'backend':'soup','task':task,'model':model})
        return plan
    def execute(self,identifier,confirmed=False):
        if confirmed is not True:raise ValueError('Review and authorize this Soup training run first')
        with self.lock:
            plan=self.space.get_plan(identifier)
            if plan.get('backend')!='soup' or plan['status']!='prepared':raise ValueError('Prepare a new Soup plan before execution')
            token=self.tokens.pop(identifier,None)
            if not token:raise ValueError('Confirmation expired or app restarted; prepare a new plan')
            result=self.call('train_execute',{'confirmation_token':token})
            plan.update(status=result['status'],soup_run_id=result['run_id'],log_path=result.get('log_path'))
            self.space.save_plan(plan);self.space.record_event('training','Soup run started: '+plan['name'],identifier,{'run_id':result['run_id']})
            return plan
    def status(self,identifier):
        plan=self.space.get_plan(identifier)
        if plan.get('backend')!='soup' or not plan.get('soup_run_id'):raise ValueError('No Soup run exists for this plan')
        record=self.call('runs_show',{'run_id':plan['soup_run_id']})
        previous=plan['status'];plan['status']=record.get('status',previous);plan['soup_run']=record
        path=Path(plan.get('log_path') or '.')
        if path.is_file() and path.resolve().is_relative_to(self.space.workspace):
            with path.open('rb') as stream:stream.seek(max(0,path.stat().st_size-16000));plan['log']=redact(stream.read().decode(errors='replace'))
        self.space.save_plan(plan)
        if previous!=plan['status']:self.space.record_event('training','Soup run '+plan['status'],identifier,{'run_id':plan['soup_run_id']})
        return plan
    def export(self,identifier,fmt,confirmed=False):
        plan=self.space.get_plan(identifier)
        if plan.get('backend')!='soup' or plan['status']!='completed':raise ValueError('Complete Soup training before exporting')
        key=identifier+':export'
        if confirmed is not True:
            if fmt not in {'gguf','onnx','awq','gptq','merged','safetensors'}:raise ValueError('Choose a supported export format')
            result=self.call('export',{'model':plan['config']['output'],'format':fmt,'output':str(self.space.workspace/'plans'/identifier/('export-'+fmt))})
            self.tokens[key]=result.pop('confirmation_token');return result
        token=self.tokens.pop(key,None)
        if not token:raise ValueError('Review export again before executing')
        result=self.call('export_execute',{'confirmation_token':token})
        self.space.record_event('training','Soup export started',identifier,{'run_id':result['run_id']})
        return result
