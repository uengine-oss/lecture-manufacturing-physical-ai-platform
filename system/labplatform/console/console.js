const { createApp } = Vue;
const j = (u, o) => fetch(u, o).then(async r => { const b = await r.json(); if (!r.ok) throw b; return b; });
const send = (m, u, b) => j(u, { method: m, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(b ?? {}) });
const TYPE_KO = { form: '폼', http: '시스템', agent: '에이전트', human: '사람', tool: '도구', end: '종료' };

createApp({
  data: () => ({
    tabs: [
      { id: 'home', label: '개요', layer: '' }, { id: 'fabric', label: 'Data Fabric', layer: 'DS' }, { id: 'studio', label: 'Ontology Studio', layer: 'ON' },
      { id: 'agents', label: 'Agents', layer: 'AG' }, { id: 'process', label: 'Processes', layer: 'OR' }, { id: 'apps', label: 'Apps', layer: 'OR' },
    ],
    tab: (location.hash || '#home').slice(1), overview: {}, datasources: [], sql: "SELECT event_id, asset_id, status FROM event ORDER BY created_at DESC", sqlRows: [],
    schemas: [], schema: null, validation: null, publishResult: null, objClass: 'Asset', objKey: 'asset_id', objVal: 'HYD-01', objResult: null, objError: null,
    gqAsset: 'HYD-01', gqEvent: '', golden: [], agentsList: [], skills: [], skillText: '', mcpServers: [], tools: [], toolName: 'get_asset_context', toolArgs: '{"asset_id": "HYD-01"}', toolResult: '',
    watches: [], watchResult: null, definitions: [], worklist: [], drafts: {}, instances: [], instanceId: null, instance: null,
    appsList: [], appTemplates: [], appName: 'hydops-ops', appTpl: 'ops-console', location: window.location,
  }),
  methods: {
    typeKo: t => TYPE_KO[t] || t,
    fmt(v) { if (v == null) return '-'; if (typeof v === 'object') return JSON.stringify(v); return String(v); },
    short(v) { const s = typeof v === 'string' ? v : JSON.stringify(v); return s.length > 120 ? s.slice(0, 120) + '…' : s; },
    go(t) { this.tab = t; location.hash = t; this.load(); },
    sampleArgs(t) { const a = {}; for (const k of Object.keys(t.args)) a[k] = k === 'asset_id' ? 'HYD-01' : k === 'event_type' ? 'COOLING_ANOMALY' : k === 'seconds' ? 60 : ''; return JSON.stringify(a); },
    async load() {
      const [ds, sc, ag, sk, ins, ap] = await Promise.all([j('/fabric/datasources'), j('/studio/schemas'), j('/agents'), j('/agents/skills'), j('/process/instances'), j('/apps')]);
      this.datasources = ds; this.schemas = sc; this.agentsList = ag; this.skills = sk; this.instances = ins; this.appsList = ap;
      this.overview = { datasources: ds.length, schemas: sc.length, published: sc.filter(s => s.published_version).length, agents: ag.length, skills: sk.length, instances: ins.length, apps: ap.length };
      if (this.tab === 'studio' && sc.length) this.schema = await j('/studio/schemas/' + sc[0].schema_name);
      if (this.tab === 'agents') {
        this.mcpServers = await j('/agents/mcp-servers'); this.watches = await j('/agents/watch');
        if (!this.tools.length && this.mcpServers.length) this.tools = await j('/agents/mcp-servers/' + this.mcpServers[0].name + '/tools').catch(() => []);
      }
      if (this.tab === 'process') {
        this.definitions = await j('/process/definitions'); const wl = await j('/process/worklist');
        for (const w of wl) if (!this.drafts[w.workitem_id]) this.drafts[w.workitem_id] = Object.fromEntries(w.form.filter(f => !f.readonly).map(f => [f.name, f.value ?? (f.type === 'select' ? f.options[0] : '')]));
        this.worklist = wl;
        if (this.instanceId) this.instance = await j('/process/instances/' + this.instanceId);
      }
      if (this.tab === 'apps') this.appTemplates = await j('/apps/templates');
      if (!this.gqEvent && ins.length) this.gqEvent = ins[0].event_id;
    },
    async runSql() { this.sqlRows = (await send('POST', '/fabric/datasources/hydops_edu/query', { sql: this.sql, limit: 20 })).rows; },
    async validate(n) { this.validation = await j('/studio/schemas/' + n + '/validate'); },
    async publish(n) { try { this.publishResult = await send('POST', '/studio/schemas/' + n + '/publish'); this.validation = null; } catch (e) { this.validation = e.detail; } this.load(); },
    async fetchObjects() {
      this.objError = null;
      try { this.objResult = await send('POST', `/studio/schemas/${this.schema.schema_name}/objects/${this.objClass}/fetch`, { filters: this.objVal ? { [this.objKey]: this.objVal } : {}, limit: 20 }); }
      catch (e) { this.objResult = null; this.objError = typeof e.detail === 'string' ? e.detail : JSON.stringify(e.detail); }
    },
    async runGolden() { this.golden = (await send('POST', `/studio/schemas/${this.schema.schema_name}/golden`, { params: { asset_id: this.gqAsset, event_id: this.gqEvent } })).results; },
    async openSkill(n) { this.skillText = (await j(`/agents/skills/${n}/files/SKILL.md`)).content; },
    async callTool() { try { const r = await send('POST', `/agents/mcp-servers/${this.mcpServers[0].name}/call`, { tool: this.toolName, args: JSON.parse(this.toolArgs) }); this.toolResult = JSON.stringify(r.result, null, 1).slice(0, 2500); } catch (e) { this.toolResult = JSON.stringify(e); } },
    async tickWatch(id) { this.watchResult = await send('POST', `/agents/watch/${id}/tick`); this.load(); },
    async toggleWatch(w) { await send('POST', '/agents/watch', { ...w, enabled: !w.enabled }); this.load(); },
    async completeWork(w) {
      const v = { ...this.drafts[w.workitem_id] }; if (v.approved_value !== '' && v.approved_value != null) v.approved_value = Number(v.approved_value); else v.approved_value = null;
      await send('POST', `/process/workitems/${encodeURIComponent(w.workitem_id)}/complete`, { values: v });
      this.instanceId = w.instance_id; this.load();
    },
    async openInstance(id) { this.instanceId = id; this.instance = await j('/process/instances/' + id); },
    async publishApp() {
      await send('POST', '/apps', { name: this.appName, template: this.appTpl, config: { hydops_api: 'http://localhost:8800', platform_api: 'http://localhost:8910', schema_name: 'HydraulicOps', process_def_id: 'cooling_response' } });
      this.load();
    },
  },
  mounted() { this.load(); setInterval(() => { if (['process', 'home', 'agents'].includes(this.tab)) this.load(); }, 2000); },
}).mount('#app');
