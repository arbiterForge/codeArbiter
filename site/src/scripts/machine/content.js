// The validated machine model, as the viewer modules read it.
// The page embeds the model that scripts/machine/machine-model.ts checked against the plugin sources at
// build time; setModel() turns it into the shapes the viewer uses. Exports are live bindings, so modules
// that import them see the model once mountMachine() has called setModel().
export let PARTS = {}, TOURS = [], ZONES = {}, FAMILIES = {}, HOSTS = {}, STATES = {}, LANE_ORDER = [], META = {};
export let SIMPLE = {}, GLOSSARY = [], FAULTS = [], LABS = {}, GATES = {}, KIND_FRAME = {}, FRAME_KEY = [], MOTION_KEY = [];

export function setModel(model) {
  PARTS = model.parts;
  TOURS = model.tours;
  ZONES = model.layout.zones;
  FAMILIES = model.layout.families;
  STATES = model.layout.states;
  LANE_ORDER = model.layout.laneOrder;
  HOSTS = Object.fromEntries(model.hosts.map((host) => [host.name, {
    name: host.label,
    omits: host.omits,
    fmt: (name) => host.commandForm.replace('{name}', name),
  }]));
  META = { version: `codeArbiter ${model.version}`, checked: model.provenance.reviewedAt.date, repo: 'https://github.com/arbiterForge/codeArbiter' };
  SIMPLE = Object.fromEntries(Object.entries(model.parts).map(([id, part]) => [id, part.simple]));
  GLOSSARY = model.glossary.map((entry) => [entry.term, entry.aliases, entry.definition, entry.part]);
  FAULTS = model.faults;
  LABS = model.labs;
  GATES = model.gates;
  KIND_FRAME = model.key.kindFrames;
  FRAME_KEY = model.key.frames.map((frame) => [frame.shape, frame.name, frame.meaning]);
  MOTION_KEY = model.key.motions.map((motion) => [motion.motion, motion.name, motion.meaning]);
}
