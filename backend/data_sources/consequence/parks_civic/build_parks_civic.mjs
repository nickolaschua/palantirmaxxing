import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const root = path.dirname(fileURLToPath(import.meta.url));
const rawDir = path.join(root, "..", "cache", "parks_civic");
const outDir = root;
fs.mkdirSync(path.join(root, "work/parks-civic"), { recursive: true });
const retrieved = "2026-09-25";

const sourceDefs = {
  parks: { id:"d_77d7ec97be83d44f61b85454f844382f", title:"NParks Parks and Nature Reserves", agency:"NParks", url:"https://data.gov.sg/datasets/d_77d7ec97be83d44f61b85454f844382f/view", published:"Snapshot", confidence:"A" },
  parkFacilities: { id:"d_14d807e20158338fd578c2913953516e", title:"Park Facilities", agency:"NParks", url:"https://data.gov.sg/datasets/d_14d807e20158338fd578c2913953516e/view", published:"Snapshot", confidence:"A" },
  sports: { id:"d_2cfb0867cdeb2b7303068995699dc33b", title:"Sport Facilities National Census 2024", agency:"SportSG", url:"https://data.gov.sg/datasets/d_2cfb0867cdeb2b7303068995699dc33b/view", published:"2024 census", confidence:"A" },
  communitySites: { id:"d_1f35a697b1a83fc771fa528cf76bcea4", title:"Community Use Sites", agency:"SLA", url:"https://data.gov.sg/collections/1589/datasets/d_1f35a697b1a83fc771fa528cf76bcea4/view", published:"Snapshot", confidence:"B" },
  clubs: { id:"d_f706de1427279e61fe41e89e24d440fa", title:"Community Clubs", agency:"People's Association", url:"https://data.gov.sg/datasets/d_f706de1427279e61fe41e89e24d440fa/view", published:"2024", confidence:"A" },
  libraries: { id:"d_27b8dae65d9ca1539e14d09578b17cbf", title:"Libraries", agency:"NLB", url:"https://data.gov.sg/collections/1463/datasets/d_27b8dae65d9ca1539e14d09578b17cbf/view", published:"2024", confidence:"A" },
  theatres: { id:"d_39620e0a12a31733842dcb6759b51a85", title:"Theatre", agency:"NAC", url:"https://data.gov.sg/datasets/d_39620e0a12a31733842dcb6759b51a85/view", published:"Historical 2018-Feb 2022; released 2025", confidence:"B" },
  monuments: { id:"d_b29c230ec6b609e29ed42f71ca9a8767", title:"National Monuments", agency:"NHB", url:"https://data.gov.sg/datasets/d_b29c230ec6b609e29ed42f71ca9a8767/view", published:"2026 release; source geography Mar 2021", confidence:"A" },
};

const scenarios = [
  {id:"WD_AM", label:"Weekday morning", hours:"06:00-10:00", day:"weekday", state:"ordinary"},
  {id:"WD_DAY", label:"Weekday daytime", hours:"10:00-17:00", day:"weekday", state:"ordinary"},
  {id:"WD_PM", label:"Weekday evening", hours:"17:00-22:00", day:"weekday", state:"ordinary"},
  {id:"WD_NIGHT", label:"Weekday night", hours:"22:00-06:00", day:"weekday", state:"ordinary"},
  {id:"WE_DAY", label:"Weekend daytime", hours:"08:00-18:00", day:"weekend/public holiday", state:"ordinary"},
  {id:"WE_PM", label:"Weekend evening", hours:"18:00-22:00", day:"weekend/public holiday", state:"ordinary"},
  {id:"EVENT", label:"Scheduled major event", hours:"event-specific", day:"any", state:"event/surge"},
  {id:"CLOSED", label:"Closed or severe-weather state", hours:"any", day:"any", state:"closure/adverse weather"},
];

