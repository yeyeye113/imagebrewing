// Extended backtest with 20 new failure cases
function normalRandom(mean=0,stddev=1){const u1=Math.random(),u2=Math.random();const z=Math.sqrt(-2*Math.log(u1||0.0001))*Math.cos(2*Math.PI*u2);return mean+z*stddev}
function clamp(v,min,max){return Math.max(min,Math.min(max,v))}
function avg(arr){return arr.length?arr.reduce((a,b)=>a+b,0)/arr.length:0}
function powerLawRandom(min,max,alpha=2.5){const u=Math.random();const v=min*Math.pow(1-u,-1/(alpha-1));return v>max?max:v}

function computeComposite(scores){
  const a=scores.artifact,m=scores.market,d=scores.distribution,r=scores.retention,b=scores.business,risk=scores.risk;
  const ps=avg([a.quality,a.originality,a.clarity,a.usability,a.emotionalHook,a.differentiation,a.completeness,a.reliability,a.aestheticQuality,a.problemSolutionFit]);
  const ms=avg([m.marketSize,m.audiencePain,m.willingnessToPay,m.trendFit,m.timingScore,100-m.competitionIntensity,100-m.substitutionRisk,100-m.platformDependency,100-m.regulatoryRisk,m.categoryGrowth]);
  const ds=avg([d.shareability,d.viralityPotential,d.storyValue,d.socialProofPotential,d.creatorReputation,d.distributionPower,d.communityPotential,d.mediaFriendliness,d.recommendationFit,d.visualSpreadPower]);
  const rs=avg([r.activationRatePotential,r.firstSessionValue,r.retentionPotential,r.habitPotential,r.networkEffect,r.switchingCost,r.longTermValue,r.updateVelocity,r.feedbackLoopStrength,r.communityLockIn]);
  const bs=avg([b.monetizationFit,b.pricingPower,b.arpuPotential,b.conversionPotential,b.upsellPotential,b.enterprisePotential,b.lowCostDistribution,b.grossMarginPotential,b.lifecycleValue,b.revenueDiversity]);
  const rks=100-avg([risk.executionRisk,risk.technicalDebt,risk.churnRisk,risk.negativeFeedbackRisk,risk.copycatRisk,risk.scalabilityRisk,risk.maintenanceBurden,risk.legalRisk,risk.platformBanRisk,risk.founderDependency]);
  const overall=ps*0.20+ms*0.18+ds*0.12+rs*0.22+bs*0.13+rks*0.15;
  return{productScore:ps,marketScore:ms,distributionScore:ds,retentionScore:rs,businessScore:bs,riskScore:rks,overall,clarityScore:a.clarity,painScore:m.audiencePain,differentiationScore:a.differentiation};
}

