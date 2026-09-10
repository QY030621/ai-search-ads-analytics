import copy
import json
from types import SimpleNamespace
import pytest
from src.recommendations import generate,schema_for


def event(rule='CTR 下滑'):
    return {'rule':rule,'confirmed':'CTR 由 5.00% 降至 2.00%。','unknown':'不能确认原因。'}


def install(monkeypatch,responses):
    calls=[]
    class Client:
        def __init__(self,**kwargs):
            assert kwargs['max_retries']==0
            self.responses=SimpleNamespace(create=self.create)
        def __enter__(self): return self
        def __exit__(self,*args): pass
        def create(self,**body):
            calls.append(copy.deepcopy(body))
            value=responses[len(calls)-1]
            result={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(value)}]}]}
            return SimpleNamespace(model_dump=lambda:result)
    monkeypatch.setattr('src.recommendations.OpenAI',Client)
    return calls


def test_ctr_schema_echo_one_repair_preserves_schema_and_evidence(monkeypatch):
    events=[event()]
    valid={'event_0':{'hypotheses':['relevance','mix'],'experiment':'mix'}}
    calls=install(monkeypatch,[schema_for(events),valid])
    result=generate({'events':events},'model','test-only',True,base_url='https://api.deepseek.com')
    assert result['source']=='AI 辅助建议（受约束生成）'
    assert len(calls)==2
    assert calls[0]['text']==calls[1]['text']
    assert calls[0]['input']==calls[1]['input']
    assert result['recommendations'][0]['sections']['观察到什么']==events[0]['confirmed']


def test_repeated_schema_echo_stops_and_falls_back(monkeypatch):
    events=[event()]
    calls=install(monkeypatch,[schema_for(events),schema_for(events)])
    result=generate({'events':events},'model','test-only',True,base_url='https://api.deepseek.com')
    assert len(calls)==2
    assert result['source']=='规则备用建议（非 AI 生成）'
    assert result['recommendations'][0]['sections']['观察到什么']==events[0]['confirmed']


@pytest.mark.parametrize('base,rule,invalid',[
    ('https://api.deepseek.com','CTR 下滑',{'event_0':{'hypotheses':['relevance','mix'],'experiment':'mix','CTR':99}}),
    ('https://api.deepseek.com','CTR 下滑',{'event_0':{'hypotheses':['relevance','fabricated'],'experiment':'relevance'}}),
    ('https://api.openai.com/v1','CTR 下滑',None),
    ('https://api.deepseek.com','有花费但零转化',None),
])
def test_no_retry_for_unrelated_or_fabricated_results(monkeypatch,base,rule,invalid):
    events=[event(rule)]
    calls=install(monkeypatch,[schema_for(events) if invalid is None else invalid])
    result=generate({'events':events},'model','test-only',True,base_url=base)
    assert len(calls)==1 and result['source']=='规则备用建议（非 AI 生成）'
