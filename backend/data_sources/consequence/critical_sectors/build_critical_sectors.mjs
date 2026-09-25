import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const here=path.dirname(fileURLToPath(import.meta.url)), outDir=here, workDir=path.join(here,"work/critical-sectors");fs.mkdirSync(workDir,{recursive:true});
const retrieved="2026-09-25", population=6111200;
const weights={H:0.35,E:0.20,D:0.20,X:0.15,R:0.05,A:0.05};

const sources=[
 {id:"EMA-SES-C2",sector:"energy",agency:"EMA",title:"Singapore Energy Statistics, Energy Transformation",date:"2025 data as at Jun 2025",facts:"13,261 MW registered generation capacity in 1H 2025; natural gas 93.1% of fuel mix; solar PV 2.5%",url:"https://www.ema.gov.sg/resources/singapore-energy-statistics/chapter2",confidence:"A",limitation:"System totals; not component availability, fuel constraints or restoration"},
 {id:"EMA-SES-C4",sector:"energy",agency:"EMA",title:"Singapore Energy Statistics, Energy Balance",date:"2024",facts:"58 TWh consumption; industry 39.4%, commerce/services 40.2%, household 14.6%, transport 5.3%; 86.9% of gas supply used for power generation",url:"https://www.ema.gov.sg/resources/singapore-energy-statistics/chapter4",confidence:"A",limitation:"Annual aggregate; no customer-to-component mapping"},
 {id:"EMA-ASR-2425",sector:"energy",agency:"EMA",title:"Annual and Sustainability Report 2024/25",date:"FY2024/25",facts:"2025 electricity consumption 57,936 GWh; generation 59,616 GWh; peak demand 8,045 MW; SAIDI 0.26 min; SAIFI 0.006",url:"https://www.ema.gov.sg/content/dam/corporate/resources/corporate-publications/annual-reports/pdf-files/EMA-Annual-Sustainability-Report-2024-2025.pdf",confidence:"A",limitation:"Reliability history does not establish scenario restoration time"},
 {id:"SINGSTAT-POP-2025",sector:"all",agency:"SingStat",title:"Population Trends 2025",date:"end-Jun 2025",facts:"Total population 6,111,200; residents 4,204,500; non-residents 1,906,700",url:"https://www.singstat.gov.sg/-/media/files/publications/population/population2025.ashx",confidence:"A",limitation:"Population is not equal to affected beneficiaries for every service component"},
 {id:"PUB-ASR-2425",sector:"water",agency:"PUB",title:"Annual and Sustainability Report 2024/25",date:"2024",facts:"100% population served; domestic potable water 303.9m m3; non-domestic 213.7m m3; NEWater 148.3m m3; distribution loss 7.1%",url:"https://www.pub.gov.sg/-/media/PUB/Publications/Report/PDF/PUB_ASR_2025.pdf",confidence:"A",limitation:"System totals; no asset service areas, redundancy or restoration"},
 {id:"PUB-WATER-LOOP",sector:"water",agency:"PUB",title:"Singapore Water Loop",date:"current public page",facts:"About 440 million gallons/day demand; demand could almost double by 2065; integrated collect/reuse/desalinate system",url:"https://www.pub.gov.sg/Public/WaterLoop",confidence:"A",limitation:"Public overview; no component-level allocation"},
 {id:"PUB-FOUR-TAPS",sector:"water",agency:"PUB",title:"Our Water Story",date:"current public page",facts:"Four National Taps: local catchment, imported water, NEWater and desalinated water",url:"https://www.pub.gov.sg/Public/WaterLoop/OurWaterStory",confidence:"A",limitation:"Diversification is known; available substitute capacity is not"},
 {id:"DGS-PUB-SENSORS",sector:"water",agency:"PUB/data.gov.sg",title:"PUB Water Level Sensors",date:"updated 13 Apr 2026",facts:"Public inventory of drain water-level sensor locations",url:"https://data.gov.sg/datasets/d_31333fa5cf0834f012d840365b336610/view",confidence:"A",limitation:"Sensor inventory does not identify criticality, drainage capacity or dependencies"},
 {id:"CAG-TRAFFIC",sector:"aviation",agency:"Changi Airport Group",title:"Traffic Statistics",date:"2025 full year",facts:"69.98m passenger movements; 2.08m tonnes air freight; 374,000 commercial aircraft movements",url:"https://www.changiairport.com/en/corporate/about-us/traffic-statistics.html",confidence:"A",limitation:"Monthly system flows; not simultaneous terminal occupancy or recovery"},
 {id:"CAAS-AR-2425",sector:"aviation",agency:"CAAS",title:"Annual Report 2024/25",date:"FY2024/25",facts:"Around 100 airlines and about 170 city links as at 31 Mar 2025",url:"https://www.caas.gov.sg/docs/default-source/default-document-library/caas_ar_fy24-25-desktop.pdf",confidence:"A",limitation:"Connectivity totals do not provide component continuity or authorised capability"},
 {id:"CAAS-ATFM",sector:"aviation",agency:"CAAS",title:"Singapore AIP ENR 1.9 Air Traffic Flow Management",date:"valid 27 Nov 2025",facts:"ATFM unit operates 24 hours and balances demand and capacity",url:"https://aim-sg.caas.gov.sg/aim-content/uploads/aip/27-NOV-2025/AIP-2/2025-11-27-000000/html/eAIP/SG-ENR-1.9-en-GB.html",confidence:"A",limitation:"No public operational capacity, redundancy or disruption consequence values"},
 {id:"MPA-PERF-2025",sector:"port",agency:"MPA",title:"Singapore Port Performance 2025",date:"2025",facts:"3.22bn GT vessel arrivals; 44.66m TEU container throughput; 56.77m tonnes bunker sales",url:"https://www.mpa.gov.sg/media-centre/details/singapore-posts-record-port-performance-in-2025-and-develops-future-readiness-through-industry-collaborations-for-2026",confidence:"A",limitation:"Annual port aggregate; no terminal allocation, crew occupancy or recovery"},
 {id:"MPA-PORT-STATS",sector:"port",agency:"MPA",title:"Port Statistics",date:"current public statistics",facts:"Cargo, container, bunker, vessel arrival and vessel-call series",url:"https://www.mpa.gov.sg/who-we-are/newsroom-resources/research-and-statistics/port-statistics",confidence:"A",limitation:"Throughput is not a direct count of affected people or component loss"},
 {id:"MPA-OCEANS-X",sector:"port",agency:"MPA",title:"OCEANS-X Maritime Data Catalogue",date:"current",facts:"Static and dynamic vessel, cargo, port-clearance and weather datasets",url:"https://oceans-x.mpa.gov.sg/",confidence:"B",limitation:"Registration/API access may be required; operational fields require governance review"},
];

