/* Suspend only this retained canvas iframe's animation work between tabs. */
export function createAnimationGate(request,cancel) {
  let active=true,next=0;
  const pending=new Map();
  const schedule=(id,entry)=>{entry.native=request(time=>{pending.delete(id);entry.callback(time);});};
  return {
    request(callback){const id=++next,entry={callback,native:null};pending.set(id,entry);if(active)schedule(id,entry);return id;},
    cancel(id){const entry=pending.get(id);if(!entry)return;if(entry.native!==null)cancel(entry.native);pending.delete(id);},
    setActive(value){
      value=!!value;if(value===active)return;active=value;
      for(const [id,entry] of pending){if(active)schedule(id,entry);else if(entry.native!==null){cancel(entry.native);entry.native=null;}}
    }
  };
}
