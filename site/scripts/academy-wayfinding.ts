/** Published track presentation, shared by the generator and reader-facing views. */
export const academyTracks = [
  { id: 'foundations', label: 'Foundation', description: 'Establish safe repository boundaries and learn the evidence-first delivery loop.' },
  { id: 'practitioner', label: 'Practitioner', description: 'Apply governed workflows to realistic features, fixes, reviews, and decisions.' },
  { id: 'power-user', label: 'Power user', description: 'Diagnose enforcement, tune governance, and operate advanced delivery paths with proof.' },
] as const;
export type AcademyTrackId = typeof academyTracks[number]['id'];
export type GuideNode = {
  id: string;
  track: string;
  title: string;
  prerequisites: readonly string[];
  nextLab: string | null;
};

/** Reading positions are not completion or permission to skip prerequisites. */
export function buildAcademyWayfinding(guides: readonly GuideNode[]) {
  const byId = new Map(guides.map(guide => [guide.id, guide]));
  if (byId.size !== guides.length) throw new Error('Academy navigation contains a duplicate lesson ID');
  for (const guide of guides) {
    if (!/^[FPU]\d{2}-[a-z0-9]+(?:-[a-z0-9]+)*$/.test(guide.id)) throw new Error(`Invalid Academy lesson ID: ${guide.id}`);
    if (!academyTracks.some(track => track.id === guide.track)) throw new Error(`Invalid Academy track: ${guide.track}`);
    if (guide.nextLab === guide.id) throw new Error(`Academy lesson cannot link to itself: ${guide.id}`);
    if (guide.nextLab !== null && !byId.has(guide.nextLab)) throw new Error(`Unknown Academy next lesson: ${guide.nextLab}`);
  }
  return guides.map((guide, index) => {
    const track = academyTracks.find(track => track.id === guide.track)!;
    const siblings = guides.filter(candidate => candidate.track === guide.track);
    return {
      id: guide.id,
      track,
      position: index + 1,
      total: guides.length,
      trackPosition: siblings.findIndex(candidate => candidate.id === guide.id) + 1,
      trackTotal: siblings.length,
      previousId: index === 0 ? null : guides[index - 1].id,
      // next_lab is authored by Academy. A missing successor is not inferred.
      nextId: guide.nextLab,
      prerequisites: guide.prerequisites.map(label => {
        const prerequisite = byId.get(label);
        return prerequisite
          ? { label: `${prerequisite.id.split('-')[0]} · ${prerequisite.title}`, lessonId: prerequisite.id }
          : { label, lessonId: null };
      }),
    };
  });
}