const profiles=[
 {id:"ENE-ELEC",sector:"energy",name:"Singapore electricity system",unit:"people served",beneficiaries:population,flow:8045,flow_unit:"MW peak demand",h:null,h_method:"Onsite workforce unavailable publicly",v:35,e_role:"electricity supply",r_base:50,public_basis:"EMA system demand, generation, capacity and reliability"},
 {id:"ENE-GAS",sector:"energy",name:"National natural-gas supply aggregate",unit:"people/service users",beneficiaries:population,flow:453040,flow_unit:"TJ annual supply (2024)",h:null,h_method:"Onsite workforce unavailable publicly",v:35,e_role:"generation fuel and direct gas supply",r_base:60,public_basis:"EMA natural-gas balance; component details withheld"},
 {id:"ENE-SOLAR",sector:"energy",name:"Distributed solar generation aggregate",unit:"system beneficiaries",beneficiaries:population,flow:1367,flow_unit:"MWac capacity (1H 2025)",h:null,h_method:"Distributed sites; no unified onsite occupancy",v:20,e_role:"distributed generation contribution",r_base:30,public_basis:"EMA technology capacity aggregate"},
 {id:"WAT-POT",sector:"water",name:"National potable-water supply system",unit:"people served",beneficiaries:population,flow:517.6,flow_unit:"million m3 sold (2024)",h:null,h_method:"Onsite workforce unavailable publicly",v:50,e_role:"potable water",r_base:60,public_basis:"PUB 100% service and potable-water sales"},
 {id:"WAT-NEW",sector:"water",name:"NEWater supply aggregate",unit:"industrial/system users",beneficiaries:population*0.6,flow:148.3,flow_unit:"million m3 sold (2024)",h:null,h_method:"Onsite workforce unavailable publicly",v:40,e_role:"recycled high-grade water",r_base:55,public_basis:"PUB NEWater sales; beneficiary count is broad proxy"},
 {id:"WAT-USED",sector:"water",name:"Used-water and sanitation system",unit:"people served",beneficiaries:population,flow:population,flow_unit:"population service proxy",h:null,h_method:"Onsite workforce unavailable publicly",v:55,e_role:"sanitation and used-water conveyance",r_base:65,public_basis:"PUB reports 100% population served by modern sanitation"},
 {id:"WAT-DRAIN",sector:"water",name:"Stormwater and drainage monitoring system",unit:"population exposure proxy",beneficiaries:population,flow:null,flow_unit:"sensor network; count retained in source dataset",h:null,h_method:"Distributed outdoor workforce/road users not quantified",v:35,e_role:"flood monitoring and drainage",r_base:45,public_basis:"PUB water-level sensor inventory and flood-resilience reporting"},
 {id:"AVI-PAX",sector:"aviation",name:"Changi passenger airport system",unit:"passenger movements",beneficiaries:69980000/365,flow:69980000,flow_unit:"annual passenger movements (2025)",h:24000,h_method:"Annual passengers / 365 x assumed 3-hour dwell / 24; low/high vary by 0.6/1.5",v:35,e_role:"passenger connectivity",r_base:55,public_basis:"CAG passenger movements; dwell time is explicit assumption"},
 {id:"AVI-CARGO",sector:"aviation",name:"Changi air-freight system",unit:"tonnes/day",beneficiaries:2080000/365,flow:2080000,flow_unit:"annual tonnes (2025)",h:null,h_method:"Cargo workforce unavailable publicly",v:25,e_role:"air cargo and supply-chain connectivity",r_base:55,public_basis:"CAG air-freight movements"},
 {id:"AVI-ATM",sector:"aviation",name:"Singapore civil air-navigation service",unit:"aircraft movements/day",beneficiaries:374000/365,flow:374000,flow_unit:"annual commercial aircraft movements (2025)",h:null,h_method:"Controller/workforce count unavailable publicly",v:35,e_role:"civil air traffic management",r_base:60,public_basis:"CAG movements and CAAS 24-hour ATFM role"},
 {id:"PORT-CONT",sector:"port",name:"Singapore container-port system",unit:"TEU/day",beneficiaries:44.66e6/365,flow:44.66e6,flow_unit:"annual TEU (2025)",h:null,h_method:"Terminal workforce/crew occupancy unavailable publicly",v:25,e_role:"container logistics",r_base:60,public_basis:"MPA annual container throughput"},
 {id:"PORT-VES",sector:"port",name:"Singapore vessel-arrival and marine-services system",unit:"gross tonnes/day",beneficiaries:3.22e9/365,flow:3.22e9,flow_unit:"annual vessel-arrival GT (2025)",h:null,h_method:"Crew and shore workforce unavailable publicly",v:30,e_role:"vessel traffic and marine services",r_base:55,public_basis:"MPA vessel-arrival tonnage"},
 {id:"PORT-BUNK",sector:"port",name:"Singapore marine-fuel supply aggregate",unit:"tonnes/day",beneficiaries:56.77e6/365,flow:56.77e6,flow_unit:"annual bunker sales tonnes (2025)",h:null,h_method:"Workforce/crew occupancy unavailable publicly",v:25,e_role:"marine fuel supply",r_base:65,public_basis:"MPA annual bunker sales; inventory quantities/locations excluded"},
];

