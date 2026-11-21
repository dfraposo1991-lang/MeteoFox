#!/usr/bin/env python3
"""Preserva previsões ECMWF emitidas ANTES da radiossondagem 12Z de Lisboa."""
import json
from datetime import datetime, timezone
from pathlib import Path
root=Path(__file__).resolve().parent
src=root/'produtos_experimentais/previsao_ecmwf.json'
out=root/'produtos_experimentais/fox_verified_skewt_previsoes.json'
data=json.loads(src.read_text(encoding='utf-8'))
run=datetime.fromisoformat(data['run_utc'].replace('Z','+00:00'))
archive=json.loads(out.read_text(encoding='utf-8')) if out.exists() else {'forecasts':[]}
by_date={r['valid_utc']:r for r in archive.get('forecasts',[])}
for record in data['soundings']:
    valid=datetime.fromisoformat(record['valid_utc'].replace('Z','+00:00'))
    if valid.hour!=12 or valid<=run or 'Lisboa' not in record['cities']:
        continue
    key=record['valid_utc']
    existing=by_date.get(key)
    # Escolher a previsão anterior ao lançamento com o menor prazo.
    if existing is None or record['step_h']<existing['step_h']:
        by_date[key]={'valid_utc':key,'run_utc':data['run_utc'],'step_h':record['step_h'],
                      'levels':record['cities']['Lisboa'],'model':data['model']}
archive['forecasts']=sorted(by_date.values(),key=lambda x:x['valid_utc'],reverse=True)[:40]
out.write_text(json.dumps(archive,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
print('Previsões 12Z preservadas:',len(archive['forecasts']))
