/* Regenerate golden outputs from the READ-ONLY original, not a JS rewrite.
   node tests/generate_js_reference.cjs <path/to/vocal/trainer/app.js>
   Origin: kinghost_www revision 41a5ec8dc9c6574cb025e6a4b3389d4a9c0a1009.
   Runtime tests consume the saved JSON and require neither Node nor the website. */
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const sourcePath = process.argv[2];
if (!sourcePath) throw new Error('Pass the read-only original trainer/app.js path.');
const source = fs.readFileSync(sourcePath, 'utf8');
const config = source.slice(source.indexOf('const CONFIG ='), source.indexOf('// DOM'));
const algorithm = source.slice(source.indexOf('const NOTE_TO_SEMITONE'), source.indexOf('function fmtSigned'));
const scoring = source.slice(source.indexOf('function globalGrade'), source.indexOf('function renderEvaluation'));
const context = vm.createContext({});
vm.runInContext(`${config}\n${algorithm}\n${scoring}\n
let expectedNotes = [];
const globalScoreEl = {};
globalThis.run = (scenario) => {
  expectedNotes = parseExercise(scenario.expected);
  const tracker = new SegmentTracker(expectedNotes, scenario.note_ms);
  for (const event of scenario.events) {
    if (event.midi == null) tracker.noPitch(event.t);
    else tracker.ingest({t:event.t, midi:event.midi, hz:midiToHz(event.midi), clarity:.99, rms:.2});
  }
  const segments = tracker.flush();
  const alignment = alignSegments(expectedNotes, segments);
  const rows = expectedNotes.map((expected,i) => alignment.assignments[i] == null ? null : analyzeMatchedSegment(segments[alignment.assignments[i]],expected));
  return {segments, alignment, rows:rows.map(r => r == null ? null : ({...r, tuning:gradeTuning(r), stability:gradeStability(r)})), global:renderGlobalScore(rows), outliers:tracker.outlierCount};
};`, context);
const tone = (start, end, midi, wobble = 0) => Array.from({length:Math.floor((end-start)/20)+1}, (_,i) => ({t:start+i*20,midi:midi + (i%2 ? wobble : -wobble)}));
const silence = (start,end) => Array.from({length:Math.floor((end-start)/20)+1},(_,i)=>({t:start+i*20,midi:null}));
const scenarios = [
  {name:'perfect_two_notes',expected:'A3 B3',note_ms:600,events:[...tone(0,580,57),...tone(600,1180,59)]},
  {name:'initial_glitches_and_excursion',expected:'A3 B3',note_ms:600,events:[{t:0,midi:70},{t:20,midi:50},...tone(40,260,57),{t:280,midi:74},...tone(300,580,57),...tone(600,1180,59.42)]},
  {name:'same_note_clock',expected:'E3 E3 E3',note_ms:500,events:tone(0,1480,52)},
  {name:'same_note_articulation',expected:'E3 E3',note_ms:1000,events:[...tone(0,380,52),...silence(400,460),...tone(480,900,52)]},
  {name:'long_pause_reacquire',expected:'C3 E3',note_ms:700,events:[...tone(0,380,48),...silence(400,660),...tone(680,1180,52)]},
  {name:'missing_middle_extra_segment',expected:'A3 C4 E4 G4',note_ms:500,events:[...tone(0,480,57),...tone(500,980,64),...tone(1000,1380,66),...tone(1400,1900,67)]},
  {name:'centered_variable_vs_biased_stable',expected:'A3 B3',note_ms:800,events:[...tone(0,780,57,.3),...tone(800,1580,59.55,.025)]},
  {name:'short_low_confidence',expected:'C3 D3',note_ms:200,events:[...tone(0,140,48),...tone(160,300,50)]},
  {name:'initial_unstable_pause_reset',expected:'A3',note_ms:1000,events:[{t:0,midi:47},{t:20,midi:63},...silence(40,300),...tone(320,1000,57)]},
  {name:'gradual_transition',expected:'A3 B3',note_ms:700,events:[...tone(0,580,57),{t:600,midi:57.9},{t:620,midi:58.3},{t:640,midi:58.8},...tone(660,1380,59)]},
  {name:'empty',expected:'A3 B3',note_ms:500,events:silence(0,1000)},
];
const output = {revision:'41a5ec8dc9c6574cb025e6a4b3389d4a9c0a1009', source_sha256:crypto.createHash('sha256').update(source).digest('hex'), scenarios:scenarios.map(s=>({...s,output:context.run(s)}))};
const destination = path.join(__dirname,'fixtures','js_tracker_reference.json');
fs.mkdirSync(path.dirname(destination),{recursive:true});
fs.writeFileSync(destination,JSON.stringify(output,null,2)+'\n');
process.stdout.write(`Saved ${scenarios.length} original-JS scenarios to ${destination}\n`);
