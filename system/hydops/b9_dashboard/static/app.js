const { createApp } = Vue;
const API = (window.HYDOPS_API || '') ;
const j = (u, o) => fetch(API + u, o).then(r => r.json());
const post = (u, b) => j(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b) });

const STATUS_KO = { DETECTED: '감지', EVIDENCE_READY: '근거 확인', PENDING_APPROVAL: '승인 대기', EXECUTED: '실행', VERIFYING: '재측정 중', VERIFY_HOLD: '재측정 보류', CLOSED: '종결', ESCALATED: '이관', REJECTED: '거부·미실행', HOLD_NO_EVIDENCE: '근거 없음 보류', SENSOR_CHECK: '센서 점검', RUN_ENDED: '실행 종료' };
const TYPE_KO = { COOLING_ANOMALY: '냉각 이상', SENSOR_FAULT: '센서 오류', PRODUCT_QUALITY: '제품 품질(합성)' };

createApp({
  data: () => ({
    state: { sim: {} }, assets: [], series: {}, actions: [], events: [], selectedId: null, detail: null,
    assetId: 'HYD-01', approver: 'kim.operator', approveValue: 0.8, W: 760, H: 300, PAD: 44,
  }),
  computed: {
    simClock() { const s = this.state.sim?.[this.assetId]; return s ? s.t.slice(11, 19) : '-'; },
    assetCards() {
      return this.assets.map(a => {
        const sim = this.state.sim?.[a.asset_id] || {};
        return { asset_id: a.asset_id, name: a.asset?.name, cooling: a.asset?.cooling, sopCount: a.applicable_sops?.length || 0,
          allowed: (a.allowed_actions || []).map(x => x.action_id), temp: sim.temp_c, load: sim.load,
          flag: a.asset_id === this.assetId ? (this.series.TS1?.slice(-1)[0]?.flag || 'OK') : 'OK' };
      });
    },
    pts() { return this.series.TS1 || []; },
    t0() { return this.pts.length ? Date.parse(this.pts[0].ts) : 0; },
    t1() { return this.pts.length ? Date.parse(this.pts[this.pts.length - 1].ts) : 1; },
    yMin() { const v = this.pts.map(p => p.value).filter(x => x != null); return Math.min(40, ...v) - 2; },
    yMax() { const v = this.pts.map(p => p.value).filter(x => x != null); return Math.max(70, ...v) + 2; },
    yTicks() { const t = []; for (let v = Math.ceil(this.yMin / 5) * 5; v <= this.yMax; v += 5) t.push(v); return t; },
    tempPath() {
      let d = '', pen = false;
      for (const p of this.pts) {
        if (p.value == null) { pen = false; continue; }
        d += (pen ? 'L' : 'M') + this.x(p.ts).toFixed(1) + ',' + this.y(p.value).toFixed(1); pen = true;
      }
      return d;
    },
    badPoints() {
      return this.pts.filter(p => p.flag !== 'OK').map(p => ({ x: this.x(p.ts), y: this.y(p.raw ?? this.yMin + 1), flag: p.flag }));
    },
    flagCounts() { const c = {}; for (const p of this.pts) c[p.flag] = (c[p.flag] || 0) + 1; return c; },
    chartActions() {
      const span = (this.t1 - this.t0) || 1, pw = this.W - this.PAD - 10;
      return this.actions.filter(a => Date.parse(a.sim_ts) >= this.t0).map(a => ({ ...a, x: this.x(a.sim_ts), waitW: 30000 / span * pw, winW: 60000 / span * pw }));
    },
    xStart() { return this.pts[0]?.ts.slice(11, 19) || ''; },
    xEnd() { return this.pts.slice(-1)[0]?.ts.slice(11, 19) || ''; },
    proposal() { return this.detail?.event?.proposal?.proposal; },
    canDecide() { return this.state.mode === 'local' && this.detail?.event?.status === 'PENDING_APPROVAL' && !this.detail.approvals.length; },
    waitingUntil() { const w = this.detail?.workflow?.interrupts?.find(i => i.type === 'wait_until'); return w ? w.until.slice(11, 19) + ' 까지' : null; },
    flowSteps() {
      const st = this.detail?.event?.status, seen = new Set(this.detail.history.map(h => h.to_status));
      const steps = [['DETECTED', '감지'], ['EVIDENCE_READY', '근거 확인'], ['PENDING_APPROVAL', '승인 대기'], ['EXECUTED', '실행'], ['VERIFYING', '재측정'], ['CLOSED', '종결']];
      const out = steps.map(([k, l]) => ({ key: k, label: l, state: st === k ? 'now' : seen.has(k) ? 'done' : '' }));
      if (['ESCALATED', 'REJECTED', 'HOLD_NO_EVIDENCE', 'SENSOR_CHECK', 'VERIFY_HOLD'].includes(st)) out.push({ key: st, label: STATUS_KO[st], state: 'branch' });
      return out;
    },
  },
  methods: {
    x(ts) { const span = (this.t1 - this.t0) || 1; return this.PAD + (Date.parse(ts) - this.t0) / span * (this.W - this.PAD - 10); },
    y(v) { return 10 + (1 - (v - this.yMin) / (this.yMax - this.yMin)) * (this.H - 40); },
    fmt(v, d) { return v == null ? '-' : Number(v).toFixed(d); },
    lastOf(s) { const a = this.series[s]; return a?.length ? a[a.length - 1].value : null; },
    tempClass(t) { return t > 60 ? 'hot' : t > 55 ? 'warm' : ''; },
    statusKo: s => STATUS_KO[s] || s, typeKo: t => TYPE_KO[t] || t,
    decisionKo: d => ({ PROPOSE: '조치 제안', HOLD: '보류', SENSOR_CHECK: '센서 점검 제안', ESCALATE: '이관' }[d] || d),
    outcomeKo: o => ({ RECOVERED: '회복', NOT_IMPROVED: '미개선', INSUFFICIENT_DATA: '데이터 부족' }[o] || o),
    time: t => (t || '').slice(11, 19),
    short(v) { const s = typeof v === 'string' ? v : JSON.stringify(v); return s.length > 110 ? s.slice(0, 110) + '…' : s; },
    async refresh() {
      try {
        const [state, series, events] = await Promise.all([j('/api/state'), j('/api/series?asset_id=' + this.assetId + '&seconds=180'), j('/api/events')]);
        this.state = state; this.series = series.series; this.actions = series.actions; this.events = events;
        if (!this.assets.length) this.assets = await j('/api/assets');
        if (this.selectedId) this.detail = await j('/api/events/' + this.selectedId);
      } catch (e) { console.warn(e); }
    },
    async select(id) {
      this.selectedId = id; this.detail = await j('/api/events/' + id);
      const v = this.detail?.event?.proposal?.proposal?.value; if (v != null) this.approveValue = v;
    },
    async inject(kind) { await post('/api/sim/' + this.assetId + '/inject', { kind }); this.refresh(); },
    async reset() { this.selectedId = null; this.detail = null; await post('/api/control', { reset: true }); this.refresh(); },
    async decide(decision) {
      await post('/api/events/' + this.selectedId + '/decision', { approver: this.approver, decision, value: decision === 'APPROVED' ? this.approveValue : null });
      this.refresh();
    },
  },
  mounted() { this.refresh(); setInterval(this.refresh, 1000); },
}).mount('#app');
