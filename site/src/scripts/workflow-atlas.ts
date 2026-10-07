/// <reference lib="dom" />
/// <reference lib="dom.iterable" />
/** Presentation only. Custom-element lifecycle also covers Astro client navigation. */
class WorkflowAtlas extends HTMLElement {
  private controller?: AbortController;
  private printState: Array<{element:HTMLElement;hidden:boolean;open?:boolean}> = [];
  connectedCallback():void {
    this.controller?.abort();
    this.controller = new AbortController();
    const controller=this.controller;
    const options={signal:controller.signal};
    let frame=0;
    let focusTarget:HTMLElement|undefined;
    const cancelFocus=()=>{cancelAnimationFrame(frame);focusTarget=undefined;};
    const entries=[...this.querySelectorAll<HTMLDetailsElement>('[data-atlas-entry]')];
    const views=[...this.querySelectorAll<HTMLDetailsElement>('[data-atlas-view]')];
    const select=this.querySelector<HTMLSelectElement>('[data-atlas-select]')!;
    const status=this.querySelector<HTMLElement>('[data-atlas-status]')!;
    const permalink=this.querySelector<HTMLAnchorElement>('[data-atlas-permalink]')!;
    const controls=this.querySelector<HTMLElement>('[data-atlas-controls]')!;
    const showAll=()=>{entries.forEach(e=>e.hidden=false);views.forEach(v=>v.hidden=false);select.value='';status.textContent='All entries and reading paths are available. This is not an execution checklist.';permalink.href='#workflow-atlas';};
    const choose=(id:string):boolean=>{
      const entry=entries.find(e=>e.dataset.atlasEntry===id);
      if(!entry) return false;
      entries.forEach(e=>e.hidden=e!==entry);entry.open=true;
      const selected=new Set((entry.dataset.views??'').split(' ').filter(Boolean));
      views.forEach(view=>{view.hidden=!selected.has(view.dataset.atlasView!);});
      select.value=id;permalink.href=`#${entry.id}`;
      status.textContent=`Showing /${id}, its exact procedure and ${selected.size} related maps. Expand a map to read its complete path.`;
      return true;
    };
    const showView=(view:HTMLDetailsElement)=>{entries.forEach(e=>e.hidden=true);views.forEach(v=>v.hidden=v!==view);view.open=true;select.value='';permalink.href=`#${view.id}`;status.textContent='Showing a source-traced map. Reading it does not perform or approve the work.';};
    const follow=(hash:string,focus=false):boolean=>{
      // Match literal IDs only. The offline edition has no module dependencies.
      if(!hash.startsWith('#') || hash.length<2 || hash.length>1024)return false;
      let id:string;try{id=decodeURIComponent(hash.slice(1));}catch{return false;}
      const target=[...this.querySelectorAll<HTMLElement>('[id]')].find(e=>e.id===id);
      if(!target){if(id==='workflow-atlas'){showAll();return true;}return false;}
      const entry=entries.find(e=>e===target);
      const view=views.find(v=>v===target || v.contains(target));
      if(entry)choose(entry.dataset.atlasEntry!);else if(view)showView(view);else return false;
      for(let parent:HTMLElement|null=target;parent && parent!==this;parent=parent.parentElement){if(parent instanceof HTMLDetailsElement)parent.open=true;parent.hidden=false;}
      if(focus)focusTarget=target;
      cancelAnimationFrame(frame);
      frame=requestAnimationFrame(()=>{
        if(controller.signal.aborted || !target.isConnected)return;
        if(focusTarget===target){
          const element=target instanceof HTMLDetailsElement ? target.querySelector<HTMLElement>('summary')! : target;
          if(!(target instanceof HTMLDetailsElement))element.tabIndex=-1;
          element.focus({preventScroll:true});focusTarget=undefined;
        }
        target.scrollIntoView({block:'start',behavior:'instant'});
      });
      return true;
    };
    select.addEventListener('change',()=>{cancelFocus();if(select.value)choose(select.value);else showAll();},options);
    this.querySelector('[data-atlas-show-all]')!.addEventListener('click',()=>{cancelFocus();showAll();select.focus();},options);
    this.querySelector<HTMLSelectElement>('[data-atlas-host-select]')!.addEventListener('change',event=>{
      const host=(event.currentTarget as HTMLSelectElement).value;
      this.querySelectorAll<HTMLElement>('[data-atlas-host]').forEach(el=>el.hidden=host!=='all' && el.dataset.atlasHost!==host);
    },options);
    // Native links own history. A chooser change alone never writes a bookmark.
    const readLocation=()=>follow(location.hash);
    window.addEventListener('hashchange',readLocation,options);
    window.addEventListener('popstate',readLocation,options);
    document.addEventListener('astro:page-load',readLocation,options);
    this.addEventListener('click',event=>{
      if(!(event instanceof MouseEvent) || event.defaultPrevented || event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)return;
      const link=event.target instanceof Element ? event.target.closest<HTMLAnchorElement>('a[href^="#"]') : null;
      if(!link || link.target || link.hasAttribute('download'))return;
      // Astro can pushState for a same-page link without a hashchange event.
      // Reveal the clicked destination after native routing, including a repeated
      // fragment. Do not prevent navigation or write a second history entry.
      const requestedHash=link.hash;
      queueMicrotask(()=>{if(!controller.signal.aborted)follow(requestedHash,true);});
    },options);
    window.addEventListener('beforeprint',()=>{
      // Repeated preview events must not replace the original reading selection.
      if(this.printState.length)return;
      this.printState=[...this.querySelectorAll<HTMLElement>('[hidden],details')].map(element=>({element,hidden:element.hidden,open:element instanceof HTMLDetailsElement?element.open:undefined}));
      this.printState.forEach(({element})=>{element.hidden=false;if(element instanceof HTMLDetailsElement)element.open=true;});
    },options);
    window.addEventListener('afterprint',()=>{this.printState.forEach(({element,hidden,open})=>{element.hidden=hidden;if(element instanceof HTMLDetailsElement && open!==undefined)element.open=open;});this.printState=[];},options);
    controller.signal.addEventListener('abort',cancelFocus,{once:true});
    controls.hidden=false;
    // An unrelated existing C04 chapter address must never be rewritten or focused.
    if(!follow(location.hash))choose('feature');
  }
  disconnectedCallback():void {this.controller?.abort();this.printState=[];}
}
if(!customElements.get('ca-workflow-atlas'))customElements.define('ca-workflow-atlas',WorkflowAtlas);
