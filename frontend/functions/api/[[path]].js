const STRATEGY = {
  starting_bankroll_usd: 20,
  stake_fraction: 0.25,
  fixture_grouping_window_minutes: 120,
  max_active_accumulators: 1,
  settlement_required_before_next_entry: true,
  execution_mode: "paper",
  minimum_odds: null,
  minimum_confidence: null,
  rollover_target_odds: 4,
  rollover_equity_target_usd: 10000,
  rollover_settlement_mode: "sequential",
  paper_cycle_required_for_pilot_readiness: 1,
  live_execution_enabled: false
};

const RULES = [
  ["Premier League","England","Arsenal",["Liverpool","Manchester United","Manchester City","Brighton","Tottenham Hotspur","Aston Villa","Chelsea"]],
  ["La Liga","Spain","Barcelona",["Real Madrid","Real Betis","Atletico Madrid"]],
  ["La Liga","Spain","Real Madrid",["Barcelona","Real Betis","Atletico Madrid"]],
  ["Bundesliga","Germany","Bayern Munich",["Borussia Dortmund"]],
  ["Eredivisie","Netherlands","PSV",["Feyenoord"]],
  ["Ligue 1","France","Paris Saint-Germain",["Monaco","Marseille","Strasbourg"]],
  ["Primeira Liga","Portugal","Porto",["Sporting CP","Benfica"]],
  ["Primeira Liga","Portugal","Sporting CP",["Porto","Benfica"]],
  ["Serie A","Italy","Inter Milan",["AC Milan","Fiorentina","Como","Lazio","Roma","Napoli"]]
];
const COMPETITIONS = [
  ["PL","Premier League","England"],["PD","La Liga","Spain"],
  ["BL1","Bundesliga","Germany"],["DED","Eredivisie","Netherlands"],
  ["FL1","Ligue 1","France"],["PPL","Primeira Liga","Portugal"],
  ["SA","Serie A","Italy"]
];
const EXCLUDED = ["halftime","half-time","first half","first team to score","exact score","correct score","total goals","over/under","both teams to score","corner","cards","player","penalty"];

