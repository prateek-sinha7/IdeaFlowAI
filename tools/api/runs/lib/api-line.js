// tools/api/runs/lib/api-line.js
// One shared console-line printer for the login/launch script blocks across
// every run.case*.http file -- keeps their look identical to stream-subscribe.js's
// output without re-declaring the same color/timestamp boilerplate each time.
module.exports = function apiLine(msg, color) {
	const NO_COLOR = !!process.env.NO_COLOR;
	const RESET = NO_COLOR ? '' : '\x1b[0m';
	const BOLD = NO_COLOR ? '' : '\x1b[1m';
	const PALETTE = NO_COLOR ? { api: '', warn: '', error: '' } : {
		api: '\x1b[38;2;37;99;235m',
		warn: '\x1b[38;2;180;83;9m',
		error: '\x1b[38;2;185;28;28m',
	};
	const C = PALETTE[color || 'api'] || PALETTE.api;
	const ts = () => new Date().toTimeString().slice(0, 8);
	process.stdout.write(ts() + '  ' + BOLD + C + 'api       ' + RESET + '  ' + msg + RESET + '\n');
};
