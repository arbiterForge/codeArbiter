/// <reference lib="dom" />
/// <reference lib="dom.iterable" />
/** Presentation only. Custom-element lifecycle also covers Astro client navigation. */
class WorkflowAtlas extends HTMLElement {
  private controller?: AbortController;
  private printState: Array<{element:HTMLElement;hidden:boolean;open?:boolean}> = [];
  connectedCallback():void {
    this.controller?.abort();
    this.controller = new AbortController();
    const options={signal:this.controller.signal};
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
    const follow=(focus=false):boolean=>{
      let id:string;try{id=decodeURIComponent(location.hash.slice(1));}catch{return false;}
      const target=[...this.querySelectorAll<HTMLElement>('[id]')].find(e=>e.id===id);
      if(!target){if(id==='workflow-atlas'){showAll();return true;}return false;}
      const entry=entries.find(e=>e===target);
      const view=views.find(v=>v===target || v.contains(target));
      if(entry)choose(entry.dataset.atlasEntry!);else if(view)showView(view);else return false;
      for(let parent:HTMLElement|null=target;parent && parent!==this;parent=parent.parentElement){if(parent instanceof HTMLDetailsElement)parent.open=true;parent.hidden=false;}
      if(focus){const focusTarget=target instanceof HTMLDetailsElement?target.querySelector<HTMLElement>('summary')!:target;if(!(target instanceof HTMLDetailsElement))focusTarget.tabIndex=-1;focusTarget.focus({preventScroll:true});target.scrollIntoView({block:'start',behavior:'auto'});}
      return true;
    };
    select.addEventListener('change',()=>{if(select.value)choose(select.value);else showAll();},options);
    this.querySelector('[data-atlas-show-all]')!.addEventListener('click',()=>{showAll();select.focus();},options);
    this.querySelector<HTMLSelectElement>('[data-atlas-host-select]')!.addEventListener('change',event=>{
      const host=(event.currentTarget as HTMLSelectElement).value;
      this.querySelectorAll<HTMLElement>('[data-atlas-host]').forEach(el=>el.hidden=host!=='all' && el.dataset.atlasHost!==host);
    },options);
    // Native links own history. A chooser change alone never writes a bookmark.
    window.addEventListener('hashchange',()=>follow(true),options);
    this.addEventListener('click',event=>{const link=(event.target as Element).closest<HTMLAnchorElement>('a[href^="#"]');if(link && link.hash===location.hash)follow(true);},options);
    window.addEventListener('beforeprint',()=>{
      this.printState=[...this.querySelectorAll<HTMLElement>('[hidden],details')].map(element=>({element,hidden:element.hidden,open:element instanceof HTMLDetailsElement?element.open:undefined}));
      this.printState.forEach(({element})=>{element.hidden=false;if(element instanceof HTMLDetailsElement)element.open=true;});
    },options);
    window.addEventListener('afterprint',()=>{this.printState.forEach(({element,hidden,open})=>{element.hidden=hidden;if(element instanceof HTMLDetailsElement && open!==undefined)element.open=open;});this.printState=[];},options);
    controls.hidden=false;
    // An unrelated existing C04 chapter address must never be rewritten or focused.
    if(!follow(false))choose('feature');
  }
  disconnectedCallback():void {this.controller?.abort();this.printState=[];}
}
if(!customElements.get('ca-workflow-atlas'))customElements.define('ca-workflow-atlas',WorkflowAtlas);