const scenarios=[
 {id:"BASE",label:"Normal baseline",loss:0,hours:0,alt:1,recovery:2,peak:1,notes:"Reference operating state"},
 {id:"PEAK",label:"Peak demand or throughput",loss:0,hours:0,alt:1,recovery:2,peak:1.25,notes:"High demand/throughput without service loss"},
 {id:"PARTIAL_2H",label:"Partial disruption, 2 hours",loss:0.25,hours:2,alt:0.35,recovery:12,peak:1,notes:"Research scenario; not a forecast"},
 {id:"MAJOR_12H",label:"Major disruption, 12 hours",loss:0.60,hours:12,alt:0.20,recovery:48,peak:1,notes:"Research scenario; not a forecast"},
 {id:"SEVERE_72H",label:"Severe disruption, 72 hours",loss:0.85,hours:72,alt:0.10,recovery:336,peak:1,notes:"Stress scenario; not a forecast"},
 {id:"SUBSTITUTE",label:"Disruption with strong substitution",loss:0.50,hours:12,alt:0.70,recovery:48,peak:1,notes:"Tests effect of alternatives; capacity is assumed"},
 {id:"PEAK_PARTIAL",label:"Peak-state partial disruption",loss:0.35,hours:6,alt:0.25,recovery:48,peak:1.25,notes:"Combined demand and disruption stress"},
 {id:"RECOVERY",label:"Recovery-constrained case",loss:0.50,hours:24,alt:0.20,recovery:2160,peak:1,notes:"90-day time-to-90% assumption"},
];

