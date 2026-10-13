import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../webui/reasoning-effort-store.js', import.meta.url), 'utf8')
  .replace(/^import .*?;\n/gm, '')
  .replace('export const store =', 'const store =');
const requests = [], errors = [];
const api = {callJsonApi: (_url, data) => new Promise((resolve, reject) => requests.push({data, resolve, reject}))};
const store = new Function('createStore', 'api', 'toastFrontendError', 'chatsStore', source + '\nreturn model;')(
  (_name, model) => model, api, message => errors.push(message), {selectedContext: {running: true}},
);
store.contextId = 'active-chat';
const saving = store.select('low');
assert.deepEqual(requests[0].data, {action: 'set', context_id: 'active-chat', effort: 'low', custom: false});
assert.equal(await store.select('high'), false, 'concurrent saves must stay blocked');
requests[0].resolve({selected: 'low', effective: 'low'});
assert.equal(await saving, true, 'running chat rejected an effort change');
assert.equal(store.selected, 'low');

const failed = store.select('high');
requests[1].reject(new Error('save failed'));
assert.equal(await failed, false);
assert.deepEqual(errors, ['save failed']);
assert.equal(store.selected, 'low', 'failed save replaced the accepted effort');
const clearing = store.select('');
requests[2].resolve({selected: '', effective: 'medium', source: 'preset'});
assert.equal(await clearing, true, 'failed save left the selector locked');
assert.equal(store.selected, '');
assert.equal(store.effective, 'medium');
store.contextId = '';
assert.equal(await store.select('low'), false);
assert.equal(requests.length, 3);
console.log('reasoning-effort active-run store: ok');