function simulateOne(composite,scores,config,strategyBoosts){
  const noise=()=>normalRandom(0,1),luck=()=>Math.random();
  let qf=composite.productScore/100,mf=composite.marketScore/100,df=composite.distributionScore/100,rf=composite.retentionScore/100,bf=composite.businessScore/100,rkf=composite.riskScore/100;
  const cf=composite.clarityScore/100,pf=composite.painScore/100,dif=composite.differentiationScore/100;
  if(strategyBoosts.clarity_boost)qf=clamp(qf+strategyBoosts.clarity_boost*0.08,0,1);
  if(strategyBoosts.distribution_boost)df=clamp(df+strategyBoosts.distribution_boost*0.08,0,1);
  if(strategyBoosts.retention_boost)rf=clamp(rf+strategyBoosts.retention_boost*0.12,0,1);
  const algorithmLuck=powerLawRandom(0.5,3,2.5);
  const timingLuck=clamp(1+noise()*0.25,0.3,2);
  const marketNoise=clamp(1+noise()*0.15,0.5,1.8);
  const creatorConsistency=clamp(0.4+luck()*0.4+noise()*0.1,0,1);
  const viralChance=luck(),negativeChance=luck();
  const viralBoost=viralChance>0.97?10+luck()*20:viralChance>0.9?3+luck()*7:viralChance>0.8?1.5+luck()*1.5:1;
  const baseExposure=qf*df*mf*algorithmLuck*timingLuck*8000;
  const distRetentionGap=Math.max(0,df-rf-0.1);
  const distRetentionPenalty=1-distRetentionGap*0.9;
  const initialExposure=baseExposure*viralBoost*marketNoise*distRetentionPenalty;
  const ctr=clamp(cf*0.12+df*0.08+pf*0.05+noise()*0.02,0.005,0.25);
  const visitors=initialExposure*ctr;
  const convRate=clamp(cf*0.25+pf*0.15+qf*0.1+(1-rkf)*0.05+noise()*0.03,0.01,0.45);
  const initialUsers=visitors*convRate;
  const d1Retention=clamp(rf*0.45+qf*0.2+cf*0.15+pf*0.2+noise()*0.05,0.05,0.85);
  let currentUsers=initialUsers,totalUsers=initialUsers,totalRevenue=0,activeUsers=initialUsers*d1Retention;
  const steps=config.granularity==='day'?config.periodDays:config.granularity==='week'?Math.ceil(config.periodDays/7):Math.ceil(config.periodDays/30);
  const stepDays=config.granularity==='day'?1:config.granularity==='week'?7:30;
  for(let step=0;step<steps;step++){
    const day=(step+1)*stepDays;
    const organicGrowth=df*0.015*algorithmLuck*creatorConsistency;
    const wordOfMouth=activeUsers*rf*0.0008*dif;
    const compSqueeze=clamp(1-Math.max(0,scores.market.competitionIntensity/100-dif*0.6)*Math.min(1,day/180)*0.5,0.5,1);
    const fatigue=viralBoost<=1?1:Math.max(0.3,Math.exp(-day/(viralBoost>5?14:30)*0.5));
    const newUsersStep=(organicGrowth+wordOfMouth)*currentUsers*stepDays*compSqueeze*fatigue;
    const currentRetention=day<=7?d1Retention*Math.pow(Math.max(day,1)/1,-0.3):d1Retention*Math.pow(7,-0.3)*Math.pow(Math.max(day,1)/7,-0.12);
    const churnRate=clamp(1-currentRetention,0,0.6)*(1+rkf*0.003);
    const churnedUsers=currentUsers*churnRate*stepDays*0.005;
    const negImpact=negativeChance>0.97?0.4:negativeChance>0.9?0.15:negativeChance>0.8?0.05:0;
    currentUsers=Math.max(0,currentUsers+newUsersStep-churnedUsers-currentUsers*negImpact);
    activeUsers=currentUsers*currentRetention;
    totalUsers=Math.max(totalUsers,totalUsers+newUsersStep);
    totalRevenue+=Math.max(0,activeUsers*(bf*0.4+noise()*0.08)*stepDays*0.008);
  }
  const finalRetention=clamp(config.periodDays<=7?d1Retention*Math.pow(config.periodDays,-0.3):d1Retention*Math.pow(7,-0.3)*Math.pow(config.periodDays/7,-0.12),0,1);
  const externalRiskFactor=clamp((scores.market.platformDependency/100)*0.3+(scores.risk.legalRisk/100)*0.25+(scores.risk.founderDependency/100)*0.2+(scores.risk.copycatRisk/100)*0.15+(scores.market.competitionIntensity/100)*0.1,0,1);
  const externalDeathChance=externalRiskFactor*(1-dif*0.5);
  let outcomeClass;
  if(currentUsers<30)outcomeClass='dead';
  else if(externalDeathChance>0.5&&currentUsers<2000&&luck()<externalDeathChance)outcomeClass='dead';
  else if(currentUsers<100&&finalRetention<0.12)outcomeClass='dead';
  else if(distRetentionGap>0.25&&currentUsers<400)outcomeClass='dead';
  else if(rf<0.45&&df>rf+0.2&&currentUsers<800)outcomeClass='dead';
  else if(currentUsers<400&&finalRetention<0.3)outcomeClass='low_alive';
  else if(currentUsers>500&&currentUsers<10000&&finalRetention>0.12&&df<0.55)outcomeClass='moderate_success';
  else if(rf>0.6&&finalRetention>0.15&&scores.market.competitionIntensity<75)outcomeClass='long_compound';
  else if(currentUsers<3000&&finalRetention>0.25)outcomeClass='niche_success';
  else if(currentUsers>30000&&viralBoost>5)outcomeClass='blockbuster';
  else if(currentUsers<8000)outcomeClass='moderate_success';
  else outcomeClass='clear_success';
  return{outcomeClass,finalUsers:Math.round(currentUsers),retentionRate:finalRetention};
}

