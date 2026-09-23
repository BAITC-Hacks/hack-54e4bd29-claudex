"""Local source integrity audit; never emit raw clinical values."""
import csv, hashlib, json
from collections import Counter
from pathlib import Path


def main():
    seen=set(); codes=set(); duplicates=code_repeats=rows=0; missing=Counter(); daily=Counter(); org=Counter()
    for path in sorted(Path('data/incoming').glob('referrals_part_*.csv')):
        with path.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f):
                rows+=1
                digest=hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).digest()
                duplicates+=digest in seen; seen.add(digest)
                code=hashlib.sha256(r.get('hospitalization_code','').encode()).digest()
                code_repeats+=code in codes; codes.add(code)
                for field in ('hospital_mo','registration_dt','planned_dt','bed_profile'):
                    missing[field]+=not bool(r.get(field,'').strip())
                daily[r['registration_dt'][:10]]+=1;org[r['hospital_mo']]+=1
    result={'rows':rows,'exact_duplicate_rows':duplicates,'repeated_case_codes':code_repeats,
       'missing':dict(missing),'dates':len(daily),'organizations':len(org),
       'daily_min':min(daily.values()),'daily_max':max(daily.values()),
       'largest_days':sorted(daily.items(),key=lambda a:a[1],reverse=True)[:5],
       'smallest_days':sorted(daily.items(),key=lambda a:a[1])[:5],
       'interpretation':'Count source records consistently with v1. Repeated codes alone are not proof of duplicate events. No rows removed. Missing reporting cannot be distinguished from true zero without source confirmation.'}
    Path('data/monitoring/source-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
