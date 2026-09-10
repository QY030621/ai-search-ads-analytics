"""Explicit live validation: real requests, only three triggered Ad diagnoses."""
from pathlib import Path
import json
from datetime import datetime, timezone
from src.api_config import load_api_config
from src.data_validation import read_csv
from src.diagnostics import diagnose
from src.recommendations import prepare, generate

ROOT=Path(__file__).parent

def main():
    model,key,base_url,error=load_api_config()
    if error or not model or not key:
        print('BLOCKED: configure AI_API_KEY, AI_BASE_URL and AI_MODEL; no real request sent.')
        return 2
    data=read_csv((ROOT/'data/sample_ads.csv').read_bytes())
    items=diagnose(data,'2026-08-28',['C01','C02','C03'])
    events=prepare([item for item in items if item['level']=='Ad'])['events']
    report={'dataset':'Personal Project / Simulated Dataset','time':datetime.now(timezone.utc).isoformat(),
            'model':model,'base_url':base_url,'results':[]}
    for event in events:
        result=generate({'events':[event]},model,key,True,base_url=base_url)
        success=result['source']=='AI 辅助建议（受约束生成）'
        unchanged=result['recommendations'][0]['sections']['观察到什么']==event['confirmed']
        report['results'].append({'object':event['object'],'rule':event['rule'],'real_api_success':success,
                                  'evidence_unchanged':unchanged,'result':result})
        print(event['rule'], 'PASS' if success and unchanged else 'FAIL (fallback; not a real success)',flush=True)
    (ROOT/'LIVE_AI_VALIDATION.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if len(report['results'])==3 and all(x['real_api_success'] and x['evidence_unchanged'] for x in report['results']) else 1

if __name__=='__main__':
    raise SystemExit(main())
