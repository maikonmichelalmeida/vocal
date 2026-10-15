/** Re-extract only the principal exercises. Never writes to the reference checkout.
 * Usage: node scripts/migrate_catalog.mjs PATH_TO_REFERENCE_VOCAL [DESTINATION_ROOT]
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const source = path.resolve(process.argv[2] || '');
const destination = path.resolve(process.argv[3] || path.join(path.dirname(fileURLToPath(import.meta.url)), '..'));
if (!process.argv[2] || source === destination || destination.startsWith(source + path.sep)) {
  throw new Error('Supply a separate read-only reference vocal directory.');
}
const sourceJs = fs.readFileSync(path.join(source, 'style.js'), 'utf8');
const revision = execFileSync('git', ['-C', source, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
function declaration(name) {
  const match = sourceJs.match(new RegExp(`^const ${name} = ([\\s\\S]*?);`, 'm'));
  if (!match) throw new Error(`Missing declaration: ${name}`);
  return `const ${name} = ${match[1]};`;
}
function functionSource(name) {
  const match = sourceJs.match(new RegExp(`^function ${name}\\([^]*?^}`, 'm'));
  if (!match) throw new Error(`Missing function: ${name}`);
  return match[0];
}
const names = ['EXERCISES', 'SESSIONS', 'SESSION_FOCUS', 'EXERCISE_TEMPO_DEFAULTS',
  'NOTE_TO_MIDI_CLASS', 'SHARP_NAMES', 'TRANSPOSE_MIN', 'TRANSPOSE_MAX', 'BPM_MIN', 'BPM_MAX'];
const functions = ['clampTranspose', 'clampBpm', 'clampSubdivision', 'getTrainingState',
  'noteToMidi', 'midiToNote', 'transposeNotes', 'noteTokens', 'bestExplicitSequence',
  'bpmFromText', 'defaultTempo', 'subdivisionFromText', 'breathingDurationFromText',
  'isUnpitchedSection', 'guideForSection', 'buildTrainingConfig'];
// No DOM, imports, network or filesystem APIs are exposed to the source functions.
// State persistence is irrelevant to the initial defaults and is deliberately stubbed.
const extracted = vm.runInNewContext([
  ...names.map(declaration),
  "const environment = { training: {}, instrument: 'acoustic_guitar_nylon' };",
  'function setTrainingState(key, state) { environment.training[key] = state; return state; }',
  ...functions.map(functionSource),
  '({exercises: EXERCISES, sessions: SESSIONS, session_focus: SESSION_FOCUS, tempo: EXERCISE_TEMPO_DEFAULTS, principal: EXERCISES.map(e => buildTrainingConfig(e))})',
].join('\n'), Object.create(null), { timeout: 2000 });
if (extracted.exercises.length !== 39) throw new Error('Expected 39 exercises.');
const assets = path.join(destination, 'assets');
fs.mkdirSync(assets, { recursive: true });
const resources = [];
for (const ex of extracted.exercises) {
  for (const kind of ['audio', 'image']) {
    const relative = ex[kind];
    if (relative === null && kind === 'image' && ex.id <= 3) continue;
    if (!relative || path.isAbsolute(relative) || relative.split('/').includes('..')) throw new Error('Invalid asset path');
    const from = path.join(source, relative);
    const to = path.join(assets, relative);
    // Case-sensitive membership check also works on Windows.
    if (!fs.readdirSync(path.dirname(from)).includes(path.basename(from))) throw new Error(`Incorrect source spelling: ${relative}`);
    const bytes = fs.readFileSync(from);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(from, to);
    if (!bytes.equals(fs.readFileSync(to))) throw new Error(`Copy mismatch: ${relative}`);
    resources.push({ exercise_id: ex.id, kind, path: relative, bytes: bytes.length, sha256: digest(bytes) });
  }
}
if (resources.filter(r => r.kind === 'audio').length !== 39 || resources.filter(r => r.kind === 'image').length !== 36) {
  throw new Error('Expected 39 MP3 and 36 PNG resources.');
}
const catalog = {
  schema_version: 1,
  source_revision: revision,
  exercises: extracted.exercises.map((ex, index) => {
    const config = extracted.principal[index];
    return { id: ex.id, name: ex.name, category: ex.type, objective: ex.objective,
      notes: ex.notes, variation: ex.variation, audio: ex.audio, image: ex.image,
      bpm: config.bpm, subdivision: config.subdivision,
      vocal_notes: config.vocalNotes, guide_notes: config.guideNotes,
      breathing_seconds: config.breathingDurationSec };
  }),
  sessions: extracted.sessions,
  session_focus: extracted.session_focus,
};
const sourceFiles = ['style.js', 'lesson-trainer.js'];
const manifest = {
  schema_version: 1,
  source_repository: 'https://github.com/maikonmichelalmeida/kinghost_www',
  source_revision: revision,
  source_files: Object.fromEntries(sourceFiles.map(name => [name, digest(fs.readFileSync(path.join(source, name)))])),
  resources,
};
for (const [filename, content] of [['catalog.json', catalog], ['manifest.json', manifest], ['principal-configs.json', extracted.principal]]) {
  fs.writeFileSync(path.join(assets, filename), JSON.stringify(content, null, 2) + '\n', 'utf8');
}
console.log(`Extracted 39 original principal configs, 39 MP3 and 36 PNG; source revision ${revision}.`);