function buildScores(p){
  return{
    artifact:{quality:p.clarity,originality:p.clarity,clarity:p.clarity,usability:p.clarity,emotionalHook:Math.round(p.clarity*0.8+p.pain*0.2),differentiation:p.clarity,completeness:p.clarity,reliability:p.clarity,aestheticQuality:p.clarity,problemSolutionFit:Math.round(p.clarity*0.5+p.pain*0.5)},
    market:{marketSize:65,audiencePain:p.pain,willingnessToPay:Math.round(p.pain*0.8),trendFit:60,timingScore:60,competitionIntensity:50,substitutionRisk:40,platformDependency:30,regulatoryRisk:15,categoryGrowth:55},
    distribution:{shareability:p.distribution,viralityPotential:p.distribution,storyValue:Math.round(p.distribution*0.9),socialProofPotential:Math.round(p.distribution*0.8),creatorReputation:50,distributionPower:p.distribution,communityPotential:Math.round(p.distribution*0.85),mediaFriendliness:p.distribution,recommendationFit:Math.round(p.distribution*0.9),visualSpreadPower:Math.round(p.distribution*0.8)},
    retention:{activationRatePotential:p.retention,firstSessionValue:p.retention,retentionPotential:p.retention,habitPotential:Math.round(p.retention*0.9),networkEffect:Math.round(p.retention*0.7),switchingCost:Math.round(p.retention*0.6),longTermValue:p.retention,updateVelocity:Math.round(p.retention*0.8),feedbackLoopStrength:Math.round(p.retention*0.75),communityLockIn:Math.round(p.retention*0.65)},
    business:{monetizationFit:Math.round(p.pain*0.6+p.clarity*0.4),pricingPower:Math.round(p.pain*0.5+p.clarity*0.3),arpuPotential:Math.round(p.pain*0.5),conversionPotential:Math.round(p.clarity*0.5+p.pain*0.3),upsellPotential:Math.round(p.pain*0.4),enterprisePotential:Math.round(p.clarity*0.4),lowCostDistribution:p.distribution,grossMarginPotential:60,lifecycleValue:Math.round(p.retention*0.6+p.pain*0.3),revenueDiversity:40},
    risk:{executionRisk:Math.round(100-p.clarity*0.5-p.retention*0.3),technicalDebt:30,churnRisk:Math.round(100-p.retention),negativeFeedbackRisk:Math.round(100-p.clarity*0.4-p.pain*0.3),copycatRisk:40,scalabilityRisk:35,maintenanceBurden:30,legalRisk:10,platformBanRisk:30,founderDependency:35}
  }
}

import{readFileSync}from'fs';
const expansion=JSON.parse(readFileSync('cases/backtest/backtest_expansion.json','utf8'));
const N=2000;
let exactHits=0,totalCases=0;
const outcomeMap={dead:'dead',low_alive:'low_alive',niche_success:'niche_success',moderate_success:'moderate_success',clear_success:'clear_success',blockbuster:'blockbuster',long_compound:'long_compound'};

console.log('=== EXTENDED BACKTEST (20 new cases) ===');
console.log('Runs per case:', N);
console.log('');

for(const tc of expansion){
  const actual=outcomeMap[tc.actual_outcome]||tc.actual_outcome;
  const scores=buildScores(tc.pre_launch);
  const composite=computeComposite(scores);
  const config={runs:N,periodDays:180,granularity:'week',mode:'standard',scenarios:['baseline'],strategies:['original']};
  const counts={dead:0,low_alive:0,niche_success:0,moderate_success:0,clear_success:0,blockbuster:0,long_compound:0};
  for(let i=0;i<N;i++){const r=simulateOne(composite,scores,config,{});counts[r.outcomeClass]++}
  const sorted=Object.entries(counts).map(([k,v])=>[k,v/N]).sort((a,b)=>b[1]-a[1]);
  const ml=sorted[0][0];
  const match=ml===actual;
  if(match)exactHits++;
  totalCases++;
  const actualProb=(counts[actual]/N*100).toFixed(1);
  console.log('['+(match?'EXACT':'MISS')+'] '+tc.name+' ('+tc.path_type.substring(0,30)+')');
  console.log('  Predicted: '+ml+' ('+(sorted[0][1]*100).toFixed(1)+'%) | Actual: '+actual+' ('+actualProb+'%)');
}

console.log('');
console.log('=== ACCURACY ===');
console.log('  Exact hit rate: '+(exactHits/totalCases*100).toFixed(0)+'% ('+exactHits+'/'+totalCases+')');
