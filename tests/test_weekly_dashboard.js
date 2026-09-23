const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');

test('a slow earlier source response cannot replace the newest selection',async()=>{
  const source=fs.readFileSync(path.join(__dirname,'../app/static/app.js'),'utf8');
  const requests=[];
  const renders=[];
  const context={AbortController,URL,
    document:{getElementById:()=>({})},window:{location:{origin:'http://localhost:8000'}},
    fetch:url=>new Promise(resolve=>requests.push({url,resolve})),
    renderWeeklyDashboard:()=>renders.push({
      selected:context.__test.state.selectedWeeklySource,
      shown:context.__test.state.weekly?.source?.id,
      loading:context.__test.state.weeklyLoading,
    }),
  };
  vm.runInNewContext(source.slice(0,source.indexOf('function showWeeklyDashboard()'))+
    '\nglobalThis.__test={state,loadWeeklyDashboard};',context);
  context.__test.state.weeklySources=[
    {id:'wylie',label:'Wylie'},{id:'wylie_isd',label:'Wylie ISD'},
  ];
  const old=context.__test.loadWeeklyDashboard('wylie');
  const current=context.__test.loadWeeklyDashboard('wylie_isd');
  assert.equal(requests.length,2);
  assert.equal(renders.at(-1).selected,'wylie_isd');
  assert.equal(renders.at(-1).shown,undefined);
  requests[1].resolve({ok:true,json:async()=>({source:{id:'wylie_isd'},categories:[]})});
  await current;
  requests[0].resolve({ok:true,json:async()=>({source:{id:'wylie'},categories:[]})});
  await old;
  assert.equal(context.__test.state.weekly.source.id,'wylie_isd');
  assert.equal(renders.at(-1).shown,'wylie_isd');
  assert.equal(renders.at(-1).loading,false);
});
