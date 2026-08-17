// tools/api/runs/lib/stream-subscribe.js
//
// The shared SSE event handler used by every run.case*.http file (and
// available to any other run.<pipeline>.http file that wants the same rich
// transcript instead of copy-pasting it). ONE place to fix a bug or add a
// new event type -- every case file picks it up for free.
//
// Usage from a `{{@streaming ...}}` block, which is already plain Node.js:
//
//   {{@streaming
//     if (!runId) { process.stdout.write('no runId -- launch failed, skipping stream\n'); return; }
//     await require('./lib/stream-subscribe.js')(runId, $requestClient);
//   }}
//
// Prints fanout bookkeeping, skill activation tracking, tool calls/results,
// agent prompts/output, hooks, gates, task progress -- nothing hidden.
// Event types this pipeline never emits (e.g. subagent_spawned on a
// non-fanout run) simply never fire; safe to reuse verbatim everywhere.

module.exports = async function subscribeAndPrint(runId, requestClient) {
	const NO_COLOR = !!process.env.NO_COLOR;
	const RESET = NO_COLOR ? '' : '\x1b[0m';
	const BOLD = NO_COLOR ? '' : '\x1b[1m';
	const DIM = NO_COLOR ? '' : '\x1b[2m';
	const C = NO_COLOR ? {
		api: '', engine: '', agent: '', tool: '', skill: '', hook: '', stream: '', chat: '', model: '', fanout: '', warn: '', error: '',
	} : {
		api: '\x1b[38;2;37;99;235m',
		engine: '\x1b[38;2;15;118;110m',
		agent: '\x1b[38;2;109;40;217m',
		tool: '\x1b[38;2;180;83;9m',
		skill: '\x1b[38;2;245;217;168m',
		hook: '\x1b[38;2;36;89;143m',
		stream: '\x1b[38;2;100;116;139m',
		chat: '\x1b[38;2;203;213;225m',
		model: '\x1b[38;2;185;212;244m',
		fanout: '\x1b[38;2;5;150;105m',
		warn: '\x1b[38;2;180;83;9m',
		error: '\x1b[38;2;185;28;28m',
	};
	const SKILL_PATH_RE = /(?:^|\/)\.?skills\/([^\/]+)\/SKILL\.md$/;
	const VERBOSE = !!process.env.RUN_VERBOSE;
	const out = (s) => process.stdout.write(s);
	const ts = () => new Date().toTimeString().slice(0, 8);
	const pad = (s) => (s + '          ').slice(0, 10);
	const line = (comp, color, msg) => out(ts() + '  ' + BOLD + color + pad(comp) + RESET + '  ' + msg + RESET + '\n');
	line('api', C.api, 'SSE /api/runs/' + runId + '/events/stream -> connected');

	let lineOpen = false;
	let currentAgent = null;
	let promptedAgent = null;
	let skilledAgent = null;
	const skillReads = [];
	let advertisedSkills = [];
	let estimatedTokens = 0;
	let toolCalls = 0;
	let outputHeaderShown = false;

	let firstSpawnAt = null;
	let lastSpawnAt = null;
	let firstResultAt = null;
	const spawned = [];
	const results = [];

	function printFanoutSummary() {
		if (!spawned.length) return;
		line('fanout', C.fanout, 'summary:');
		line('fanout', C.fanout, 'spawned: ' + spawned.length + ' worker(s): ' + spawned.map(s => s.agent).join(', '));
		const dispatchMs = (lastSpawnAt && firstSpawnAt) ? (lastSpawnAt - firstSpawnAt) : 0;
		line('fanout', C.fanout, 'dispatch spread: ' + dispatchMs + 'ms (all spawns are emitted before the gather)');
		if (firstSpawnAt && firstResultAt) {
			const groupSec = ((firstResultAt - firstSpawnAt) / 1000).toFixed(1);
			line('fanout', C.fanout, 'group wall clock: ' + groupSec + 's');
			line('fanout', C.fanout, 'per-worker start/end times are NOT in this stream — read them from');
			line('fanout', C.fanout, "  backend/runs/*/" + runId + "/.logs/run-logs.jsonl (grep step_)");
		}
		const failed = results.filter(r => r.status && r.status !== 'complete');
		if (failed.length) {
			line('fanout', C.fanout, C.error + 'FAILED workers: ' + failed.map(r => r.agent + '=' + r.status).join(', ') + RESET);
		} else {
			line('fanout', C.fanout, 'all workers completed');
		}
	}

	function printSkillSummary() {
		line('skill', C.skill, 'summary:');
		line('skill', C.skill, 'advertised: ' + (advertisedSkills.length ? advertisedSkills.join(', ') : '(none)'));
		if (skillReads.length) {
			for (const r of skillReads) {
				line('skill', C.skill, 'activated: ' + r.agent + " read '" + r.skill + "'");
			}
		} else {
			line('skill', C.skill, 'activated: (none -- no agent opened a skill)');
		}
		line('skill', C.skill, 'est cost: ' + (estimatedTokens ? '~' + estimatedTokens + ' tok/agent' : '(n/a)'));
	}

	function closeLine() { if (lineOpen) { out(RESET + '\n'); lineOpen = false; } }
	function short(v, n) {
		const s = typeof v === 'string' ? v : JSON.stringify(v);
		const flat = s.split('\n').join(' ');
		return flat.length > n ? flat.slice(0, n) + '...' : flat;
	}

	await new Promise((resolve) => {
		let done = false;
		const finish = () => { if (!done) { done = true; closeLine(); resolve(); } };
		requestClient.addEventListener('message', (evt) => {
			const [name, msg] = evt.detail;
			if (name === 'error') { if (!done) { closeLine(); line('stream', C.stream, C.error + 'SSE error ' + short(msg && msg.body, 120) + RESET); } finish(); return; }
			let data; try { data = JSON.parse(msg.body); } catch { data = null; }
			if (!data) return;
			if (VERBOSE) { closeLine(); line('stream', C.stream, DIM + 'raw ' + short(data, 300) + RESET); }
			const type = data.type;
			const d = data.data || {};

			if (type === 'subagent_spawned') {
				closeLine();
				const now = Date.now();
				if (firstSpawnAt === null) firstSpawnAt = now;
				lastSpawnAt = now;
				spawned.push({ worker: d.worker, agent: d.agent });
				line('fanout', C.fanout, 'spawned worker ' + d.worker + ' -> ' + d.agent
					+ (d.isolation ? ' [isolation=' + d.isolation + ']' : ''));
			} else if (type === 'subagent_result') {
				closeLine();
				if (firstResultAt === null) {
					firstResultAt = Date.now();
					const groupSec = ((firstResultAt - firstSpawnAt) / 1000).toFixed(1);
					line('fanout', C.fanout, 'first worker returned after ' + groupSec + 's');
				}
				results.push({ worker: d.worker, agent: d.agent, status: d.status });
				const statusColor = d.status === 'complete' ? '' : C.error;
				line('fanout', C.fanout, 'worker ' + d.worker + ' (' + d.agent + ') -> ' + statusColor + (d.status || '?') + RESET);
			} else if (type === 'agent_start') {
				if (d.agent_id === currentAgent) return;
				currentAgent = d.agent_id;
				toolCalls = 0;
				outputHeaderShown = false;
				closeLine();
				out('\n');
				line('agent', C.agent, BOLD + '==> ' + String(d.agent_id).toUpperCase() + (d.name ? ' (' + String(d.name).toUpperCase() + ')' : '') + RESET);
			} else if (type === 'agent_input') {
				if (d.agent_id === promptedAgent) return;
				promptedAgent = d.agent_id;
				closeLine();
				const prompt = (d.context_message || '').trim();
				line('agent', C.agent, d.agent_id + ' prompt (' + prompt.length + ' chars):');
				out(DIM + prompt.replace(/^/gm, '    ') + RESET + '\n');
			} else if (type === 'agent_skills') {
				if (d.agent_id === skilledAgent) return;
				skilledAgent = d.agent_id;
				closeLine();
				const skillNames = (d.attached_skills || []).map(s => s.name || '(unnamed)');
				const skills = skillNames.join(', ') || '(none)';
				const hooks = (d.attached_hooks || []).join(', ') || '(none)';
				const tokens = d.estimated_tokens || 0;
				if (skillNames.length && !advertisedSkills.length) advertisedSkills = skillNames.map(n => n.toLowerCase());
				if (tokens) estimatedTokens = tokens;
				line('skill', C.skill, 'advertised: ' + skills + (tokens ? ' (~' + tokens + ' tok/agent)' : ''));
				line('skill', C.skill, 'hooks: ' + hooks);
				const loadErrors = d.skills_load_errors || [];
				if (loadErrors.length) {
					line('skill', C.skill, C.error + 'SKILL LOAD ERRORS: ' + loadErrors.join('; ') + RESET);
				}
			} else if (type === 'tool_call') {
				closeLine();
				toolCalls++;
				let skillId = null;
				if (d.tool === 'read_file' && d.args) {
					const candidates = [d.args.file_path, d.args.path, ...Object.values(d.args).filter(v => typeof v === 'string')];
					for (const c of candidates) {
						const m = c && String(c).match(SKILL_PATH_RE);
						if (m) { skillId = m[1]; break; }
					}
				}
				if (skillId) {
					skillReads.push({ agent: currentAgent, skill: skillId });
					line('skill', C.skill, 'USED ' + currentAgent + " read '" + skillId + "'");
				} else {
					line('tool', C.tool, d.tool + ' input=' + short(d.args, 80));
				}
			} else if (type === 'tool_result') {
				closeLine();
				line('tool', C.tool, d.tool + ' output=' + short(d.result, 80));
			} else if (type === 'agent_chunk') {
				if (!outputHeaderShown) {
					closeLine();
					line('model', C.model, 'output:');
					outputHeaderShown = true;
				}
				if (!lineOpen) { out('    '); lineOpen = true; }
				out(d.chunk || '');
			} else if (type === 'agent_complete') {
				closeLine();
				const toolNote = toolCalls === 0
					? C.warn + 'NO TOOL CALLS' + RESET
					: toolCalls + ' tool call' + (toolCalls === 1 ? '' : 's');
				line('agent', C.agent, (d.agent_id || currentAgent) + ' complete ' + (d.duration || '?') + 's ' + (d.total_tokens || '?') + ' tok ' + toolNote);
			} else if (type === 'artifact_fallback') {
				closeLine();
				line('engine', C.engine, C.warn + 'artifact_fallback ' + (d.agent_id || '?') + ' -> ' + (d.filename || '?')
					+ ' (the model did not write it itself)' + RESET);
			} else if (type === 'gate_blocked') {
				closeLine();
				const issues = (data.issues || d.issues || []).map(i => i.severity + ' ' + i.validator + ': ' + i.message).join('; ');
				line('engine', C.engine, C.warn + 'WARN gate ' + (data.gate || d.gate) + ' blocked -- ' + short(issues, 120) + RESET);
			} else if (type === 'pipeline_complete') {
				closeLine();
				line('engine', C.engine, 'pipeline complete');
				printFanoutSummary();
				printSkillSummary();
				finish();
			} else if (['pipeline_failed', 'pipeline_cancelled', 'budget_aborted', 'error'].includes(type)) {
				closeLine();
				line('engine', C.engine, C.error + type + RESET);
				printFanoutSummary();
				finish();
			} else if (type === 'pipeline_start') {
				closeLine();
				line('engine', C.engine, 'pipeline start' + (d.pipeline_type ? ' ' + d.pipeline_type : ''));
			} else if (type === 'agent_error') {
				closeLine();
				line('agent', C.agent, C.error + (d.agent_id || '?') + ' error: ' + short(d.error, 160) + RESET);
			} else if (type === 'task_progress') {
				closeLine();
				const tasks = d.completed_tasks || [];
				const last = tasks[tasks.length - 1];
				line('engine', C.engine, 'task ' + (d.completed_count || tasks.length) + (last && last.title ? ': ' + last.title : ''));
			} else if (type === 'hook_run') {
				closeLine();
				const sev = (d.severity || '').toLowerCase();
				const msgColor = sev === 'error' ? C.error : (sev === 'warn' || sev === 'warning') ? C.warn : '';
				const msg2 = (d.event || '?') + ' [' + (d.hook_type || '?') + '] -> ' + (d.outcome || '?') + (d.summary ? ': ' + d.summary : '');
				line('hook', C.hook, msgColor + msg2 + RESET);
			} else if (type === 'workflow_validated') {
				closeLine();
				line('engine', C.engine, 'workflow validated: ' + ((d.dag_edges || []).length) + ' dag edges' + (typeof d.satisfiable === 'boolean' ? ' satisfiable=' + d.satisfiable : ''));
			} else if (type === 'stream_attached') {
				closeLine();
				line('stream', C.stream, 'attached live=' + d.live + ' replayed_through_seq=' + (d.replayed_through_seq || 0));
			} else if (type === 'chat_reply') {
				closeLine();
				line('chat', C.chat, 'chat card' + (d.card_kind ? ' (' + d.card_kind + ')' : ''));
			} else if (type) {
				closeLine();
				line('stream', C.stream, DIM + type + ' ' + short(d && Object.keys(d).length ? d : data, 100) + RESET);
			}
		});
		requestClient.addEventListener('disconnect', finish);
		setTimeout(finish, 12 * 60 * 1000);
	});
};