function json(data,status=200){return new Response(JSON.stringify(data),{status,headers:{"content-type":"application/json; charset=utf-8","cache-control":"no-store"}})}
function norm(s){return String(s||"").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/&/g,"and").replace(/[^a-z0-9]+/g," ").trim().replace(/^(fc|afc|sc) /,"").replace(/ (fc|cf|sc|afc)$/,"").replace(/\s+/g," ")}
function teamMatch(a,b){
 const x=norm(a),y=norm(b);
 const aliases={"manchester united":["man united"],"manchester city":["man city"],"paris saint germain":["psg"],"tottenham hotspur":["tottenham"],"inter milan":["internazionale","inter"],"bayern munich":["bayern munchen"],"bayern munchen":["bayern munich"]};
 return x===y || (aliases[x]||[]).includes(y) || (aliases[y]||[]).includes(x);
}
function allowedFixture(match,league,country){
 const home=match.homeTeam?.name,away=match.awayTeam?.name;
 if(!home||!away||!match.utcDate||!["SCHEDULED","TIMED"].includes(match.status))return false;
 const rule=RULES.find(r=>r[0]===league&&r[1]===country&&teamMatch(r[2],home));
 return !!rule && !rule[3].some(team=>teamMatch(team,away));
}
async function fetchFixtures(days,env){
 const token=env.FOOTBALL_DATA_API_TOKEN;
 if(!token)throw new Error("FOOTBALL_DATA_API_TOKEN is not configured in Cloudflare Pages settings.");
 const from=new Date(),to=new Date(from.getTime()+days*86400000);
 const dateFrom=from.toISOString().slice(0,10),dateTo=to.toISOString().slice(0,10);
 const all=[];
 for(const [code,league,country] of COMPETITIONS){
  const url=new URL("https://api.football-data.org/v4/competitions/"+code+"/matches");
  url.searchParams.set("dateFrom",dateFrom);url.searchParams.set("dateTo",dateTo);
  const response=await fetch(url,{headers:{"X-Auth-Token":token,"Accept":"application/json"}});
  if(!response.ok){
   if(response.status===403)continue;
   throw new Error("football-data.org returned HTTP "+response.status+" for "+league+". Check token and plan access.");
  }
  const body=await response.json();
  for(const m of body.matches||[])if(allowedFixture(m,league,country))all.push({
   kickoff:m.utcDate,country,league,home_team:m.homeTeam.name,away_team:m.awayTeam.name
  });
 }
 all.sort((a,b)=>Date.parse(a.kickoff)-Date.parse(b.kickoff));
 return {date_from:dateFrom,date_to:dateTo,fixtures:all};
}
function asArray(value){if(Array.isArray(value))return value;if(typeof value==="string"){try{return JSON.parse(value)}catch{}}return []}
function validMarket(fixture,event){
 for(const market of event.markets||[]){
  const question=String(market.question||"");
  if(EXCLUDED.some(term=>question.toLowerCase().includes(term))||market.active===false||market.closed===true)continue;
  const outcomes=asArray(market.outcomes).map(String),prices=asArray(market.outcomePrices).map(Number);
  if(outcomes.length!==3||prices.length!==3||prices.some(p=>!Number.isFinite(p)||p<=0||p>=1))continue;
  const hi=outcomes.map((x,i)=>teamMatch(x,fixture.home_team)?i:-1).filter(i=>i>=0);
  const ai=outcomes.map((x,i)=>teamMatch(x,fixture.away_team)?i:-1).filter(i=>i>=0);
  const di=outcomes.map((x,i)=>["draw","tie"].includes(norm(x))?i:-1).filter(i=>i>=0);
  if(hi.length!==1||ai.length!==1||di.length!==1)continue;
  const hp=prices[hi[0]],dp=prices[di[0]],ap=prices[ai[0]];
  return {market_id:market.id,condition_id:market.conditionId,question,market_type:"match_winner_1x2",
   home_win_price:hp,home_win_decimal_odds:Number((1/hp).toFixed(4)),
   liquidity_usd:Number(market.liquidityNum??market.liquidity)||null,volume_usd:Number(market.volumeNum??market.volume)||null,
   outcomes:{home:{name:outcomes[hi[0]],price:hp,decimal_odds:Number((1/hp).toFixed(4))},draw:{name:outcomes[di[0]],price:dp,decimal_odds:Number((1/dp).toFixed(4))},away:{name:outcomes[ai[0]],price:ap,decimal_odds:Number((1/ap).toFixed(4))}},
   data_quality:"validated_three_outcome_market"};
 }
 return null;
}
async function marketResearch(fixtures,limit){
 const matches=[];
 for(const fixture of fixtures){
  const url=new URL("https://gamma-api.polymarket.com/public-search");
  url.searchParams.set("q",fixture.home_team+" "+fixture.away_team);
  url.searchParams.set("events_status","active");url.searchParams.set("limit_per_type",String(limit));url.searchParams.set("search_tags","true");
  const response=await fetch(url,{headers:{Accept:"application/json"}});
  if(!response.ok)throw new Error("Polymarket Gamma returned HTTP "+response.status);
  const body=await response.json(),events=body.events||[];
  const matching=events.filter(e=>teamMatch(e.title||e.slug,fixture.home_team)&&teamMatch(e.title||e.slug,fixture.away_team));
  let selected=null,eventMatch=null;
  for(const event of matching){selected=validMarket(fixture,event);if(selected){eventMatch=event;break}}
  matches.push({...fixture,market_match_status:matching.length?"matched":"unmatched",
   polymarket_events:matching.map(e=>({event_id:e.id,event_title:e.title,event_slug:e.slug,event_url:e.slug?"https://polymarket.com/event/"+e.slug:null})),
   market_status:selected?"validated":"no_valid_match_winner_market",selected_market:selected});
 }
 return matches;
}
async function ensureDb(db){
 await db.exec(`CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY CHECK(id=1), equity REAL NOT NULL, stake_fraction REAL NOT NULL, target_odds REAL NOT NULL, equity_target REAL NOT NULL, status TEXT NOT NULL, pilot_ready INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS cycles (id INTEGER PRIMARY KEY AUTOINCREMENT, starting_equity REAL NOT NULL, reserve REAL NOT NULL, initial_stake REAL NOT NULL, current_rollover_stake REAL NOT NULL, cumulative_odds REAL NOT NULL DEFAULT 1, status TEXT NOT NULL, started_at TEXT NOT NULL, settled_at TEXT);
 CREATE TABLE IF NOT EXISTS legs (id INTEGER PRIMARY KEY AUTOINCREMENT, cycle_id INTEGER NOT NULL, fixture TEXT NOT NULL, selection TEXT NOT NULL, decimal_odds REAL NOT NULL, result TEXT NOT NULL, settled_at TEXT NOT NULL);`);
 const row=await db.prepare("SELECT id FROM account WHERE id=1").first();
 if(!row){
  const now=new Date().toISOString(),stake=20*.25;
  await db.prepare("INSERT INTO account(id,equity,stake_fraction,target_odds,equity_target,status,pilot_ready,created_at,updated_at) VALUES(1,20,.25,4,10000,'paper',0,?,?)").bind(now,now).run();
  await db.prepare("INSERT INTO cycles(starting_equity,reserve,initial_stake,current_rollover_stake,cumulative_odds,status,started_at) VALUES(?,?,?,?,1,'active',?)").bind(20,15,stake,stake,now).run();
 }
}
async function rolloverState(db){
 await ensureDb(db);
 const account=await db.prepare("SELECT * FROM account WHERE id=1").first();
 const cycle=await db.prepare("SELECT * FROM cycles WHERE status='active' ORDER BY id DESC LIMIT 1").first();
 const latest=await db.prepare("SELECT * FROM cycles ORDER BY id DESC LIMIT 1").first();
 const completed=await db.prepare("SELECT * FROM cycles WHERE status IN ('won','lost') ORDER BY id DESC LIMIT 1").first();
 const current=cycle||latest;
 const legs=current?await db.prepare("SELECT fixture,selection,decimal_odds,result,settled_at FROM legs WHERE cycle_id=? ORDER BY id").bind(current.id).all():{results:[]};
 const stake=Number((account.equity*account.stake_fraction).toFixed(2));
 return {equity_usd:Number(account.equity.toFixed(2)),stake_fraction:account.stake_fraction,next_cycle_stake_usd:stake,reserve_usd:Number((account.equity-stake).toFixed(2)),target_odds:account.target_odds,equity_target_usd:account.equity_target,account_status:account.status,pilot_ready:!!account.pilot_ready,cycle:current,last_completed_cycle:completed,legs:legs.results||[],execution_mode:"paper",orders_placed:0};
}
async function settle(db,payload){
 await ensureDb(db);
 const {fixture,selection}=payload;
 const result=payload.result,odds=Number(payload.decimal_odds);
 if(typeof fixture!=="string"||!fixture.trim()||typeof selection!=="string"||!selection.trim())throw new Error("Fixture and selection are required.");
 if(!["won","lost","void"].includes(result))throw new Error("Result must be won, lost, or void.");
 if(result!=="void"&&(!Number.isFinite(odds)||odds<1.01||odds>1000))throw new Error("Decimal odds must be between 1.01 and 1000.");
 const account=await db.prepare("SELECT * FROM account WHERE id=1").first();
 if(account.status!=="paper")throw new Error("Paper rollover is paused.");
 const cycle=await db.prepare("SELECT * FROM cycles WHERE status='active' ORDER BY id DESC LIMIT 1").first();
 if(!cycle)throw new Error("No active rollover cycle.");
 const now=new Date().toISOString(),legOdds=result==="void"?1:odds;
 await db.prepare("INSERT INTO legs(cycle_id,fixture,selection,decimal_odds,result,settled_at) VALUES(?,?,?,?,?,?)").bind(cycle.id,fixture.trim(),selection.trim(),legOdds,result,now).run();
 let event="leg_recorded";
 if(result==="lost"){
  const equity=Math.max(0,Number((account.equity-cycle.initial_stake).toFixed(2)));
  await db.prepare("UPDATE cycles SET status='lost',settled_at=? WHERE id=?").bind(now,cycle.id).run();
  await db.prepare("UPDATE account SET equity=?,status=?,updated_at=? WHERE id=1").bind(equity,equity<=0?"paused":"paper",now).run();
  if(equity>0){const stake=Number((equity*account.stake_fraction).toFixed(2));await db.prepare("INSERT INTO cycles(starting_equity,reserve,initial_stake,current_rollover_stake,cumulative_odds,status,started_at) VALUES(?,?,?,?,1,'active',?)").bind(equity,Number((equity-stake).toFixed(2)),stake,stake,now).run()}
  event="cycle_lost";
 }else if(result==="won"){
  const cumulative=cycle.cumulative_odds*odds,exposure=cycle.current_rollover_stake*odds;
  if(cumulative+1e-9>=account.target_odds){
   const equity=Number((cycle.reserve+exposure).toFixed(2)),status=equity>=account.equity_target?"paused":"paper";
   await db.prepare("UPDATE cycles SET cumulative_odds=?,current_rollover_stake=?,status='won',settled_at=? WHERE id=?").bind(cumulative,exposure,now,cycle.id).run();
   await db.prepare("UPDATE account SET equity=?,pilot_ready=1,status=?,updated_at=? WHERE id=1").bind(equity,status,now).run();
   if(status==="paper"){const stake=Number((equity*account.stake_fraction).toFixed(2));await db.prepare("INSERT INTO cycles(starting_equity,reserve,initial_stake,current_rollover_stake,cumulative_odds,status,started_at) VALUES(?,?,?,?,1,'active',?)").bind(equity,Number((equity-stake).toFixed(2)),stake,stake,now).run()}
   event="target_hit";
  }else await db.prepare("UPDATE cycles SET cumulative_odds=?,current_rollover_stake=? WHERE id=?").bind(cumulative,exposure,cycle.id).run();
 }
 return {...await rolloverState(db),last_event:event};
}
export async function onRequest({request,env,params}){
 const path="/api/"+(params.path||"");
 try{
  if(request.method==="GET"&&path==="/api/health")return json({status:"ok",service:"polyedge-cloudflare-api"});
  if(request.method==="GET"&&path==="/api/v1/config")return json({version:"1.0",competition_scope:"domestic_league_only",venue_scope:"selected_team_home_only",selected_teams:RULES.map(r=>({league:r[0],country:r[1],team:r[2],excluded_opponents:r[3]}))});
  if(request.method==="GET"&&path==="/api/v1/strategy")return json(STRATEGY);
  if(request.method==="GET"&&path==="/api/v1/rollover")return json(await rolloverState(env.POLYEDGE_DB));
  if(request.method==="POST"&&path==="/api/v1/rollover/settle")return json(await settle(env.POLYEDGE_DB,await request.json()));
  if(request.method==="GET"&&path==="/api/v1/polymarket/football-markets"){
   const url=new URL(request.url),days=Number(url.searchParams.get("days")||14),limit=Number(url.searchParams.get("limit")||5);
   if(!Number.isInteger(days)||days<1||days>14||!Number.isInteger(limit)||limit<1||limit>20)return json({detail:"days must be 1–14 and limit must be 1–20"},422);
   const scan=await fetchFixtures(days,env),matches=await marketResearch(scan.fixtures,limit);
   const analyses=matches.map(f=>({kickoff:f.kickoff,league:f.league,home_team:f.home_team,away_team:f.away_team,market_status:f.market_status,selected_market:f.selected_market}));
   const valid=analyses.filter(f=>f.selected_market),odds=valid.reduce((n,f)=>n*f.selected_market.home_win_decimal_odds,1);
   const state=await rolloverState(env.POLYEDGE_DB),qualifies=valid.length>0;
   const accumulator={status:qualifies?"proposed_paper_accumulator":"not_proposed",execution_mode:"paper",legs:qualifies?valid.map(f=>({fixture:f.home_team+" vs "+f.away_team,kickoff:f.kickoff,selection:f.home_team+" to win",market_question:f.selected_market.question,yes_price:f.selected_market.home_win_price,decimal_odds:f.selected_market.home_win_decimal_odds,condition_id:f.selected_market.condition_id})):[],leg_count:qualifies?valid.length:0,combined_decimal_odds:qualifies?Number(odds.toFixed(4)):null,stake_usd:qualifies?state.next_cycle_stake_usd:0,potential_return_usd:qualifies?Number((state.next_cycle_stake_usd*odds).toFixed(2)):null,potential_profit_usd:qualifies?Number((state.next_cycle_stake_usd*(odds-1)).toFixed(2)):null,reason:qualifies?"All included legs have a validated three-outcome match-winner market.":"No qualifying match-winner legs were validated.",orders_placed:0};
   return json({provider:"Polymarket Gamma public-search",authentication:"none_public_market_data",date_from:scan.date_from,date_to:scan.date_to,fixtures_checked:scan.fixtures.length,events_scanned:matches.reduce((n,f)=>n+(f.polymarket_events||[]).length,0),matched_fixtures:matches.filter(f=>f.market_match_status==="matched").length,unmatched_fixtures:matches.filter(f=>f.market_match_status==="unmatched").length,matches,market_intelligence:{provider:"Polymarket Gamma public market data",fixtures_analysed:analyses.length,validated_match_winner_markets:valid.length,rejected_or_missing_markets:analyses.length-valid.length,fixtures:analyses,paper_accumulator:accumulator,execution_mode:"paper",orders_placed:0},execution_mode:"paper",orders_placed:0});
  }
  if(request.method==="GET"&&path==="/api/v1/fixtures/live"){
   const url=new URL(request.url),days=Number(url.searchParams.get("days")||7);
   if(!Number.isInteger(days)||days<1||days>14)return json({detail:"days must be between 1 and 14"},422);
   const scan=await fetchFixtures(days,env);
   return json({mode:"live_fixture_scan",provider:"football-data.org",...scan,total_fixtures:scan.fixtures.length,qualifying_fixtures:scan.fixtures.length,skipped_fixtures:0,eligible:scan.fixtures,skipped:[],accumulator_groups:[],execution_mode:"paper",note:"Live fixture data only; no orders are placed."});
  }
  return json({detail:"API route not found",path},404);
 }catch(error){return json({detail:error?.message||"Unexpected API error"},500)}
}