function bandScore(x){if(x<=0)return 0;if(x<1e3)return 10;if(x<1e4)return 25;if(x<1e5)return 40;if(x<1e6)return 60;if(x<1e7)return 80;return 100;}
function recoveryScore(h){if(h<6)return 5;if(h<=24)return 15;if(h<=72)return 30;if(h<=336)return 50;if(h<=2160)return 75;return 100;}
function occScore(n){return Math.min(100,20*Math.log10(n+1));}
function hScore(n,v){return Math.round(10*occScore(n)*(0.6+0.4*v/100))/10;}
function clamp(x){return Math.max(0,Math.min(100,x));}
function esc(x){const s=x==null?"":String(x);return /[",\n]/.test(s)?`"${s.replaceAll('"','""')}"`:s;}
function csv(headers,rows){return [headers.join(","),...rows.map(r=>headers.map(h=>esc(r[h])).join(","))].join("\n");}

const rows=[];
for(const p of profiles)for(const s of scenarios){
 const people=p.h==null?null:Math.round(p.h*s.peak), hl=people==null?null:Math.round(people*0.6), hh=people==null?null:Math.round(people*1.5);
 const effective=p.beneficiaries*s.loss*s.hours*(1-s.alt); const ec=bandScore(effective), el=bandScore(effective*0.6), eh=bandScore(effective*1.5);
 const rc=recoveryScore(s.recovery), rl=recoveryScore(Math.max(1,s.recovery*0.6)), rh=recoveryScore(s.recovery*1.5);
 rows.push({profile_id:p.id,sector:p.sector,profile_name:p.name,scenario_id:s.id,scenario_label:s.label,
  people_low:hl??"",people_central:people??"",people_high:hh??"",people_state:people==null?"unavailable":"derived",people_method:p.h_method,
  beneficiaries:p.beneficiaries,loss_fraction:s.loss,outage_hours:s.hours,alternative_capacity_fraction:s.alt,effective_service_person_hours:Math.round(effective),service_unit:p.unit,
  H_low:hl==null?"":hScore(hl,p.v),H_central:people==null?"":hScore(people,p.v),H_high:hh==null?"":hScore(hh,p.v),H_state:people==null?"unavailable":"derived",H_confidence:people==null?"E":"D",
  E_low:el,E_central:ec,E_high:eh,E_state:"derived_scenario",E_confidence:p.unit==="people served"?"C":"D",
  D_low:"",D_central:"",D_high:"",D_state:"unavailable",D_confidence:"E",
  X_low:"",X_central:"",X_high:"",X_state:"unavailable",X_confidence:"E",
  R_low:rl,R_central:rc,R_high:rh,R_state:"assumption",R_confidence:"D",
  A_low:"",A_central:"",A_high:"",A_state:"unavailable",A_confidence:"E",
  policy_total_score:"",policy_total_status:"unavailable: incomplete vector",numeric_dimensions:(people==null?2:3),vector_numeric_coverage:(people==null?2:3)/6,
  scenario_notes:s.notes,public_basis:p.public_basis,score_status:"Full vector contract present; null is unavailable, not zero"});
}

const profileRows=profiles.map(p=>({...p,beneficiaries:Math.round(p.beneficiaries),h:p.h??"",D_requirement:"authorised input",X_requirement:"verified dependency edges",A_requirement:"operator inventory bands",location_resolution:"system aggregate only"}));
fs.mkdirSync(outDir,{recursive:true});fs.mkdirSync(workDir,{recursive:true});
const ph=Object.keys(profileRows[0]), rh=Object.keys(rows[0]), sh=Object.keys(sources[0]);
fs.writeFileSync(path.join(outDir,"critical-sectors-profiles.csv"),csv(ph,profileRows));
fs.writeFileSync(path.join(outDir,"critical-sectors-scenarios.csv"),csv(rh,rows));
fs.writeFileSync(path.join(outDir,"critical-sectors-sources.csv"),csv(sh,sources));
fs.writeFileSync(path.join(outDir,"critical-sectors-metadata.json"),JSON.stringify({title:"Singapore energy, water, aviation and port public evidence",retrieved,profiles:profiles.length,scenario_rows:rows.length,vector:["H","E","D","X","R","A"],weights,population_basis:population,warning:"System-level public evidence only. Do not allocate national totals to specific facilities. Null values are unavailable, not zero. Policy totals remain null until required evidence is supplied."},null,2));

const wb=Workbook.create(); const read=wb.worksheets.add("Read Me"), prof=wb.worksheets.add("Profiles"), scen=wb.worksheets.add("Scenario Vectors"), model=wb.worksheets.add("Scoring Model"), src=wb.worksheets.add("Source Log"), gaps=wb.worksheets.add("Data Gaps");
function col(n){let s="";while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26)}return s;}
function title(ws,t,sub,last){ws.mergeCells(`A2:${last}2`);ws.getRange("A2").values=[[t]];ws.getRange("A2").format={font:{bold:true,size:16,color:"#183B56"}};ws.mergeCells(`A3:${last}3`);ws.getRange("A3").values=[[sub]];ws.getRange("A3").format={font:{italic:true,color:"#526477"}};}
function table(ws,start,h,data,name){ws.getRange(`A${start}:${col(h.length)}${start}`).values=[h];if(data.length)ws.getRange(`A${start+1}:${col(h.length)}${start+data.length}`).values=data;const t=ws.tables.add(`A${start}:${col(h.length)}${start+data.length}`,true,name);t.style="TableStyleMedium2";ws.freezePanes.freezeRows(start);return t;}
title(read,"Critical-sector public evidence","Energy, water, aviation and port system profiles with complete H/E/D/X/R/A schema","J");
read.getRange("A6:B15").values=[["Metric","Value"],["Profiles",profiles.length],["Scenario rows",rows.length],["Scenarios/profile",scenarios.length],["Official sources",sources.length],["Population basis",population],["Vector","H, E, D, X, R, A"],["Complete policy totals",0],["Geographic resolution","System aggregate"],["Retrieved",retrieved]];read.getRange("A6:B6").format={fill:"#183B56",font:{bold:true,color:"#FFFFFF"}};
read.getRange("A18:A23").values=[["Rules"],["1. Do not allocate national totals equally to facilities or invent component locations."],["2. H is unavailable except where public passenger flow supports a broad occupancy estimate."],["3. E is scenario-derived from beneficiaries, loss, duration and assumed alternative capacity."],["4. D, X and A remain null until authorised/operator evidence exists."],["5. R is an explicit recovery-time assumption; replace it with time to 30/60/90% function."]];for(let r=18;r<=23;r++)read.mergeCells(`A${r}:J${r}`);read.getRange("A18:J18").format={fill:"#147D80",font:{bold:true,color:"#FFFFFF"}};read.getRange("A:J").format.columnWidth=20;
title(prof,"System profiles","Public aggregate identities and raw evidence; no sensitive component reconstruction",col(ph.length));table(prof,6,ph,profileRows.map(x=>ph.map(h=>x[h])),"Profiles");for(let i=0;i<ph.length;i++)prof.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=["public_basis","h_method"].includes(ph[i])?52:22;prof.getRange(`A7:${col(ph.length)}${6+profileRows.length}`).format.rowHeight=42;
title(scen,"Scenario vectors","All scenarios carry H/E/D/X/R/A low-central-high values, states and confidence",col(rh.length));table(scen,6,rh,rows.map(x=>rh.map(h=>x[h])),"Vectors");for(let i=0;i<rh.length;i++)scen.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=["people_method","scenario_notes","public_basis","score_status","policy_total_status"].includes(rh[i])?46:15;scen.getRange(`A7:${col(rh.length)}${6+rows.length}`).format.rowHeight=38;
title(model,"Scoring model","Policy weights are recorded separately from evidence; no incomplete total is emitted","F");const wr=Object.entries(weights).map(([k,v])=>[k,v,k==="H"?"Human exposure":k==="E"?"Essential civilian service":k==="D"?"Authorised capability":k==="X"?"Cascading consequence":k==="R"?"Functional recovery":"Additional hazard",["D","X","A"].includes(k)?"Unavailable publicly":"Available or assumption by profile"]);table(model,6,["Factor","Weight","Meaning","Current status"],wr,"Weights");model.getRange("B7:B12").format.numberFormat="0%";model.getRange("A15:B17").values=[["E input","beneficiaries × loss fraction × outage hours × (1-alternative capacity)"],["R input","time to 90% function mapped to published bands"],["Policy total","0.70×weighted + 0.30×MAX(H,E,D), only when required dimensions exist"]];model.getRange("A:F").format.columnWidth=30;
title(src,"Source log","Official public evidence and its limitations",col(sh.length));table(src,6,sh,sources.map(x=>sh.map(h=>x[h])),"Sources");for(let i=0;i<sh.length;i++)src.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=["facts","limitation"].includes(sh[i])?55:sh[i]==="url"?70:22;src.getRange(`A7:${col(sh.length)}${6+sources.length}`).format.rowHeight=55;
const gapRows=[
 ["Component/service area","Energy; water; aviation; port","Operator/agency","null","Do not allocate system totals to components"],
 ["Onsite people and shifts","All profiles except passenger aggregate","Operator","H unavailable","Do not infer from throughput"],
 ["Authorised capability D","Potentially aviation and other authorised systems","Authorised owner","D unavailable","Accept only approved abstract values"],
 ["Dependency edges X","All four sectors","Operators/agencies","X unavailable","Require beneficiary, loss, duration and alternative capacity"],
 ["Recovery to 30/60/90%","All four sectors","Operators/engineering","R assumption","Version distributions by scenario"],
 ["Hazard inventory A","Fuel, port, airport and selected water/energy assets","Operator/regulator","A unavailable","Use approved bands, not inferred quantities"],
 ["Alternative capacity","All four sectors","Operators/system planners","Scenario assumption","Sensitivity-test 0-100%"],
 ["Co-dependency and double count","Energy-water-transport links","Model owner","unresolved","Keep direct E separate from downstream X"],
];title(gaps,"Data gaps","Operator fields needed before component-level or complete-vector scoring","E");table(gaps,6,["Missing field","Affected profiles","Required provider","Current treatment","Rule"],gapRows,"Gaps");[34,40,28,24,60].forEach((w,i)=>gaps.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);gaps.getRange("A7:E20").format.rowHeight=52;
[read,prof,scen,model,src,gaps].forEach(x=>x.showGridlines=false);wb.recalculate();
const err=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!",options:{useRegex:true,maxResults:100},summary:"formula error scan"});
const previews={"Read Me":"A1:J24","Profiles":"A1:Q20","Scenario Vectors":"A1:AO20","Scoring Model":"A1:F18","Source Log":"A1:I20","Data Gaps":"A1:E16"};for(const [n,r] of Object.entries(previews)){const p=await wb.render({sheetName:n,range:r,scale:1,format:"png"});fs.writeFileSync(path.join(workDir,`${n.replaceAll(" ","-").toLowerCase()}.png`),new Uint8Array(await p.arrayBuffer()));}
const out=await SpreadsheetFile.exportXlsx(wb);await out.save(path.join(outDir,"singapore-critical-sectors-evidence.xlsx"));
console.log(JSON.stringify({profiles:profiles.length,scenarios:rows.length,sources:sources.length,errors:err.ndjson},null,2));
