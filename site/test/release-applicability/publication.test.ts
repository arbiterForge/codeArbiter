import { describe, expect, it } from 'vitest';
import { observedPublication, type CurrentGovernanceRelease } from '../../scripts/release-applicability';
import { presentProofApplicability } from '../../src/release-applicability-presentation';
const release:CurrentGovernanceRelease={target:'ca',tag:'v3.0.0',version:'3.0.0',publicationCommit:'a'.repeat(40),originalPublicationReceipt:'not-recorded'};
function observation(state='published') { return {format:'codearbiter.route-publication-observation/0.1.0',observed_at:'2026-11-13T12:00:00Z',source_commit:'b'.repeat(40),workflow_run:'123',release_visibility:'draft-inclusive',clock_starts:'confirmed-non-draft-github-release',removal_authorization:'not-evaluated',observations:[{target:'ca',tag:'v3.0.0',first_containing_version:'3.0.0',tag_commit:'a'.repeat(40),state,release_id:state==='tag-only'?null:42,release_draft:state==='tag-only'?null:state==='draft'}]}; }
describe('observed publication is distinct from source applicability',()=>{
 it('never calls an offline local tag or historical receipt published',()=>{
  expect(observedPublication(release,undefined)).toEqual({state:'unknown'});
  expect(observedPublication({...release,originalPublicationReceipt:'recorded'},undefined)).toEqual({state:'unknown'});
 });
 it.each(['published','draft','tag-only'])('retains exact observed %s state',state=>{
  expect(observedPublication(release,observation(state)).state).toBe(state);
 });
 it('refuses wrong tag/source/payload identity, duplicate rows and malformed observations',()=>{
  const wrongTag=observation();wrongTag.observations[0].tag='v2.0.0';
  const wrongCommit=observation();wrongCommit.observations[0].tag_commit='c'.repeat(40);
  const wrongVersion=observation();wrongVersion.observations[0].first_containing_version='2.0.0';
  const duplicate=observation();duplicate.observations.push(duplicate.observations[0]);
  const draft=observation();draft.observations[0].release_draft=true;
  for(const value of [wrongTag,wrongCommit,wrongVersion,duplicate,draft,{},null])expect(observedPublication(release,value).state).toBe('unknown');
 });
 it('keeps public-hidden/missing and unavailable observations unknown',()=>{
  const hidden=observation('tag-only');hidden.release_visibility='public';
  expect(observedPublication(release,hidden).state).toBe('unknown');
  expect(observedPublication(release,observation('api-unavailable')).state).toBe('unknown');
 });
 it('retains source matches while explicitly exposing unknown, draft or published state',()=>{
  for(const state of ['unknown','draft','published']){
   const result=presentProofApplicability({applicable:true,currentSource:{matchesReplay:true},publishedSource:{matchesReplay:true},publication:{state}});
   expect(result.isMismatch).toBe(false);expect(result.message).toContain(state==='published'?'observed published':`publication ${state}`);
  }
 });
});
