"""Single-worker, local-only replay of forecasts learned from real referrals.

No raw clinical rows, account data or operational service credentials are loaded.
The authenticated operational API is not mounted or bypassed by this app.
"""
from __future__ import annotations

import asyncio
import json
import hashlib

import joblib
from threadpoolctl import threadpool_limits
from ml.monitoring import predict, alert_for
from ml.risk import risk_context
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class Replay:
    def __init__(self, directory: Path):
        self.directory = directory
        self.lock = threading.RLock()
        self.running = False
        self.index = 0
        self.decisions: dict = {}
        self.updated_at = None
        self.bundle = None
        self.estimator = None
        self.calculated = {}
        self.reload()

    def reload(self):
        file = self.directory/'bundle.json'
        if file.exists():
            self.bundle = json.loads(file.read_text())
            if 'runtime' in self.bundle:
                artifact = self.directory/'model.joblib'
                if hashlib.sha256(artifact.read_bytes()).hexdigest() != self.bundle['report']['artifact_sha256']:
                    raise ValueError('Model checksum mismatch; rerun training')
                self.estimator = joblib.load(artifact)['model']
            state = self.directory/'replay-state.json'
            if state.exists():
                stored = json.loads(state.read_text())
                if stored.get('model_id') == self.bundle['report']['model_id']:
                    self.index = min(stored.get('index', 0), len(self.bundle['snapshots'])-1)
                    self.decisions = stored.get('decisions', {})

    def save(self):
        self.updated_at = datetime.now(timezone.utc).isoformat()
        state = {'model_id': self.bundle['report']['model_id'], 'index': self.index, 'decisions': self.decisions}
        tmp = self.directory/'replay-state.tmp'
        tmp.write_text(json.dumps(state, ensure_ascii=False))
        tmp.replace(self.directory/'replay-state.json')

    def require_data(self):
        if not self.bundle:
            raise HTTPException(503, 'Сначала запустите обучение: python -m ml.monitoring')

    def snapshot(self):
        if self.estimator is None:
            return self.bundle['snapshots'][self.index]
        if self.index not in self.calculated:
            runtime = self.bundle['runtime']
            origin = runtime['start_origin'] + self.index
            dates = runtime['dates'][:origin+1]
            observed = {name: values[:origin+1] for name, values in runtime['series'].items()}
            with threadpool_limits(limits=2):
                predictions = predict(self.estimator, observed, dates, origin)
                risks = self.estimator.risk_scores(observed, dates, origin) if hasattr(self.estimator, "risk_scores") else None
            alerts = []
            for name, values in observed.items():
                alert = alert_for(name, values, dates, origin, predictions[name],
                                  runtime['qualities'][name], self.bundle['report']['model_id'], risk=risk_context(self.estimator,name,risks))
                if alert:
                    alerts.append(alert)
            alerts.sort(key=lambda a: (-{'CRITICAL': 3, 'HIGH': 2, 'WARNING': 1}[a['severity']], -a.get('risk_score', 0), -a['extra_referrals']))
            self.calculated[self.index] = {'as_of': dates[-1], 'new_records': runtime['daily_records'][origin],
                                          'hospitals_checked': len(observed), 'alerts': alerts}
        return self.calculated[self.index]

    def view(self):
        with self.lock:
            self.require_data()
            snapshot = self.snapshot()
            alerts = [{**a, 'status': self.decisions.get(a['id'], {}).get('status', 'NEW')}
                      for a in snapshot['alerts']]
            return {**snapshot, 'alerts': alerts, 'mode': 'HISTORICAL_REPLAY', 'running': self.running,
                    'index': self.index, 'total_steps': len(self.bundle['snapshots']),
                    'finished': self.index == len(self.bundle['snapshots'])-1,
                    'updated_at': self.updated_at, 'interval_seconds': 10,
                    'model_id': self.bundle['report']['model_id'],
                    'prediction_mode': 'На каждом новом дне сохранённая обученная модель заново рассчитывает прогноз по доступной истории. Будущие значения в признаки не входят.'}

    def step(self):
        with self.lock:
            self.require_data()
            if self.index < len(self.bundle['snapshots'])-1:
                self.index += 1
                self.snapshot()
                self.save()
            if self.index == len(self.bundle['snapshots'])-1:
                self.running = False
            return self.view()


class Control(BaseModel):
    action: Literal['play', 'pause', 'step', 'reset']


class Decision(BaseModel):
    status: Literal['NEW', 'IN_PROGRESS', 'CLOSED']


def create_app(directory: Path | None = None):
    replay = Replay(directory or Path(os.environ.get('MONITORING_DIR', 'data/monitoring')))

    @asynccontextmanager
    async def lifespan(app):
        async def ticker():
            while True:
                await asyncio.sleep(10)
                if replay.running:
                    replay.step()
        task = asyncio.create_task(ticker())
        yield
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    app = FastAPI(title='MedSignal — локальный пилот', lifespan=lifespan)
    app.state.replay = replay

    def mutation_guard(header):
        # No CORS policy is enabled; a cross-origin browser cannot set this header.
        if header != '1':
            raise HTTPException(403, 'Demo control header required')

    @app.get('/api/pilot/health')
    def health():
        return {'status': 'ok', 'data_ready': replay.bundle is not None}

    @app.get('/api/pilot/monitor')
    def monitor():
        return replay.view()

    @app.get('/api/pilot/model')
    def model():
        replay.require_data()
        return replay.bundle['report']

    @app.get('/api/pilot/alerts/{alert_id}')
    def detail(alert_id: str):
        with replay.lock:
            replay.require_data()
            # Historical cards remain available after the replay advances.
            for snapshot in replay.bundle['snapshots'][:replay.index+1]:
                for alert in snapshot['alerts']:
                    if alert['id'] == alert_id:
                        return {**alert, **replay.decisions.get(alert_id, {'status': 'NEW'}),
                                'current_as_of': replay.bundle['snapshots'][replay.index]['as_of']}
            raise HTTPException(404, 'Предупреждение не найдено')

    @app.post('/api/pilot/replay')
    def control(command: Control, x_medsignal_demo: str | None = Header(default=None)):
        mutation_guard(x_medsignal_demo)
        with replay.lock:
            replay.require_data()
            if command.action == 'step':
                return replay.step()
            if command.action == 'reset':
                replay.index = 0
                replay.calculated.clear()
                replay.running = False
            elif command.action == 'play':
                replay.running = replay.index < len(replay.bundle['snapshots'])-1
            else:
                replay.running = False
            replay.save()
            return replay.view()

    @app.patch('/api/pilot/alerts/{alert_id}')
    def decide(alert_id: str, command: Decision, x_medsignal_demo: str | None = Header(default=None)):
        mutation_guard(x_medsignal_demo)
        with replay.lock:
            detail(alert_id)
            replay.decisions[alert_id] = {'status': command.status, 'changed_at': datetime.now(timezone.utc).isoformat()}
            replay.save()
            return detail(alert_id)

    return app


app = create_app()
