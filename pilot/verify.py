"""Verify the actual saved estimator, data cutoff, and replay against training output."""
import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
from threadpoolctl import threadpool_limits

from ml.monitoring import predict, alert_for


def verify(directory=Path('data/monitoring')):
    bundle = json.loads((directory/'bundle.json').read_text())
    report, runtime = bundle['report'], bundle['runtime']
    assert hashlib.sha256((directory/'model.joblib').read_bytes()).hexdigest() == report['artifact_sha256']
    model = joblib.load(directory/'model.joblib')
    assert model['train_end'] < report['validation_start'] <= report['validation_end'] < report['test_start']
    checked = 0
    with threadpool_limits(limits=2):
        for index in (0, len(bundle['snapshots'])-1):
            origin = runtime['start_origin']+index
            history = {name: values[:origin+1] for name, values in runtime['series'].items()}
            dates = runtime['dates'][:origin+1]
            forecasts = predict(model['model'], history, dates, origin)
            expected = {a['id']: a for a in bundle['snapshots'][index]['alerts']}
            actual = {}
            for name, values in history.items():
                alert = alert_for(name, values, dates, origin, forecasts[name], runtime['qualities'][name], report['model_id'])
                if alert:
                    actual[alert['id']] = alert
            assert expected.keys() == actual.keys(), 'Saved estimator and replay alert sets differ'
            for key in expected:
                np.testing.assert_allclose(actual[key]['predicted_total'], expected[key]['predicted_total'], atol=0.1)
            checked += len(forecasts)
    print(json.dumps({'verified': True, 'hospital_forecasts_recomputed': checked,
                      'artifact_sha256': report['artifact_sha256'], 'test_metrics': report['test']['ml']}, indent=2))

if __name__ == '__main__':
    verify()
