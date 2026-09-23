from datetime import date, timedelta
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sklearn.ensemble import HistGradientBoostingRegressor
from threadpoolctl import threadpool_limits

from ml.monitoring import features, samples, alert_for, aggregate, metrics
from pilot.api import create_app


def dates(n=90):
    return [(date(2025, 1, 1)+timedelta(days=i)).isoformat() for i in range(n)]


def test_features_and_training_do_not_see_future():
    values = list(range(90))
    future = values[:62]+[100000]*28
    for horizon in range(1,8):
        assert features(values, dates(), 61, horizon) == features(future, dates(), 61, horizon)
    a, b = samples({'hospital':values}, dates(), 61)
    c, d = samples({'hospital':future}, dates(), 61)
    np.testing.assert_array_equal(a,c)
    np.testing.assert_array_equal(b,d)
    assert b.max()==61


def test_training_changes_predictions_when_targets_change():
    x, y = samples({'hospital':[10+(i%7)*5 for i in range(90)]}, dates(), 61)
    with threadpool_limits(limits=1):
        first = HistGradientBoostingRegressor(max_iter=30, early_stopping=False, random_state=42).fit(x,y)
        second = HistGradientBoostingRegressor(max_iter=30, early_stopping=False, random_state=42).fit(x,y+50)
        assert np.mean(second.predict(x)-first.predict(x)) > 40


def test_alert_is_model_forecast_compared_with_history_not_baseline_disagreement():
    args = ('hospital',[10]*90,dates(),61)
    assert alert_for(*args,[10]*7,{},'model') is None
    alert = alert_for(*args,[20]*7,{},'model')
    assert alert['reference_total']==70
    assert alert['growth_percent']==100
    assert alert['severity']=='CRITICAL'
    assert alert_for(*args,[20]*7,{},'model')['id']==alert['id']
    assert len(alert['actions'])==3


def test_missing_source_day_is_rejected(tmp_path):
    path=tmp_path/'source.csv'
    path.write_text('hospital_mo,registration_dt\nA,2025-01-01\nA,2025-01-03\n')
    with pytest.raises(ValueError,match='missing'):
        aggregate([path])


def test_duplicate_export_is_rejected(tmp_path):
    p=tmp_path/'one.csv'; q=tmp_path/'two.csv'
    p.write_text('hospital_mo,registration_dt\nA,2025-01-01\n'); q.write_text(p.read_text())
    with pytest.raises(ValueError,match='Duplicate'):
        aggregate([p,q])


def test_zero_actual_wape_is_not_fake_zero_accuracy():
    assert metrics([0,0],[1,2])['wape'] is None


def bundle(tmp_path):
    value={'report':{'model_id':'test'},'snapshots':[
      {'as_of':'2025-03-17','alerts':[{'id':'a','status':'NEW'}]},
      {'as_of':'2025-03-18','alerts':[{'id':'b','status':'NEW'}]}]}
    (tmp_path/'bundle.json').write_text(json.dumps(value))


def test_replay_end_and_decisions_survive_restart(tmp_path):
    bundle(tmp_path)
    with TestClient(create_app(tmp_path)) as client:
        assert client.post('/api/pilot/replay',json={'action':'step'}).status_code==403
        headers={'X-MedSignal-Demo':'1'}
        assert client.get('/api/pilot/alerts/b').status_code==404
        assert client.patch('/api/pilot/alerts/a',json={'status':'IN_PROGRESS'},headers=headers).status_code==200
        response=client.post('/api/pilot/replay',json={'action':'step'},headers=headers).json()
        assert response['finished'] and response['index']==1
        assert client.post('/api/pilot/replay',json={'action':'step'},headers=headers).json()['index']==1
        assert client.get('/api/pilot/alerts/a').json()['status']=='IN_PROGRESS'
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/pilot/monitor').json()['index']==1
        assert client.get('/api/pilot/alerts/a').json()['status']=='IN_PROGRESS'


def test_empty_install_never_returns_fabricated_results(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get('/api/pilot/monitor').status_code==503


def test_risk_features_and_labels_respect_cutoff():
    from ml.risk import risk_features, risk_samples
    values=[int(20+10*np.sin(i/5)) for i in range(90)]
    future=values[:62]+[99999]*28
    assert risk_features(values, dates(),61)==risk_features(future,dates(),61)
    x,y=risk_samples({'a':values},dates(),61)
    changed_x,changed_y=risk_samples({'a':future},dates(),61)
    np.testing.assert_array_equal(x,changed_x)
    np.testing.assert_array_equal(y,changed_y)
    assert len(y)==28  # origins 27..54, last target 61, validation starts 62


def test_risk_label_matches_original_event():
    from ml.risk import growth_label
    values=[10]*28+[13]*7
    assert growth_label(values,27)==1
    assert growth_label([10]*28+[11]*7,27)==0
    assert growth_label([1]*28+[20]*7,27)==0  # insufficient reference volume


def test_risk_alert_can_disagree_with_mean_without_claiming_growth():
    a=alert_for('a',[10]*90,dates(),61,[8]*7,{},'v2',risk={'score':.8,'threshold':.7})
    assert a is not None and a['extra_referrals']<0
    assert a['title']=='Риск существенного роста направлений'
    assert 'не калиброванная вероятность' in a['trigger']
    assert 'больше обычного' not in a['actions'][0]['text']
    assert alert_for('a',[10]*90,dates(),61,[100]*7,{},'v2',risk={'score':.2,'threshold':.7}) is None


def test_threshold_budget_and_confusion_counts():
    from ml.risk import choose_threshold,classification
    y=[1,1,0,0,0,0,0,0]
    p=[.9,.7,.8,.1,.2,.3,.1,.1]
    threshold,m=choose_threshold(y,p)
    assert m['alert_rate_percent']<=25
    assert m['precision_percent']>=40
    assert classification([1,1,0,0],[1,0,1,0])==dict(true_positive=1,false_positive=1,false_negative=1,true_negative=1,precision_percent=50.,recall_percent=50.,f1=.5,f2=.5,alert_count=2,alert_rate_percent=50.,cases=4)


def test_runtime_uses_segment_threshold():
    from ml.risk import risk_context
    class Model:
        groups={'a':'large'}
        segment_thresholds={'large':.2}
        threshold=.7
    assert risk_context(Model(),'a',{'a':.3})=={'score':.3,'threshold':.2}
    assert risk_context(Model(),'a',None) is None
