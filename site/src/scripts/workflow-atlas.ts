/// <reference lib="dom" />
/// <reference lib="dom.iterable" />
import type {Atlas,AtlasView,AtlasNode} from '../../scripts/execution-maps/atlas-model';

/** Port of the original standalone viewer: one live SVG, independent entry
 * highlighting, a persistent inspector, pan/zoom and complete-vector export. */
class WorkflowAtlas extends HTMLElement {
  private controller?:AbortController;
  private observer?:ResizeObserver;
  private frames=new Set<number>();
  private urls=new Set<string>();
  private atlas!:Atlas;
  private active!:AtlasView;
  private route='';
  private selected='';
  private scale=1;
  private fitMode:'width'|'all'|'manual'='width';
  private stage!:HTMLElement;
  private inspector!:HTMLElement;
  private select!:HTMLSelectElement;
  private templates=new Map<string,HTMLTemplateElement>();
  private drag?:{x:number;y:number;left:number;top:number;pointer:number};
  private printOpen:boolean|undefined;
  private q<T extends Element=HTMLElement>(selector:string):T {
    const element=this.querySelector<T>(selector);if(!element)throw new Error(`Incomplete atlas: ${selector}`);return element;
  }
  private later(callback:()=>void):void {
    const controller=this.controller;const frame=requestAnimationFrame(()=>{this.frames.delete(frame);if(this.isConnected && !controller?.signal.aborted)callback();});this.frames.add(frame);
  }
  connectedCallback():void {
    this.controller?.abort();this.observer?.disconnect();
    this.controller=new AbortController();const controller=this.controller,options={signal:controller.signal};
    this.atlas=JSON.parse(this.q('[data-atlas-data]').textContent??'') as Atlas;
    this.stage=this.q('[data-atlas-stage]');this.inspector=this.q('[data-atlas-inspector]');this.select=this.q('[data-atlas-select]');
    this.templates=new Map([...this.querySelectorAll<HTMLTemplateElement>('[data-svg-template]')].map(t=>[t.dataset.svgTemplate!,t]));
    this.querySelectorAll<HTMLElement>('[data-atlas-controls]').forEach(el=>el.hidden=false);
    this.select.addEventListener('change',()=>this.choose(this.select.value),options);
    this.addEventListener('click',event=>{
      const target=event.target instanceof Element?event.target:null;if(!target)return;
      const view=target.closest<HTMLButtonElement>('button[data-atlas-view]');if(view){this.show(view.dataset.atlasView!);return;}
      const chip=target.closest<HTMLButtonElement>('button[data-route]');if(chip){this.choose(chip.dataset.route!);return;}
      const jump=target.closest<HTMLButtonElement>('button[data-jump]');if(jump){this.show(jump.dataset.jump!);this.stage.scrollIntoView({block:'nearest'});return;}
      const action=target.closest<HTMLElement>('[data-action]')?.dataset.action;
      if(action==='clear')this.choose('');
      if(action==='fit-width')this.fit('width');
      if(action==='fit-all')this.fit('all');
      if(action==='read-size')this.readSize();
      if(action==='plus' || action==='minus'){this.fitMode='manual';this.resize(this.scale*(action==='plus'?1.22:1/1.22));}
      if(action==='export')this.exportSvg();
      if(action==='sources')this.q<HTMLDialogElement>('[data-source-dialog]').showModal();
      if(action==='close-sources')this.q<HTMLDialogElement>('[data-source-dialog]').close();
      if(action==='details')this.inspector.scrollIntoView({block:'start'});
      if(!(event instanceof MouseEvent) || event.defaultPrevented || event.button!==0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey)return;
      const link=target.closest<HTMLAnchorElement>('a[href^="#"]');
      if(!link || link.target || link.hasAttribute('download'))return;
      // Keep the previously repaired Astro seam: an explicit native link can
      // pushState without hashchange. Read its literal destination, not a selector.
      const hash=link.hash;queueMicrotask(()=>{if(!controller.signal.aborted)this.follow(hash,true);});
    },options);
    this.stage.addEventListener('click',event=>{
      if(!(event.target instanceof Element) || event.target.closest('a'))return;
      const node=event.target.closest<SVGElement>('[data-node]');if(node)this.inspect(node.dataset.node!);
    },options);
    this.stage.addEventListener('keydown',event=>{
      const target=event.target instanceof Element?event.target:null;
      if(target?.closest('a'))return;
      const node=target?.closest<SVGElement>('[data-node]');
      if(node && (event.key==='Enter'||event.key===' ')){event.preventDefault();this.inspect(node.dataset.node!);return;}
      if(['+','=','-','0','Escape'].includes(event.key))event.preventDefault();
      if(event.key==='+' || event.key==='=' || event.key==='-'){this.fitMode='manual';this.resize(this.scale*(event.key==='-'?1/1.22:1.22));}
      if(event.key==='0')this.fit('width');
      if(event.key==='Escape')this.choose('');
    },options);
    this.stage.addEventListener('wheel',event=>{
      if(event.ctrlKey || event.metaKey){event.preventDefault();this.fitMode='manual';this.resize(this.scale*(event.deltaY<0?1.12:1/1.12));}
    },{...options,passive:false});
    this.stage.addEventListener('pointerdown',event=>{
      if(event.pointerType!=='mouse' || event.button!==0 || !(event.target instanceof Element) || event.target.closest('[data-node],a'))return;
      this.drag={x:event.clientX,y:event.clientY,left:this.stage.scrollLeft,top:this.stage.scrollTop,pointer:event.pointerId};
      this.stage.setPointerCapture(event.pointerId);this.stage.classList.add('dragging');
    },options);
    this.stage.addEventListener('pointermove',event=>{if(this.drag){this.stage.scrollLeft=this.drag.left-event.clientX+this.drag.x;this.stage.scrollTop=this.drag.top-event.clientY+this.drag.y;}},options);
    for(const event of ['pointerup','pointercancel','lostpointercapture'])this.stage.addEventListener(event,()=>{this.drag=undefined;this.stage.classList.remove('dragging');},options);
    const locationChanged=()=>this.follow(location.hash);
    window.addEventListener('hashchange',locationChanged,options);
    window.addEventListener('popstate',locationChanged,options);
    document.addEventListener('astro:page-load',locationChanged,options);
    window.addEventListener('beforeprint',()=>{
      if(this.printOpen!==undefined)return;
      const reading=this.q<HTMLDetailsElement>('.reading-wrap');this.printOpen=reading.open;reading.open=true;
    },options);
    window.addEventListener('afterprint',()=>{
      if(this.printOpen===undefined)return;
      this.q<HTMLDetailsElement>('.reading-wrap').open=this.printOpen;this.printOpen=undefined;
    },options);
    this.q<HTMLDialogElement>('[data-source-dialog]').addEventListener('click',event=>{
      if(event.target===event.currentTarget)this.q<HTMLDialogElement>('[data-source-dialog]').close();
    },options);
    this.observer=new ResizeObserver(()=>{if(this.printOpen===undefined && this.fitMode!=='manual')this.later(()=>this.fit(this.fitMode==='all'?'all':'width'));});
    this.observer.observe(this.stage);
    this.route='';this.show(this.atlas.views[0].id);
    this.follow(location.hash);
    controller.signal.addEventListener('abort',()=>{
      this.frames.forEach(cancelAnimationFrame);this.frames.clear();this.observer?.disconnect();
      if(this.drag && this.stage.hasPointerCapture(this.drag.pointer))this.stage.releasePointerCapture(this.drag.pointer);
      this.drag=undefined;this.urls.forEach(URL.revokeObjectURL);this.urls.clear();
    },{once:true});
  }
  disconnectedCallback():void {
    if(this.printOpen!==undefined){this.q<HTMLDetailsElement>('.reading-wrap').open=this.printOpen;this.printOpen=undefined;}
    this.controller?.abort();
  }
  private resize(value:number,preserve=true):void {
    const old=this.scale,middleX=(this.stage.scrollLeft+this.stage.clientWidth/2)/old,middleY=(this.stage.scrollTop+this.stage.clientHeight/2)/old;
    this.scale=Math.min(2,Math.max(.1,value));
    const svg=this.stage.querySelector<SVGSVGElement>('svg');if(!svg)return;
    svg.style.width=`${this.active.width*this.scale}px`;svg.style.height=`${this.active.height*this.scale}px`;
    this.q('[data-zoom]').textContent=`${Math.round(this.scale*100)}%`;
    this.dataset.zoom=String(this.scale);
    if(preserve){this.stage.scrollLeft=middleX*this.scale-this.stage.clientWidth/2;this.stage.scrollTop=middleY*this.scale-this.stage.clientHeight/2;}
  }
  private fit(mode:'width'|'all'):void {
    if(!this.active || !this.stage.clientWidth || this.printOpen!==undefined)return;
    this.fitMode=mode;
    this.resize(mode==='all'?Math.min(this.stage.clientWidth/this.active.width,this.stage.clientHeight/this.active.height):this.stage.clientWidth/this.active.width,false);
    this.stage.scrollLeft=0;this.stage.scrollTop=0;
  }
  private show(id:string):void {
    const view=this.atlas.views.find(v=>v.id===id),template=this.templates.get(id);if(!view || !template)return;
    this.active=view;this.selected='';this.stage.replaceChildren(template.content.cloneNode(true));
    this.querySelectorAll<HTMLButtonElement>('button[data-atlas-view]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.atlasView===id)));
    this.dataset.activeView=id;this.fit('width');this.highlight();this.details();
  }
  private choose(name:string):void {
    this.route=this.atlas.commands.some(c=>c.name===name)?name:'';this.selected='';this.select.value=this.route;
    this.highlight();this.details();if(this.route && this.clientWidth<=900)this.readSize();
  }
  private highlight():void {
    const nodes=new Map(this.active.nodes.map(n=>[n.id,n]));
    this.stage.querySelectorAll<SVGElement>('[data-node]').forEach(el=>{
      el.classList.toggle('dim',!!this.route&&!nodes.get(el.dataset.node!)?.routes.includes(this.route));
      el.classList.toggle('selected',el.dataset.node===this.selected);
      el.setAttribute('aria-pressed',String(el.dataset.node===this.selected));
    });
    this.stage.querySelectorAll<SVGElement>('.node-source').forEach(el=>el.classList.toggle('dim',!!this.route&&!nodes.get(el.dataset.forNode!)?.routes.includes(this.route)));
    this.stage.querySelectorAll<SVGElement>('.edge').forEach((el,i)=>{
      const edge=this.active.edges[i];const relevant=edge.routes.length?edge.routes.includes(this.route):nodes.get(edge.a)?.routes.includes(this.route)&&nodes.get(edge.b)?.routes.includes(this.route);
      el.classList.toggle('dim',!!this.route&&!relevant);
    });
    this.q('[data-atlas-status]').textContent=this.route?`/${this.route} · ${this.active.nodes.filter(n=>n.routes.includes(this.route)).length} related nodes in this view`:`${this.active.title} · ${this.active.nodes.length} nodes`;
    this.dataset.route=this.route;this.dataset.selectedNode=this.selected;
    this.q<HTMLAnchorElement>('[data-atlas-permalink]').href=this.selected?`#atlas-node-${this.active.id}-${this.selected}`:`#atlas-view-${this.active.id}${this.route?'~'+this.route:''}`;
  }
  private template(kind:string,id:string):DocumentFragment|undefined {
    return [...this.querySelectorAll<HTMLTemplateElement>(`template[data-${kind}]`)].find(t=>t.getAttribute(`data-${kind}`)===id)?.content.cloneNode(true) as DocumentFragment|undefined;
  }
  private details():void {
    const fragment=this.template(this.selected?'node-inspector':this.route?'command-inspector':'view-inspector',this.selected||this.route||this.active.id);
    if(fragment)this.inspector.replaceChildren(fragment);
    if(this.route && !this.selected) {
      const related=this.atlas.views.filter(v=>v.nodes.some(n=>n.routes.includes(this.route)));
      const label=document.createElement('h4');label.textContent='Shown in';this.inspector.append(label);
      const choices=document.createElement('div');choices.className='chips';
      for(const view of related){const button=document.createElement('button');button.type='button';button.dataset.jump=view.id;button.textContent=view.tab_label;choices.append(button);}this.inspector.append(choices);
      if(!this.active.nodes.some(n=>n.routes.includes(this.route))){const note=document.createElement('p');note.className='notice';note.textContent='This entry is not drawn in the selected view. Choose one of its related maps below.';this.inspector.prepend(note);}
    }
  }
  private inspect(id:string):void {if(!this.active.nodes.some(n=>n.id===id))return;this.selected=id;this.highlight();this.details();}
  private readSize(node?:AtlasNode):void {
    this.fitMode='manual';this.resize(.85,false);
    const target=node??this.active.nodes.find(n=>n.kind==='cmd'&&(!this.route||n.title.includes('/'+this.route)))??this.active.nodes.find(n=>n.routes.includes(this.route))??this.active.nodes[0];
    this.stage.scrollLeft=Math.max(0,target.x*this.scale-25);this.stage.scrollTop=Math.max(0,target.y*this.scale-65);
  }
  private follow(hash:string,focus=false):boolean {
    if(!hash.startsWith('#') || hash.length<2 || hash.length>1024)return false;
    let id:string;try{id=decodeURIComponent(hash.slice(1));}catch{return false;}
    if(id==='atlas-reading' || id.startsWith('atlas-read-')) {
      const target=[...this.querySelectorAll<HTMLElement>('.reading-wrap [id],.reading-wrap')].find(e=>e.id===id);if(!target)return false;
      this.q<HTMLDetailsElement>('.reading-wrap').open=true;
      this.later(()=>{target.scrollIntoView({block:'start'});if(focus){target.tabIndex=-1;target.focus({preventScroll:true});}});return true;
    }
    const command=this.atlas.commands.find(c=>'atlas-'+c.name===id);
    const aliases:Record<string,string>={feature:'feature-sprint',sprint:'feature-sprint','debug-fix':'debug-handoff',tribunal:'tribunal-lifecycle',brownfield:'brownfield-lifecycle',greenfield:'knowledge-operations',dependency:'change-lanes',adr:'knowledge-operations',release:'review-delivery'};
    let view:AtlasView|undefined,node:AtlasNode|undefined,route='';
    if(command) {
      route=command.name;
      const preferred:Record<string,string>={feature:'feature-sprint',sprint:'feature-sprint',fix:'change-lanes',debug:'debug-handoff',tribunal:'tribunal-lifecycle',init:'brownfield-lifecycle','create-context':'brownfield-lifecycle',decompose:'knowledge-operations',review:'review-delivery',commit:'review-delivery',pr:'review-delivery',release:'review-delivery'};
      view=this.atlas.views.find(v=>v.id===preferred[route])??this.atlas.views.find(v=>v.nodes.some(n=>n.routes.includes(route)));
    } else if(id.startsWith('atlas-node-')) {
      for(const candidate of this.atlas.views){const found=candidate.nodes.find(n=>`atlas-node-${candidate.id}-${n.id}`===id);if(found){view=candidate;node=found;break;}}
    } else {
      const parts=id.replace(/^atlas-view-/,'').split('~');
      if(parts.length>2 || (parts[1]&&!this.atlas.commands.some(c=>c.name===parts[1])))return false;
      view=this.atlas.views.find(v=>v.id===(aliases[parts[0]]??parts[0]));route=parts[1]??'';
    }
    if(!view)return false;
    this.route=route;this.select.value=route;this.show(view.id);if(node){this.inspect(node.id);this.readSize(node);}
    this.later(()=>{
      if(node){this.readSize(node);if(focus)this.stage.querySelector<SVGElement>(`[data-node="${node.id}"]`)?.focus({preventScroll:true});}
      else if(focus)this.stage.focus({preventScroll:true});
      this.stage.scrollIntoView({block:'nearest',behavior:'instant'});
    });
    return true;
  }
  private exportSvg():void {
    const template=this.templates.get(this.active.id);if(!template)return;
    const url=URL.createObjectURL(new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n',template.innerHTML],{type:'image/svg+xml'}));this.urls.add(url);
    const link=document.createElement('a');link.href=url;link.download=`codearbiter-${this.active.id}.svg`;link.click();
    setTimeout(()=>{URL.revokeObjectURL(url);this.urls.delete(url);},1000);
  }
}
if(!customElements.get('ca-workflow-atlas'))customElements.define('ca-workflow-atlas',WorkflowAtlas);
