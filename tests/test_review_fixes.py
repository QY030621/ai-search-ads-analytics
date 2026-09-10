from pathlib import Path
import pandas as pd
import pytest
from src.data_validation import read_csv, validate, ValidationError
from src.metrics import aggregate, daily_trends
from src.diagnostics import diagnose
from src.recommendations import generate, prepare
from src.recommendation_catalog import CATALOG
from src import api_config
ROOT=Path(__file__).resolve().parents[1]

@pytest.fixture
def data():
    return read_csv((ROOT/'data/sample_ads.csv').read_bytes())

def test_purchase_value_contradiction_rejected(data):
    data.loc[0,'conversions']=0
    with pytest.raises(ValidationError,match='conversion_value'):
        validate(data.assign(date=data.date.dt.strftime('%Y-%m-%d')))

def test_valid_zero_purchase_evidence_and_recommendation(data):
    event=next(x for x in diagnose(data,'2026-08-28',['C03']) if x['object']=='C03 / C03_A02')
    assert pd.isna(event['current'].CPA) and event['current'].ROAS==0
    evidence=event['records'][2]['confirmed']
    assert 'CPA=N/A' in evidence and 'ROAS=0.00' in evidence
    assert generate(prepare([event]))['recommendations'][0]['sections']['观察到什么']==evidence

def test_zero_evidence_uses_computed_ratio(monkeypatch,data):
    # Deliberately override calculation to ensure prose does not hardcode zero.
    import src.diagnostics as module
    original=module.aggregate
    def calculated(frame):
        result=original(frame)
        result['ROAS']=1.25
        return result
    monkeypatch.setattr(module,'aggregate',calculated)
    event=next(x for x in module.diagnose(data,'2026-08-28',['C03']) if x['object']=='C03 / C03_A02')
    assert 'ROAS=1.25' in event['records'][2]['confirmed']

def test_empty_vs_explicit_zero(data):
    assert aggregate(data.iloc[:0]).isna().all().all()
    zero=data.head(1).copy()
    zero[['impressions','clicks','cost','conversions','conversion_value']]=0
    row=aggregate(zero).iloc[0]
    assert row.cost==0 and row.conversions==0 and pd.isna(row.ROAS)

def test_entire_ad_window_missing(data):
    missing=data[~(data.ad_id.eq('C03_A02') & data.date.ge('2026-08-22'))]
    item=next(x for x in diagnose(missing,'2026-08-28',['C03']) if x['object']=='C03 / C03_A02')
    assert item['current'].isna().all() and item['current_coverage']=='0/7'
    assert all(r['status']=='数据不足' for r in item['records'])

def test_partial_daily_campaign_breaks_line(data):
    missing=data[~(data.ad_id.eq('C01_A02') & data.date.eq('2026-08-22'))]
    trend=daily_trends(missing,'2026-08-21','2026-08-23',['C01'])
    assert trend.coverage.tolist()==['完整','部分数据','完整']
    assert pd.isna(trend.iloc[1].cost) and pd.isna(trend.iloc[1].CTR)
    assert trend.iloc[0].cost==200

def test_entire_missing_day_and_ad(data):
    missing=data[~data.date.eq('2026-08-22')]
    assert daily_trends(missing,'2026-08-22','2026-08-22',['C01']).iloc[0].coverage=='缺失'
    missing=data[~(data.ad_id.eq('C01_A02') & data.date.ge('2026-08-22'))]
    trend=daily_trends(missing,'2026-08-22','2026-08-28',['C01'])
    assert trend.coverage.eq('部分数据').all() and trend.cost.isna().all()

def test_explicit_zero_day_not_missing(data):
    mask=data.campaign_id.eq('C01') & data.date.eq('2026-08-22')
    data.loc[mask,['impressions','clicks','cost','conversions','conversion_value']]=0
    point=daily_trends(data,'2026-08-22','2026-08-22',['C01']).iloc[0]
    assert point.coverage=='完整' and point.cost==0

def test_hypothesis_experiment_alignment():
    for name in ['visibility','mix']:
        text=CATALOG['CTR 下滑'][name][2]
        assert '观察性检查' in text and '不能' in text
    assert '不是在证明原始下降原因' in CATALOG['CTR 下滑']['relevance'][2]
    assert '不是在证明原始零转化原因' in CATALOG['有花费但零转化']['intent'][2]

def test_local_api_config(tmp_path,monkeypatch):
    path=tmp_path/'secrets.toml'
    monkeypatch.setattr(api_config,'SECRETS_PATH',path)
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    monkeypatch.delenv('OPENAI_MODEL',raising=False)
    path.write_text('OPENAI_API_KEY="test-only"\nOPENAI_MODEL="test-model"',encoding='utf-8')
    assert api_config.load_api_config()==('test-model','test-only','https://api.openai.com/v1','')
    path.write_text('invalid = [',encoding='utf-8')
    model,key,base_url,error=api_config.load_api_config()
    assert not model and not key and error

def test_ui_rejects_purchase_value_contradiction(data):
    from streamlit.testing.v1 import AppTest
    data.loc[0,'conversions']=0
    data['date']=data.date.dt.strftime('%Y-%m-%d')
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    app.file_uploader[0].set_value(('bad.csv',data.to_csv(index=False).encode(),'text/csv')).run()
    assert not app.exception and len(app.error)==1 and not app.metric

def test_ui_missing_window_shows_na(data):
    from streamlit.testing.v1 import AppTest
    data=data[~(data.ad_id.eq('C03_A02') & data.date.ge('2026-08-22'))].copy()
    data['date']=data.date.dt.strftime('%Y-%m-%d')
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    app.file_uploader[0].set_value(('missing.csv',data.to_csv(index=False).encode(),'text/csv')).run()
    app.selectbox[1].set_value(8).run()
    assert not app.exception
    assert app.dataframe[3].value.loc['当前窗口'].eq('N/A').all()
    assert any('部分数据或缺失日期已断开' in c.value for c in app.caption)