const weights = { occupancy:0.40, vulnerability:0.15, civicService:0.15, recoveryHeritage:0.15, concentration:0.10, accessEgress:0.05 };
const typeRules = {
  park:{vulnerability:25,civicService:10,recoveryHeritage:20,concentration:10,accessEgress:15, basis:"Area-based outdoor density plus mapped facility uplift"},
  nature_reserve:{vulnerability:25,civicService:15,recoveryHeritage:75,concentration:5,accessEgress:35,basis:"Area-based visitor density; ecological/heritage recovery is not monetary loss"},
  sport_venue:{vulnerability:30,civicService:15,recoveryHeritage:25,concentration:45,accessEgress:25,basis:"Facility-count venue prior; no site attendance published"},
  community_use_site:{vulnerability:25,civicService:20,recoveryHeritage:15,concentration:15,accessEgress:20,basis:"Open-site prior; event status dominates occupancy"},
  community_club:{vulnerability:45,civicService:55,recoveryHeritage:35,concentration:55,accessEgress:25,basis:"Community programme prior; site capacity unavailable"},
  library:{vulnerability:40,civicService:35,recoveryHeritage:45,concentration:55,accessEgress:25,basis:"Public-library prior; branch attendance/capacity unavailable"},
  theatre:{vulnerability:30,civicService:20,recoveryHeritage:55,concentration:80,accessEgress:45,basis:"Performance-venue prior; event schedule/capacity unavailable"},
  monument:{vulnerability:20,civicService:10,recoveryHeritage:90,concentration:20,accessEgress:20,basis:"Protected heritage asset; visitor counts generally unavailable"},
};

const occProfiles = {
  park:{WD_AM:[0.25,0.8,2],WD_DAY:[0.2,0.6,2],WD_PM:[0.4,1.5,4],WD_NIGHT:[0.02,0.1,0.4],WE_DAY:[0.6,2.5,8],WE_PM:[0.4,1.8,6],EVENT:[2,8,25],CLOSED:[0,0.03,0.2]},
  nature_reserve:{WD_AM:[0.05,0.2,0.7],WD_DAY:[0.08,0.3,1],WD_PM:[0.03,0.15,0.5],WD_NIGHT:[0,0.01,0.05],WE_DAY:[0.2,0.8,2.5],WE_PM:[0.03,0.15,0.6],EVENT:[0.5,2,6],CLOSED:[0,0.01,0.05]},
  sport_venue:{WD_AM:[10,35,120],WD_DAY:[10,50,180],WD_PM:[40,150,500],WD_NIGHT:[0,3,15],WE_DAY:[50,180,600],WE_PM:[30,120,450],EVENT:[150,500,1800],CLOSED:[0,2,10]},
  community_use_site:{WD_AM:[0,5,25],WD_DAY:[0,8,40],WD_PM:[3,20,100],WD_NIGHT:[0,1,8],WE_DAY:[5,30,150],WE_PM:[5,25,120],EVENT:[80,300,1200],CLOSED:[0,0,5]},
  community_club:{WD_AM:[15,60,180],WD_DAY:[30,120,350],WD_PM:[80,280,700],WD_NIGHT:[0,5,20],WE_DAY:[80,300,800],WE_PM:[60,220,650],EVENT:[250,700,1800],CLOSED:[0,3,15]},
  library:{WD_AM:[10,40,120],WD_DAY:[80,250,600],WD_PM:[60,200,500],WD_NIGHT:[0,2,10],WE_DAY:[120,350,800],WE_PM:[40,150,400],EVENT:[200,600,1200],CLOSED:[0,2,10]},
  theatre:{WD_AM:[0,10,50],WD_DAY:[5,30,150],WD_PM:[20,120,500],WD_NIGHT:[0,3,15],WE_DAY:[20,100,400],WE_PM:[50,250,900],EVENT:[300,800,2000],CLOSED:[0,2,10]},
  monument:{WD_AM:[0,5,25],WD_DAY:[5,30,150],WD_PM:[2,15,80],WD_NIGHT:[0,1,5],WE_DAY:[10,60,250],WE_PM:[2,15,80],EVENT:[80,300,1000],CLOSED:[0,1,5]},
};

