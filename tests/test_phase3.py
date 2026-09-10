from pathlib import Path
import pandas as pd
import pytest
from src.data_validation import read_csv
from src.diagnostics import diagnose
ROOT=Path(__file__).resolve().parents[1]

def fixture(previous=(1000,200,200,10,500),current=None):
    current=current or previous
    rows=[]
    for i,day in enumerate(pd.date_range('2026-08-15',periods=14)):
        values=(previous if i==0 else current if i==7 else (0,0,0,0,0))
        rows.append([day,'C01','A01','USD',*values])
    return pd.DataFrame(rows,columns=['date','campaign_id','ad_id','currency','impressions','clicks','cost','conversions','conversion_value'])

def rules(data,complete=True):
    return {r['rule']:r for r in diagnose(data,'2026-08-28',['C01'],complete)[0]['records']}

def test_sample_expected():
    data=read_csv((ROOT/'data/sample_ads.csv').read_bytes())
    results=diagnose(data,'2026-08-28',['C01','C02','C03'])
    assert len(results)==9
    expected={'C01':[], 'C02':['CTR 下滑'], 'C03':['CPC 上升并伴随 CPA 恶化'],
              'C01 / C01_A01':[], 'C01 / C01_A02':[], 'C02 / C02_A01':['CTR 下滑'],
              'C02 / C02_A02':[], 'C03 / C03_A01':['CPC 上升并伴随 CPA 恶化'],
              'C03 / C03_A02':['有花费但零转化']}
    for item in results:
        assert [r['rule'] for r in item['records'] if r['status']=='触发']==expected[item['object']]
        assert item['current_window']=='2026-08-22 — 2026-08-28'
        assert item['previous_window']=='2026-08-15 — 2026-08-21'
        assert all(r['unknown'] and r['trigger'] and r['confirmed'] and r['reason'] for r in item['records'])
    assert 'CVR 5.00% → 2.50%' in results[2]['records'][1]['confirmed']

@pytest.mark.parametrize('clicks,status',[(70,'触发'),(71,'未触发'),(49,'数据不足')])
def test_ctr_boundaries(clicks,status):
    data=fixture((1000,100,100,10,500),(1000,clicks,100,10,500))
    assert rules(data)['CTR 下滑']['status']==status

@pytest.mark.parametrize('impressions,status',[(999,'数据不足'),(1000,'触发')])
def test_ctr_impressions(impressions,status):
    data=fixture((impressions,100,100,10,500),(impressions,70,100,10,500))
    assert rules(data)['CTR 下滑']['status']==status

@pytest.mark.parametrize('cost,status',[(300,'触发'),(299.99,'未触发')])
def test_cpc_exact_growth(cost,status):
    assert rules(fixture((1000,200,240,10,500),(1000,200,cost,10,500)))['CPC 上升并伴随 CPA 恶化']['status']==status

@pytest.mark.parametrize('cost,status',[(250,'未触发'),(250.01,'触发')])
def test_strict_cpa_target(cost,status):
    assert rules(fixture(current=(1000,200,cost,10,500)))['CPC 上升并伴随 CPA 恶化']['status']==status

@pytest.mark.parametrize('clicks,conversions,status',[(200,10,'触发'),(199,10,'数据不足'),(200,9,'数据不足'),(200,0,'数据不足')])
def test_cpc_volume(clicks,conversions,status):
    assert rules(fixture(current=(1000,clicks,300,conversions,conversions*50)))['CPC 上升并伴随 CPA 恶化']['status']==status

def test_cpc_needs_both_changes():
    assert rules(fixture(current=(1000,200,300,15,750)))['CPC 上升并伴随 CPA 恶化']['status']=='未触发'
    assert rules(fixture((2000,400,400,20,1000),(2000,400,400,10,500)))['CPC 上升并伴随 CPA 恶化']['status']=='未触发'

@pytest.mark.parametrize('clicks,cost,status',[(50,50,'触发'),(49,50,'数据不足'),(50,49.99,'数据不足')])
def test_zero_boundaries(clicks,cost,status):
    assert rules(fixture(current=(1000,clicks,cost,0,0)))['有花费但零转化']['status']==status

def test_normal_target_boundaries_and_no_fifth_alert():
    assert rules(fixture())['正常对照']['status']=='正常对照'
    assert rules(fixture((1000,200,250,10,500)))['正常对照']['status']=='正常对照'
    for values in [(1000,200,251,10,500),(1000,200,200,10,399)]:
        out=rules(fixture(values))
        assert out['正常对照']['status']=='未满足'
        assert not any(r['status']=='触发' for r in out.values())

def test_no_normal_when_insufficient():
    assert rules(fixture((1000,199,200,10,500)))['正常对照']['status']=='数据不足'

def test_missing_day_and_missing_baseline():
    data=fixture(current=(1000,200,100,0,0))
    out=rules(data.drop(index=8))
    assert all(r['status']=='数据不足' for r in out.values())
    out=rules(data.iloc[7:])
    assert out['有花费但零转化']['status']=='触发'
    assert out['CTR 下滑']['status']=='数据不足'

def test_campaign_missing_ad_does_not_look_complete():
    data=fixture()
    other=data.assign(ad_id='A02').iloc[:7]
    assert rules(pd.concat([data,other]))['正常对照']['status']=='数据不足'

def test_lag_unconfirmed():
    out=rules(fixture(current=(1000,200,100,0,0)),False)
    assert all(r['status']=='数据不足' for r in out.values())

def test_zero_baselines_and_all_zero():
    for values in [(0,0,0,0,0),(1000,200,0,10,500)]:
        out=rules(fixture(values))
        assert out['正常对照']['status']=='数据不足'
        assert not any(r['status']=='触发' for r in out.values())

def test_campaign_filter():
    data=read_csv((ROOT/'data/sample_ads.csv').read_bytes())
    assert len(diagnose(data,'2026-08-28',['C02']))==3

def test_ui_default_and_incomplete_end():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not app.exception
    summary=app.dataframe[2].value
    assert len(summary)==9
    assert summary.iloc[1]['结果']=='CTR 下滑'
    app.date_input[0].set_value((pd.Timestamp('2026-08-01').date(),pd.Timestamp('2026-08-07').date())).run()
    assert not app.exception
    assert (app.dataframe[2].value['结果']=='数据不足').all()

def test_ui_upload_requires_complete_confirmation():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    app.file_uploader[0].set_value(('sample.csv',(ROOT/'data/sample_ads.csv').read_bytes(),'text/csv')).run()
    assert not app.exception
    assert (app.dataframe[2].value['结果']=='数据不足').all()
    app.checkbox[0].set_value(True).run()
    assert not app.exception and app.dataframe[2].value.iloc[1]['结果']=='CTR 下滑'
