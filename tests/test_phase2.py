from pathlib import Path
from datetime import date
import io
import math
import pandas as pd
import pytest
from src.data_validation import read_csv, validate, ValidationError
from src.metrics import aggregate, filter_data, missing_days

ROOT = Path(__file__).resolve().parents[1]

@pytest.fixture
def sample():
    return read_csv((ROOT/'data/sample_ads.csv').read_bytes())

def test_sample_contract(sample):
    assert len(sample)==168
    assert sample.date.nunique()==28
    assert sample.groupby('campaign_id').ad_id.nunique().tolist()==[2,2,2]
    assert sample.groupby('ad_id').size().eq(28).all()
    assert (sample.conversion_value==sample.conversions*50).all()
    assert not sample.duplicated(['date','campaign_id','ad_id']).any()
    assert missing_days(sample,'2026-08-01','2026-08-28')==0

@pytest.mark.parametrize('ad,expected',[
 ('C01_A01',[5,1,50,5,20,2.5]),
 ('C02_A01',[2,1,20,5,20,2.5]),
 ('C03_A01',[5,1.5,75,5,30,5/3]),
 ('C03_A02',[5,1,50,0,None,0])])
def test_manual_scenarios(sample,ad,expected):
    part=sample[(sample.ad_id==ad)&(sample.date>='2026-08-22')]
    out=aggregate(part).iloc[0]
    for metric, value in zip(['CTR','CPC','CPM','CVR','CPA','ROAS'],expected):
        assert pd.isna(out[metric]) if value is None else out[metric]==pytest.approx(value)

def test_sum_before_ratio_and_hierarchy(sample):
    out=aggregate(sample).iloc[0]
    assert out.cost==16730
    assert out.conversions==784
    assert out.conversion_value==39200
    assert out.CTR==pytest.approx(16380/336000*100)
    assert out.CPA==pytest.approx(16730/784)
    assert out.ROAS==pytest.approx(39200/16730)
    for by in [['campaign_id'],['campaign_id','ad_id']]:
        rolled=aggregate(aggregate(sample,by)).iloc[0]
        pd.testing.assert_series_equal(out,rolled)
    unequal=pd.DataFrame(dict(impressions=[100,900],clicks=[10,9],cost=[10,90],conversions=[2,1],conversion_value=[100,50]))
    result=aggregate(unequal).iloc[0]
    assert result.CTR==pytest.approx(1.9)
    assert result.CPA==pytest.approx(100/3)

def test_zero_denominators(sample):
    zeros=sample.head(1).copy()
    zeros[['impressions','clicks','cost','conversions','conversion_value']]=0
    assert aggregate(zeros)[['CTR','CPC','CPM','CVR','CPA','ROAS']].isna().all().all()

def test_filters_and_gaps(sample):
    selected=filter_data(sample,date(2026,8,22),date(2026,8,28),['C03'])
    assert len(selected)==14
    assert aggregate(selected).iloc[0].CPA==50
    assert filter_data(sample,date(2026,8,22),date(2026,8,28),[]).empty
    assert missing_days(sample.iloc[1:],'2026-08-01','2026-08-28')==1

@pytest.mark.parametrize('field,value',[
 ('date','2026-02-30'),('date','2026-8-01'),('currency','EUR'),('campaign_id',' '),
 ('clicks',-1),('clicks',0.5),('clicks',3000),('conversions',101),
 ('cost','abc'),('cost','inf'),('cost',None),('cost',1.234),('conversion_value',-1)])
def test_reject_bad_values(sample,field,value):
    data=sample.head(1).astype(object)
    data.loc[0,field]=value
    with pytest.raises(ValidationError): validate(data)

def test_structure_rejection(sample):
    with pytest.raises(ValidationError): validate(sample.drop(columns='cost'))
    with pytest.raises(ValidationError): validate(sample.iloc[:0])
    with pytest.raises(ValidationError): validate(pd.concat([sample,sample.head(1)]))
    bad=sample.copy(); bad.loc[6,'campaign_id']='C99'
    with pytest.raises(ValidationError): validate(bad)

@pytest.mark.parametrize('payload',[b'', b'cost,cost\n1,2',b'date,cost\n2026-08-01,1,2',b'\xff\xfe',b'date,cost\n"broken'])
def test_malformed_csv(payload):
    with pytest.raises(ValidationError): read_csv(payload)

def test_bom_and_identifiers(sample):
    text=sample.assign(date=sample.date.dt.strftime('%Y-%m-%d')).to_csv(index=False)
    assert len(read_csv(('\ufeff'+text).encode('utf-8')))==168

def test_app_default_and_filters():
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    assert not app.exception
    assert app.metric[0].value=='$16,730.00'
    app.multiselect[0].set_value(['C03'])
    app.date_input[0].set_value((date(2026,8,22),date(2026,8,28))).run()
    assert not app.exception
    assert app.metric[0].value=='$1,750.00'
    assert app.metric[3].value=='$50.00'
    assert len(app.dataframe[1].value)==2
    app.multiselect[0].set_value([]).run()
    assert not app.exception and len(app.info)==1

def test_app_upload_validation_and_na(sample):
    from streamlit.testing.v1 import AppTest
    app=AppTest.from_file(str(ROOT/'app.py'),default_timeout=30).run()
    app.file_uploader[0].set_value(('bad.csv',b'cost\n-1','text/csv')).run()
    assert not app.exception and len(app.error)==1 and len(app.metric)==0
    zero=sample[(sample.ad_id=='C03_A02')&(sample.date>='2026-08-22')].copy()
    zero['date']=zero.date.dt.strftime('%Y-%m-%d')
    app.file_uploader[0].set_value(('zero.csv',zero.to_csv(index=False).encode(),'text/csv')).run()
    assert not app.exception and not app.error
    assert app.metric[3].value=='N/A'
    assert app.metric[4].value=='0.00×'
    app.file_uploader[0].set_value(('gap.csv',zero.drop(index=zero.index[2]).to_csv(index=False).encode(),'text/csv')).run()
    assert not app.exception and len(app.warning)==1
    app.file_uploader[0].set_value(('empty.csv',b'','text/csv')).run()
    assert not app.exception and len(app.error)==1 and len(app.metric)==0