function readGeo(id){ return JSON.parse(fs.readFileSync(path.join(rawDir, `${id}.geojson`), "utf8")); }
function csvParse(text){
  const rows=[]; let row=[],v="",q=false;
  for(let i=0;i<text.length;i++){ const c=text[i]; if(q){ if(c==='"'&&text[i+1]==='"'){v+='"';i++;} else if(c==='"')q=false; else v+=c; } else if(c==='"')q=true; else if(c===','){row.push(v);v="";} else if(c==='\n'){row.push(v.replace(/\r$/, ""));rows.push(row);row=[];v="";} else v+=c; }
  if(v||row.length){row.push(v);rows.push(row);} const h=rows.shift(); return rows.filter(r=>r.some(Boolean)).map(r=>Object.fromEntries(h.map((x,i)=>[x,r[i]??""])));
}
function htmlFields(html=""){
  const out={}; const re=/<th[^>]*>([^<]+)<\/th>\s*<td[^>]*>([\s\S]*?)<\/td>/gi; let m;
  while((m=re.exec(html))){out[m[1].trim()]=m[2].replace(/<[^>]+>/g," ").replace(/&amp;/g,"&").replace(/&#39;/g,"'").replace(/\s+/g," ").trim();}
  return out;
}
function coords(g){
  if(!g)return [null,null]; if(g.type==="Point")return [g.coordinates[1],g.coordinates[0]];
  const pts=[]; const walk=x=>{if(Array.isArray(x)&&typeof x[0]==="number")pts.push(x);else if(Array.isArray(x))x.forEach(walk)}; walk(g.coordinates);
  if(!pts.length)return [null,null]; return [pts.reduce((s,p)=>s+p[1],0)/pts.length,pts.reduce((s,p)=>s+p[0],0)/pts.length];
}
function pointInRing(pt,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const xi=ring[i][0],yi=ring[i][1],xj=ring[j][0],yj=ring[j][1];const hit=((yi>pt[1])!==(yj>pt[1]))&&(pt[0]<(xj-xi)*(pt[1]-yi)/(yj-yi+1e-15)+xi);if(hit)inside=!inside;}return inside;}
function inGeom(pt,g){if(!g)return false;if(g.type==="Polygon")return pointInRing(pt,g.coordinates[0]);if(g.type==="MultiPolygon")return g.coordinates.some(p=>pointInRing(pt,p[0]));return false;}
function clamp(x,a=0,b=100){return Math.max(a,Math.min(b,x));}
function occupancyScore(n){return Math.round(clamp(100*Math.log10(1+Math.max(0,n))/Math.log10(2001)));}
function csvEscape(x){const s=x==null?"":String(x);return /[",\n]/.test(s)?`"${s.replaceAll('"','""')}"`:s;}
function toCsv(headers, rows){return [headers.join(","),...rows.map(r=>headers.map(h=>csvEscape(r[h])).join(","))].join("\n");}
function id(prefix,i){return `${prefix}-${String(i+1).padStart(4,"0")}`;}

const facilities = readGeo(sourceDefs.parkFacilities.id).features;
const parkFeatures = readGeo(sourceDefs.parks.id).features;
const sites=[];
for(let i=0;i<parkFeatures.length;i++){
  const f=parkFeatures[i], p=f.properties, [lat,lon]=coords(f.geometry), area=Number(p["SHAPE_1.AREA"]||0), facilityCount=facilities.reduce((n,x)=>n+(x.geometry?.type==="Point"&&inGeom(x.geometry.coordinates,f.geometry)?1:0),0);
  const subtype=String(p.N_RESERVE)==="1"?"nature_reserve":"park";
  sites.push({site_id:id("PARK",i),name:p.NAME||`Unnamed park ${i+1}`,category:"green_recreation",subtype,latitude:lat,longitude:lon,postal_code:"",area_sqm:Math.round(area),facility_count:facilityCount,facility_types:"",source_id:sourceDefs.parks.id,source_native_id:p.L_CODE||p.OBJECTID_1||"",source_updated:p.FMEL_UPD_D||"",raw_evidence:"geometry; area; reserve flag; spatial count of NParks facility points",derivation:"Representative coordinate is mean of geometry vertices; facility points counted inside boundary",data_confidence:area>0?"A":"B"});
}

const sportRows=csvParse(fs.readFileSync(path.join(rawDir,`${sourceDefs.sports.id}.geojson`),"utf8"));
const sportGroups=new Map();
for(const r of sportRows){const k=[r.VenueName,r.PostalCode,r.Latitude,r.Longitude].join("|");if(!sportGroups.has(k))sportGroups.set(k,{...r,types:new Set()});sportGroups.get(k).types.add(r.SportsFacility);}
let seq=0;
for(const g of sportGroups.values())sites.push({site_id:id("SPORT",seq++),name:g.VenueName,category:"green_recreation",subtype:"sport_venue",latitude:Number(g.Latitude),longitude:Number(g.Longitude),postal_code:g.PostalCode,area_sqm:"",facility_count:g.types.size,facility_types:[...g.types].sort().join("; "),source_id:sourceDefs.sports.id,source_native_id:"",source_updated:"2024",raw_evidence:"venue; postcode; coordinates; facility types",derivation:"Deduplicated by venue/postcode/coordinate; repeated facility records collapsed",data_confidence:"A"});

function addSimple(key,prefix,subtype,extract){const def=sourceDefs[key], feats=readGeo(def.id).features;feats.forEach((f,i)=>{const e=extract(f), c=coords(f.geometry);sites.push({site_id:id(prefix,i),name:e.name||`${subtype} ${i+1}`,category:subtype==="community_use_site"?"green_recreation":"commercial_civic",subtype,latitude:e.lat??c[0],longitude:e.lon??c[1],postal_code:e.postal||"",area_sqm:e.area||"",facility_count:e.facility_count||"",facility_types:e.facility_types||"",source_id:def.id,source_native_id:e.native||"",source_updated:e.updated||"",raw_evidence:e.evidence||"source feature",derivation:e.derivation||"No transformation beyond field normalization",data_confidence:def.confidence});});}
addSimple("communitySites","CUS","community_use_site",f=>({name:f.properties.NAME,area:Math.round(Number(f.properties["SHAPE.AREA"]||0)),native:f.properties.OBJECTID,updated:f.properties.FMEL_UPD_D,evidence:"name; description; polygon; area"}));
addSimple("clubs","CC","community_club",f=>{const h=htmlFields(f.properties.Description);return {name:h.NAME||f.properties.Name,postal:h.ADDRESSPOSTALCODE,updated:h.FMEL_UPD_D,evidence:"name; address; postcode; public website; point geometry"};});
addSimple("libraries","LIB","library",f=>{const h=htmlFields(f.properties.Description);return {name:h.NAME||f.properties.Name,postal:h.ADDRESSPOSTALCODE,updated:h.FMEL_UPD_D,evidence:"name; address; postcode; public website; point geometry"};});
addSimple("theatres","THR","theatre",f=>({name:f.properties.VENUE_NAME,postal:f.properties.POSTALCODE,native:f.properties.OBJECTID,updated:f.properties.FMEL_UPD_D,evidence:"venue name; address; postcode; website; point geometry"}));
addSimple("monuments","MON","monument",f=>({name:f.properties.NAME,postal:f.properties.ADDRESSPOSTALCODE,native:f.properties.OBJECTID,updated:f.properties.FMEL_UPD_D,evidence:"national monument designation; address; public heritage link; point geometry"}));

const scenarioRows=[];
for(const s of sites){
  const rule=typeRules[s.subtype];
  for(const sc of scenarios){
    let [low,central,high]=occProfiles[s.subtype][sc.id]; let method=rule.basis;
    if(s.subtype==="park"||s.subtype==="nature_reserve"){
      const ha=Math.max(0.2,Number(s.area_sqm||0)/10000); const facilityUplift=1+Math.min(1.5,Number(s.facility_count||0)/40);
      low=Math.round(low*ha);central=Math.round(central*ha*facilityUplift);high=Math.round(high*ha*facilityUplift);method+=`; density x ${ha.toFixed(2)} ha x facility uplift ${facilityUplift.toFixed(2)}`;
    } else if(s.subtype==="sport_venue"){
      const mult=1+Math.min(2,Math.max(0,Number(s.facility_count||1)-1)*0.25);low=Math.round(low*mult);central=Math.round(central*mult);high=Math.round(high*mult);method+=`; facility-type multiplier ${mult.toFixed(2)}`;
    }
    const o=occupancyScore(central), composite=Math.round(10*(o*weights.occupancy+rule.vulnerability*weights.vulnerability+rule.civicService*weights.civicService+rule.recoveryHeritage*weights.recoveryHeritage+rule.concentration*weights.concentration+rule.accessEgress*weights.accessEgress))/10;
    scenarioRows.push({site_id:s.site_id,scenario_id:sc.id,scenario_label:sc.label,hours:sc.hours,day_type:sc.day,state:sc.state,occupancy_low:low,occupancy_central:central,occupancy_high:high,occupancy_score:o,vulnerability_score:rule.vulnerability,civic_service_score:rule.civicService,recovery_heritage_score:rule.recoveryHeritage,crowd_concentration_score:rule.concentration,access_egress_score:rule.accessEgress,composite_index:composite,occupancy_method:method,estimate_confidence:(s.subtype==="park"||s.subtype==="nature_reserve")?"C":"D",score_status:"Research prior; not observed site attendance or an operational recommendation"});
  }
}

fs.mkdirSync(outDir,{recursive:true});
const siteHeaders=Object.keys(sites[0]); const scenarioHeaders=Object.keys(scenarioRows[0]);
fs.writeFileSync(path.join(outDir,"parks-civic-sites.csv"),toCsv(siteHeaders,sites));
fs.writeFileSync(path.join(outDir,"parks-civic-scenarios.csv"),toCsv(scenarioHeaders,scenarioRows));
const metadata={title:"Singapore parks and civic venues consequence evidence starter dataset",retrieved,scope:"Civilian consequence data preparation only",site_count:sites.length,scenario_row_count:scenarioRows.length,scenarios,weights,warning:"Composite index is a transparent research baseline, not an interception, targeting, or operational recommendation. Preserve factors and uncertainty bands when reweighting.",sources:Object.values(sourceDefs)};
fs.writeFileSync(path.join(outDir,"parks-civic-metadata.json"),JSON.stringify(metadata,null,2));

const wb=Workbook.create();
const scenarioSample=scenarioRows.slice(0,2000);
const readme=wb.worksheets.add("Read Me"), siteSheet=wb.worksheets.add("Sites"), scenSheet=wb.worksheets.add("Scenario Sample"), model=wb.worksheets.add("Scoring Model"), src=wb.worksheets.add("Source Log"), ass=wb.worksheets.add("Assumptions");
function col(n){let s="";while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26)}return s;}
function title(sh,t,sub,last){sh.mergeCells(`A2:${last}2`);sh.getRange("A2").values=[[t]];sh.getRange("A2").format={font:{bold:true,size:16,color:"#183B56"}};sh.mergeCells(`A3:${last}3`);sh.getRange("A3").values=[[sub]];sh.getRange("A3").format={font:{italic:true,color:"#526477"}};}
function table(sh,start,headers,rows,name){sh.getRange(`A${start}:${col(headers.length)}${start}`).values=[headers];if(rows.length)sh.getRange(`A${start+1}:${col(headers.length)}${start+rows.length}`).values=rows;const t=sh.tables.add(`A${start}:${col(headers.length)}${start+rows.length}`,true,name);t.style="TableStyleMedium2";sh.freezePanes.freezeRows(start);return t;}
function base(sh){sh.showGridlines=false;}

title(readme,"Parks and civic venues evidence dataset","Public site inventory, scenario-conditioned occupancy ranges, factor scores and transparent baseline weighting","J");
readme.getRange("A6:B13").values=[["Metric","Value"],["Sites",sites.length],["Scenario rows",scenarioRows.length],["Scenarios per site",scenarios.length],["Public source layers",Object.keys(sourceDefs).length],["Retrieved",retrieved],["Observed site attendance rows",0],["Composite index range","0-100"]];
readme.getRange("A6:B6").format={fill:"#183B56",font:{bold:true,color:"#FFFFFF"}};
readme.getRange("A16:A20").values=[["How to use"],["1. Use Sites as the stable public inventory. Preserve source_id, source_native_id and source_updated."],["2. Join the full parks-civic-scenarios.csv on site_id. This workbook contains a 2,000-row preview."],["3. Replace priors when site capacity, attendance, schedules or operator data become available."],["4. Recalculate the composite only after agreeing policy weights; never convert missing data to zero."]];
readme.mergeCells("A16:J16");readme.getRange("A16:J16").format={fill:"#147D80",font:{bold:true,color:"#FFFFFF"}};
readme.mergeCells("A17:J17");readme.mergeCells("A18:J18");readme.mergeCells("A19:J19");readme.mergeCells("A20:J20");
readme.getRange("A23:A25").values=[["Boundary"],["This workbook supports civilian location categorisation and research estimates. It does not model weapon effects, select interception points, rank targets, or provide an operational recommendation."],["The final index is transparent and reversible: all component scores, ranges, assumptions, and weights are retained in the CSV files."]];readme.mergeCells("A23:J23");readme.mergeCells("A24:J24");readme.mergeCells("A25:J25");readme.getRange("A23:J23").format={fill:"#FFF0C7",font:{bold:true,color:"#725000"}};
readme.getRange("A:J").format.columnWidth=18;readme.getRange("A:A").format.columnWidth=27;readme.getRange("B:B").format.columnWidth=22;

title(siteSheet,"Site inventory","One normalized row per public park or civic/recreation venue; source-native fields retained where available",col(siteHeaders.length));
table(siteSheet,6,siteHeaders,sites.map(x=>siteHeaders.map(h=>x[h])),"SiteInventory");
const siteWidths=[15,34,20,22,12,12,13,13,13,34,20,20,18,18,48,54,15];siteWidths.forEach((w,i)=>siteSheet.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);siteSheet.getRange(`A7:${col(siteHeaders.length)}${6+sites.length}`).format.rowHeight=32;

title(scenSheet,"Scenario sample","First 2,000 of 57,656 conditional rows; use parks-civic-scenarios.csv for the complete dataset",col(scenarioHeaders.length));
table(scenSheet,6,scenarioHeaders,scenarioSample.map(x=>scenarioHeaders.map(h=>x[h])),"ScenarioSample");
const sw=[15,13,24,16,20,22,14,16,14,15,18,18,20,23,21,19,17,55,18,52];sw.forEach((w,i)=>scenSheet.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);scenSheet.getRange(`A7:${col(scenarioHeaders.length)}${6+scenarioSample.length}`).format.rowHeight=34;

title(model,"Scoring model","Editable baseline weights and explicit derivations; component scores are retained separately","H");
const weightRows=[["Factor","Weight","Meaning","Source status"],["Occupancy",weights.occupancy,"Log-normalized central people estimate","Derived from conditional range"],["Vulnerability",weights.vulnerability,"Broad venue-type vulnerability prior","Assumption; no individual inference"],["Civic service",weights.civicService,"Community/public-service role","Public function plus prior"],["Recovery/heritage",weights.recoveryHeritage,"Difficulty of replacement and protected heritage","Designation/type prior"],["Crowd concentration",weights.concentration,"Enclosure and crowd-density tendency","Venue-type prior"],["Access/egress",weights.accessEgress,"Evacuation/access constraint tendency","Venue-type prior"]];
model.getRange("A6:D12").values=weightRows;model.getRange("A6:D6").format={fill:"#183B56",font:{bold:true,color:"#FFFFFF"}};model.getRange("B7:B12").format.numberFormat="0%";model.getRange("A14:B15").values=[["Weight check","=SUM(B7:B12)"],["Occupancy formula","100*LOG10(1+central_people)/LOG10(2001), capped 0-100"]];model.getRange("B14").formulas=[["=SUM(B7:B12)"]];model.getRange("B14").format.numberFormat="0%";
const ruleHeaders=["Subtype","Vulnerability","Civic service","Recovery/heritage","Concentration","Access/egress","Occupancy basis"];
const ruleRows=Object.entries(typeRules).map(([k,v])=>[k,v.vulnerability,v.civicService,v.recoveryHeritage,v.concentration,v.accessEgress,v.basis]);table(model,18,ruleHeaders,ruleRows,"TypeRules");[22,16,18,22,18,18,60].forEach((w,i)=>model.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);

title(src,"Source log","Official sources used in this release","I");
const srcHeaders=["Dataset ID","Title","Agency","Coverage/date","Retrieved","Confidence","Use","Limitation","URL"];
const srcRows=Object.values(sourceDefs).map(d=>[d.id,d.title,d.agency,d.published,retrieved,d.confidence,d===sourceDefs.parkFacilities?"Spatial facility counts within parks":"Site inventory","No reliable site/hour attendance or capacity",d.url]);table(src,6,srcHeaders,srcRows,"Sources");[38,36,22,28,14,13,30,48,70].forEach((w,i)=>src.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);src.getRange("A7:I20").format.rowHeight=45;

title(ass,"Assumptions and gaps","Everything that must be validated, replaced or sensitivity-tested before downstream use","G");
const assHeaders=["Item","Applies to","Current treatment","Why needed","Replacement data","Uncertainty","Rule"];
const assRows=[
  ["Hourly attendance","All sites","Low/central/high scenario prior","No universal site-level attendance feed","Turnstiles, bookings, ticketing, footfall studies","High","Never describe central estimate as observed"],
  ["Park occupancy","Parks/reserves","Visitors per hectare with mapped-facility uplift","Public polygons lack visitor counts","Counters, mobility studies, event permits","High","Large area does not imply uniform occupancy"],
  ["Venue capacity","Clubs/libraries/theatres/sports","Broad type prior","Capacity is absent from source layers","Fire certificate capacity or operator inventory","High","Replace before site-specific decisions"],
  ["Event state","All event-capable sites","Separate EVENT row","Schedules are future-specific","Venue calendar, permit or booking feed","High","Do not average event and ordinary states"],
  ["Closed/adverse state","All sites","Near-zero public occupancy range","Closure compliance and staff presence vary","Operator closure procedure","Medium","Missing is not zero"],
  ["Vulnerability","All sites","Type-level score only","No ethical basis for inferring individuals","Aggregate age/accessibility data or operator input","Medium-high","Never infer individual health status"],
  ["Civic service","Civic venues","Function-based prior","Continuity role may vary by incident","Agency continuity designation","Medium","Keep service role separate from occupancy"],
  ["Recovery/heritage","Monuments/reserves","Higher type prior","Protected assets can be difficult to replace","Conservation/asset recovery plan","Medium","Not a monetary valuation"],
  ["Composite weights","All","Editable research baseline","Weights are policy choices, not discovered facts","Approved policy set plus sensitivity tests","High","Retain vector; do not store only total"],
  ["Duplicates/co-location","All layers","Source records kept separate","Different functions may share one building","Stable building/site crosswalk","Medium","Do not sum co-located rows without deduplication"],
];table(ass,6,assHeaders,assRows,"AssumptionRegister");[30,26,46,45,45,18,52].forEach((w,i)=>ass.getRange(`${col(i+1)}:${col(i+1)}`).format.columnWidth=w);ass.getRange("A7:G20").format.rowHeight=55;

[readme,siteSheet,scenSheet,model,src,ass].forEach(base);
wb.recalculate();
const errors=await wb.inspect({kind:"match",searchTerm:"#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!",options:{useRegex:true,maxResults:100},summary:"formula error scan"});
const previews={"Read Me":"A1:J26","Sites":"A1:Q24","Scenario Sample":"A1:T24","Scoring Model":"A1:G27","Source Log":"A1:I15","Assumptions":"A1:G17"};
for(const [n,range] of Object.entries(previews)){const p=await wb.render({sheetName:n,range,scale:1,format:"png"});fs.writeFileSync(path.join(root,"work/parks-civic",`${n.replaceAll(" ","-").toLowerCase()}.png`),new Uint8Array(await p.arrayBuffer()));}
const out=await SpreadsheetFile.exportXlsx(wb);await out.save(path.join(outDir,"singapore-parks-civic-evidence.xlsx"));
console.log(JSON.stringify({sites:sites.length,scenarios:scenarioRows.length,subtypes:Object.fromEntries([...new Set(sites.map(x=>x.subtype))].map(k=>[k,sites.filter(x=>x.subtype===k).length])),errors:errors.ndjson,outputs:["singapore-parks-civic-evidence.xlsx","parks-civic-sites.csv","parks-civic-scenarios.csv","parks-civic-metadata.json"]},null,2));
