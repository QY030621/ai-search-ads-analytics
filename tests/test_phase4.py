import copy
import io
import json
from pathlib import Path
import pytest
from types import SimpleNamespace
from src.data_validation import read_csv
from src.diagnostics import diagnose
from src.recommendations import prepare,generate,compose,fingerprint,request_ai
from src.recommendation_catalog import CATALOG
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def payload():
    data=read_csv((ROOT/'data/sample_ads.csv').read_bytes())
    return prepare(diagnose(data,'2026-08-28',['C01','C02','C03']))

def choices(events):
    return {f'event_{i}':{'hypotheses':list(CATALOG[e['rule']])[:2], 'experiment':list(CATALOG[e['rule']])[1]} for i,e in enumerate(events)}

def test_only_triggered_diagnostics_no_raw_or_normal(payload):
    assert len(payload['events'])==5
    assert len(payload['checks'])==1
    assert all(e['status']=='触发' for e in payload['events'])
    assert 'current' not in payload['events'][0] and 'previous' not in payload['events'][0]
    assert all(e['rule']!='正常对照' for e in payload['events'])
    json.dumps(payload,allow_nan=False)

def test_different_suggestions_and_immutable_evidence(payload):
    before=copy.deepcopy(payload)
    result=generate(payload)
    assert result['source']=='规则备用建议（非 AI 生成）'
    assert len(result['recommendations'])==5
    assert len({r['sections']['建议做什么实验'] for r in result['recommendations']})==3
    for event,rec in zip(payload['events'],result['recommendations']):
        assert rec['sections']['观察到什么']==event['confirmed']
        assert len(rec['sections'])==6
        assert len(rec['sections']['可能原因'].splitlines())==3
        assert '未验证' in rec['sections']['可能原因']
        assert '立即暂停' not in json.dumps(rec,ensure_ascii=False)
    assert payload==before

def test_successful_api_selection(payload):
    def transport(events,model,key):
        assert events==payload['events'] and model=='test-model'
        return choices(events)
    result=generate(payload,'test-model','fake-secret',True,transport)
    assert result['source']=='AI 辅助建议（受约束生成）'
    assert all(len(r['sections']['可能原因'].splitlines())==2 for r in result['recommendations'])

@pytest.mark.parametrize('exc',[TimeoutError('secret'),OSError('secret'),ValueError('secret')])
def test_failure_safe_fallback(payload,exc):
    def transport(*args): raise exc
    result=generate(payload,'model','key',True,transport)
    assert result['source']=='规则备用建议（非 AI 生成）'
    assert 'secret' not in json.dumps(result)
    assert len(result['recommendations'])==5

@pytest.mark.parametrize('mutation',['missing','extra','numbers','unknown','duplicate','single','experiment','not_dict','schema_echo'])
def test_invalid_output_falls_back(payload,mutation):
    invalid=choices(payload['events'])
    if mutation=='missing': invalid.pop('event_0')
    if mutation=='extra': invalid['event_extra']={}
    if mutation=='numbers': invalid['event_0']['observation']='CTR=99%'
    if mutation=='unknown': invalid['event_0']['hypotheses'][0]='立即暂停广告'
    if mutation=='duplicate': invalid['event_0']['hypotheses']=['relevance','relevance']
    if mutation=='single': invalid['event_0']['hypotheses']=['relevance']
    if mutation=='experiment': invalid['event_0']['experiment']='fabricated'
    if mutation=='not_dict': invalid=[]
    if mutation=='schema_echo':
        from src.recommendations import schema_for
        invalid=schema_for(payload['events'])
    result=generate(payload,'model','key',True,lambda *args:invalid)
    assert result['source']=='规则备用建议（非 AI 生成）'
    assert result['recommendations'][0]['sections']['观察到什么']==payload['events'][0]['confirmed']

def test_normal_and_insufficient_do_not_call_api():
    data=read_csv((ROOT/'data/sample_ads.csv').read_bytes())
    for complete in [True,False]:
        p=prepare(diagnose(data,'2026-08-28',['C01'],complete))
        def forbidden(*args): raise AssertionError('Should not call API')
        assert generate(p,'model','key',True,forbidden)['recommendations']==[]
        assert bool(p['checks']) is (not complete)

def test_configuration_and_cache_key(payload):
    assert '未配置' in generate(payload,use_api=True)['message']
    altered=copy.deepcopy(payload)
    altered['events'][0]['confirmed']='Different evidence'
    assert fingerprint(payload,'model')!=fingerprint(altered,'model')
    assert fingerprint(payload,'model')!=fingerprint(payload,'other')

@pytest.mark.parametrize('base_url',['https://api.openai.com/v1','https://api.deepseek.com'])
def test_http_contract(payload,monkeypatch,base_url):
    def create(**body):
        assert body['store'] is False
        task=json.loads(body['input'])
        assert task['diagnostics']==payload['events']
        assert 'checks' not in task and 'raw' not in task
        assert body['text']['format']['strict'] is True
        assert task['required_event_ids']==[f'event_{i}' for i in range(len(payload['events']))]
        if base_url=='https://api.deepseek.com':
            assert body['reasoning']=={'effort':'none'}
        else:
            assert 'reasoning' not in body
        response={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(choices(payload['events']))}]}]}
        return SimpleNamespace(model_dump=lambda:response)
    class Client:
        def __init__(self,**kwargs):
            assert kwargs==dict(api_key='fake-secret',base_url=base_url,timeout=30,max_retries=0)
            self.responses=SimpleNamespace(create=create)
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setattr('src.recommendations.OpenAI',Client)
    assert request_ai(payload['events'],'model','fake-secret',base_url)==choices(payload['events'])

@pytest.mark.parametrize('response',[{'status':'incomplete'}, {'status':'completed','output':[]},
 {'status':'completed','output':[{'type':'message','content':[{'type':'refusal','refusal':'no'}]}]}])
def test_provider_unusable_response(payload,monkeypatch,response):
    class Client:
        def __init__(self,**kwargs):
            self.responses=SimpleNamespace(create=lambda **kw:SimpleNamespace(model_dump=lambda:response))
        def __enter__(self): return self
        def __exit__(self,*args): pass
    monkeypatch.setattr('src.recommendations.OpenAI',Client)
    assert generate(payload,'model','key',True)['source']=='规则备用建议（非 AI 生成）'

def test_ui_offline_and_stale_result_clear(monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('OPENAI_MODEL',raising=False)
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not app.exception
    assert len(app.session_state['recommendation_result']['recommendations'])==5
    app.button[0].click().run()
    assert not app.exception
    assert '未配置' in app.session_state['recommendation_result']['message']
    app.multiselect[0].set_value(['C01']).run()
    assert not app.exception
    assert app.session_state['recommendation_result']['recommendations']==[]
