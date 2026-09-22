"""Download the three public referral exports; no credentials are required."""
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen
import shutil


def main():
    directory = Path('data/incoming')
    directory.mkdir(parents=True, exist_ok=True)
    for part in range(1, 4):
        path = directory/f'referrals_part_{part:03}.csv'
        if path.exists():
            print(f'Already present: {path.name}; remove explicitly to fetch a new release')
            continue
        name = f'Направления на плановую госпитализацию в стационары_part_{part:03}_of_003.csv'
        url = 'https://magda-minio-web.data.gov.kz/magda-datasets/mz_bg_planned_hospitalization_referrals/'+quote(name)
        temporary = path.with_suffix('.csv.part')
        with urlopen(url, timeout=120) as response, temporary.open('wb') as output:
            shutil.copyfileobj(response, output, length=1024*1024)
        temporary.replace(path)
        print(f'Downloaded: {path.name}')

if __name__ == '__main__':
    main()
