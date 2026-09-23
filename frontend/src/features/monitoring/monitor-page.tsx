'use client';
import Link from 'next/link';
import {useState} from 'react';
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query';
import {ArrowRight, BellRing, Pause, Play, RefreshCw, SkipForward} from 'lucide-react';
import {pilotApi, number, day, severity, status} from './api';
import type {Monitor} from './types';

const button = 'inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm font-medium hover:bg-secondary disabled:opacity-40';
export function MonitorPage() {
 const client = useQueryClient();
 const [search, setSearch] = useState('');
 const [filter, setFilter] = useState('ALL');
 const query = useQuery({queryKey:['monitor'], queryFn:()=>pilotApi<Monitor>('monitor'), refetchInterval:2000, retry:1});
 const command = useMutation({mutationFn:(action:string)=>pilotApi<Monitor>('replay','POST',{action}),
  onSuccess:data=>client.setQueryData(['monitor'],data)});
 const data = query.data;
 const alerts = data?.alerts.filter(a=>a.hospital.toLowerCase().includes(search.toLowerCase()) && (filter==='ALL'||a.status===filter)) ?? [];
 return <div className="mx-auto max-w-6xl space-y-6">
  <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="mb-2 text-xs font-semibold uppercase tracking-widest text-teal-700">MedFlow · плановая госпитализация</p>
   <h1 className="text-3xl font-semibold tracking-tight">Где ожидается рост потока?</h1>
   <p className="mt-2 max-w-2xl text-sm text-muted-foreground">Обученная модель выявляет риск роста потока на 7 дней. Откройте предупреждение, чтобы проверить основания и план действий.</p></div>
   <Link className={button} href="/monitor/model">Как проверена модель <ArrowRight size={16}/></Link></div>
  <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-amber-950">
   <div className="flex flex-wrap items-center justify-between gap-4"><div><p className="font-semibold">Историческое воспроизведение · реальные данные</p>
    <p className="mt-1 text-sm">{data ? `Данные по ${day(data.as_of)}. Один шаг — один день. Автоматически — каждые 10 секунд.` : 'Загружаем результаты обучения…'}</p></div>
    <div className="flex gap-2"><button className={button} disabled={!data || command.isPending || data.finished} onClick={()=>command.mutate(data?.running?'pause':'play')}>{data?.running?<Pause size={16}/>:<Play size={16}/>} {data?.running?'Пауза':'Запустить'}</button>
     <button aria-label="Следующий день" className={button} disabled={!data || command.isPending || data.finished || data.running} onClick={()=>command.mutate('step')}><SkipForward size={16}/> День</button>
     <button aria-label="Сначала" className={button} disabled={!data || command.isPending} onClick={()=>command.mutate('reset')}><RefreshCw size={16}/></button></div></div>
   <p className="mt-3 text-xs font-medium">Исследовательский пилот: полнота обнаружения роста пока низкая. Не единственный канал контроля.</p>
   <p className="mt-3 text-xs">Это не подключение к больницам в реальном времени. На каждом шаге сохранённая модель заново рассчитывает прогноз по доступной на эту дату истории. Будущие записи не входят в признаки.</p>
   {data?.finished && <p className="mt-2 font-medium">Достигнут конец выгрузки. Новые данные не выдумываются; можно повторить воспроизведение.</p>}
  </section>
  {(query.error || command.error) && <p role="alert" className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">{(query.error || command.error)?.message}</p>}
  {data && <><div className="grid gap-4 sm:grid-cols-3">{[
   ['Предупреждений за день',data.alerts.length],['Организаций проверено',data.hospitals_checked],['Записей за новый день',data.new_records]
  ].map(([label,value])=><div key={label} className="rounded-xl border bg-card p-5"><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-3xl font-semibold">{number(Number(value))}</p></div>)}</div>
   <div className="flex flex-wrap gap-3"><input aria-label="Поиск по больнице" className="min-w-60 flex-1 rounded-lg border bg-background px-4 py-2 text-sm" placeholder="Найти больницу…" value={search} onChange={e=>setSearch(e.target.value)}/>
    <select aria-label="Статус предупреждения" className="rounded-lg border bg-background px-3 py-2 text-sm" value={filter} onChange={e=>setFilter(e.target.value)}><option value="ALL">Все статусы</option>{Object.entries(status).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></div>
   <div className="space-y-3">{alerts.map(alert=><Link key={alert.id} href={`/monitor/${alert.id}`} className="block rounded-xl border bg-card p-5 transition hover:border-teal-500 hover:shadow-sm">
    <div className="flex flex-wrap items-center gap-2 text-xs"><span className={`rounded-full px-2.5 py-1 font-semibold ${alert.severity==='CRITICAL'?'bg-red-100 text-red-800':alert.severity==='HIGH'?'bg-orange-100 text-orange-800':'bg-amber-100 text-amber-900'}`}><BellRing className="mr-1 inline" size={13}/>{severity[alert.severity]}</span>
     <span className="rounded-full bg-secondary px-2.5 py-1">{status[alert.status]}</span>
     {alert.quality.status==='EXPERIMENTAL' && <span className="text-muted-foreground">На проверке по этой больнице простой прогноз точнее</span>}</div>
    <div className="mt-3 flex items-center justify-between gap-5"><div><h2 className="text-lg font-semibold">{alert.title}</h2><p className="mt-1 text-sm text-muted-foreground">{alert.hospital}</p></div><ArrowRight className="shrink-0 text-teal-700" size={20}/></div>
    <p className="mt-3 text-sm"><strong>{number(alert.predicted_total)}</strong> направлений за неделю · обычно {number(alert.reference_total)} · изменение {alert.extra_referrals > 0 ? "+" : ""}{number(alert.extra_referrals)}</p>
    {alert.risk_score !== undefined && <p className="mt-2 text-xs text-muted-foreground">Оценка риска {alert.risk_score.toFixed(3)} · порог {(alert.risk_threshold ?? 0).toFixed(3)}. Это не вероятность. Численный прогноз может не показывать роста.</p>}
   </Link>)}</div>
   {alerts.length===0 && <div className="rounded-xl border border-dashed p-10 text-center text-muted-foreground">{data.alerts.length?'По выбранным фильтрам предупреждений нет.':'Модель не обнаружила роста выше порога на эту дату.'}</div>}
   <p className="text-xs text-muted-foreground">Приоритет предварительный: риск роста потока не означает подтверждённую перегрузку. Очередь и свободные койки в этих данных не измеряются.</p>
  </>}
 </div>;
}
