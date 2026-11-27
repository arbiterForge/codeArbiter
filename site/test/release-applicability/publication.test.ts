import { describe, expect, it } from 'vitest';
import { observedPublication, type CurrentGovernanceRelease } from '../../scripts/release-applicability';
import { presentProofApplicability } from '../../src/release-applicability-presentation';
const release:CurrentGovernanceRelease={target:'ca',tag:'v3.0.0',version:'3.0.0',publicationCommit:'a'.repeat(40),originalPublicationReceipt:'not-recorded'};
function observation(state='published') { return {format:'codearbiter.route-publication-observation/0.1.0',observed_at:'2026-11-13T12:00:00Z',source_commit:'b'.repeat(40),workflow_run:'123',release_visibility:'draft-inclusive',clock_starts:'confirmed-non-draft-github-release',removal_authorization:'not-evaluated',site_observations:[{target:'claude',tag:'v3.0.0',version:'3.0.0',tag_commit:'a'.repeat(40),state,release_id:state==='tag-only'?null:42,release_draft:state==='tag-only'?null:state==='draft'}]}; }
describe('observed publication is distinct from source applicability',()=>{
 it('never calls an offline local tag or historical receipt published',()=>{
  expect(observedPublication(release,undefined)).toEqual({state:'unknown'});
  expect(observedPublication({...release,originalPublicationReceipt:'recorded'},undefined)).toEqual({state:'unknown'});
 });
 it.each(['published','draft','tag-only'])('retains exact observed %s state',state=>{
  expect(observedPublication(release,observation(state)).state).toBe(state);
 });
 it('refuses wrong tag/source/payload identity, duplicate rows and malformed observations',()=>{
  const wrongTag=observation();wrongTag.site_observations[0].tag='v2.0.0';
  const wrongCommit=observation();wrongCommit.site_observations[0].tag_commit='c'.repeat(40);
  const wrongVersion=observation();wrongVersion.site_observations[0].version='2.0.0';
  const duplicate=observation();duplicate.site_observations.push(duplicate.site_observations[0]);
  const draft=observation();draft.site_observations[0].release_draft=true;
  for(const value of [wrongTag,wrongCommit,wrongVersion,duplicate,draft,{},null])expect(observedPublication(release,value).state).toBe('unknown');
 });
 it('keeps public-hidden/missing and unavailable observations unknown',()=>{
  const hidden=observation('tag-only');hidden.release_visibility='public';
  expect(observedPublication(release,hidden).state).toBe('unknown');
  expect(observedPublication(release,observation('api-unavailable'))).toMatchObject({
   state:'unknown',uncertainty:'api-unavailable',workflowRun:'123',
  });
 });
 it('keeps route-clock rows and site target aliases outside Docs authority',()=>{
  const site = observation();
  const onlyClock = { ...site, observations: site.site_observations, site_observations: undefined };
  expect(observedPublication(release,onlyClock)).toEqual({state:'unknown'});
  site.site_observations[0].target = 'ca';
  expect(observedPublication(release,site)).toEqual({state:'unknown'});
 });
 it('retains source matches while explicitly exposing unknown, draft or published state',()=>{
  for(const state of ['unknown','draft','published']){
   const result=presentProofApplicability({applicable:true,currentSource:{matchesReplay:true},publishedSource:{matchesReplay:true},publication:{state}});
   expect(result.isMismatch).toBe(false);expect(result.message).toContain(state==='published'?'observed published':`publication ${state}`);
  }
 });
});
