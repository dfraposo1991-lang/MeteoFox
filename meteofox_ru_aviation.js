/* METEOFOX LEVC: interpretação em russo exclusiva da apresentação da LEVC.
   Não altera os boletins de origem; grupos desconhecidos não são inventados. */
(function(){
'use strict';
const weather={DZ:'морось',RA:'дождь',SN:'снег',SG:'снежные зёрна',IC:'ледяные кристаллы',
 PL:'ледяная крупа',GR:'град',GS:'мелкий град',UP:'осадки неопределённого типа',
 BR:'дымка',FG:'туман',FU:'дым',VA:'вулканический пепел',DU:'пыль',SA:'песок',
 HZ:'мгла',PY:'водяные брызги',PO:'пыльные вихри',SQ:'шквал',FC:'воронкообразное облако',
 SS:'песчаная буря',DS:'пыльная буря',TS:'гроза',SH:'ливневые осадки',FZ:'переохлаждённые осадки',
 MI:'низкий',BC:'клочья',PR:'частичный',DR:'позёмок',BL:'метель',
 RE:'недавние',VC:'поблизости'};
const clouds={FEW:'незначительная облачность (1–2 октанта)',SCT:'рассеянная облачность (3–4 октанта)',
 BKN:'значительная облачность (5–7 октантов)',OVC:'сплошная облачность (8 октантов)',VV:'вертикальная видимость'};
const num=(n)=>Number(n).toLocaleString('ru-RU',{maximumFractionDigits:1});
const kmh=(kt)=>num(Number(kt)*1.852);
function decodeWeather(t){
 let s=t, intensity='';
 if(s[0]==='-'){intensity='слабая интенсивность';s=s.slice(1);}
 else if(s[0]==='+'){intensity='сильная интенсивность';s=s.slice(1);}
 const parts=[];if(s.startsWith('VC')){parts.push('поблизости');s=s.slice(2);}
 if(s.startsWith('RE')){parts.push('недавно');s=s.slice(2);}
 for(const modifier of ['TS','SH','FZ','MI','BC','PR','DR','BL']){
  if(s.startsWith(modifier)){parts.push(weather[modifier]);s=s.slice(2);break;}
 }
 while(s.length>=2){const code=s.slice(0,2);if(!weather[code])return null;parts.push(weather[code]);s=s.slice(2);}
 return s.length?null:[...parts,intensity].filter(Boolean).join(', ');
}
function decodeGroup(t){
 let m;
 if(/^(METAR|SPECI|TAF|AMD|COR|AUTO|NIL|=)$/.test(t))return null;
 if(/^[A-Z]{4}$/.test(t))return null;
 if((m=/^(\d{2})(\d{2})(\d{2})Z$/.exec(t)))return 'Время выпуска: '+m[1]+'-е число, '+m[2]+':'+m[3]+' UTC';
 if((m=/^(\d{2})(\d{2})\/(\d{2})(\d{2})$/.exec(t)))return 'Период прогноза: с '+m[1]+'-го, '+m[2]+':00 UTC до '+m[3]+'-го, '+m[4]+':00 UTC';
 if((m=/^FM(\d{2})(\d{2})(\d{2})$/.exec(t)))return 'Изменение прогноза с '+m[1]+'-го числа, '+m[2]+':'+m[3]+' UTC';
 if(t==='TEMPO')return 'Временные изменения погоды';
 if(t==='BECMG')return 'Постепенное изменение условий';
 if(t==='PROB30')return 'Вероятность следующих условий: 30%';
 if(t==='PROB40')return 'Вероятность следующих условий: 40%';
 if(t==='NOSIG')return 'Существенных изменений в ближайшие два часа не ожидается';
 if(t==='CAVOK')return 'Видимость не менее 10 км, существенная погода и значимая облачность отсутствуют (CAVOK)';
 if(t==='NSC')return 'Значимой облачности нет';
 if(t==='NCD')return 'Облачность не обнаружена автоматической системой';
 if(t==='SKC'||t==='CLR')return 'Ясное небо';
 if((m=/^(VRB|\d{3}|\/\/\/)(\d{2,3}|\/\/)(?:G(\d{2,3}))?(KT|MPS|KMH)$/.exec(t))){
  const factor=m[4]==='KT'?1.852:m[4]==='MPS'?3.6:1;
  const speed=m[2]==='//'? 'не определена':num(Number(m[2])*factor)+' км/ч';
  const direction=m[1]==='VRB'?'переменное направление':m[1]==='///'?'направление неизвестно':m[1]+'°';
  return 'Ветер: '+direction+', '+speed+(m[3]?', порывы до '+num(Number(m[3])*factor)+' км/ч':'');
 }
 if((m=/^(\d{3})V(\d{3})$/.exec(t)))return 'Изменение направления ветра: от '+m[1]+'° до '+m[2]+'°';
 if(t==='9999')return 'Горизонтальная видимость: 10 км или более';
 if((m=/^\d{4}$/.exec(t)))return 'Горизонтальная видимость: '+num(Number(t)/1000)+' км';
 if((m=/^(FEW|SCT|BKN|OVC|VV)(\d{3}|\/\/\/)(CB|TCU)?$/.exec(t))){
  const h=m[2]==='///'?'не установлена':'нижняя граница '+num(Number(m[2])*100*0.3048)+' м';
  return 'Облака: '+clouds[m[1]]+', '+h+(m[3]==='CB'?', кучево-дождевые облака':m[3]==='TCU'?', мощные кучевые облака':'');
 }
 if((m=/^(M?\d{2}|\/\/)\/(M?\d{2}|\/\/)$/.exec(t))){
  const temp=x=>x==='//'? 'не определена':(x.startsWith('M')?'-':'')+Number(x.replace('M',''))+' °C';
  return 'Температура воздуха: '+temp(m[1])+'; точка росы: '+temp(m[2]);
 }
 if((m=/^Q(\d{4})$/.exec(t)))return 'Давление QNH: '+Number(m[1])+' гПа';
 if((m=/^A(\d{4})$/.exec(t)))return 'Давление: '+num(Number(m[1])/100)+' дюйма рт. ст.';
 if(t==='NSW')return 'Значимые погодные явления прекратятся';
 if(t==='VV///')return 'Вертикальная видимость не определена';
 if(t==='TX' || t==='TN')return null;
 if(t==='RMK')return 'Дополнительные замечания станции';
 if(t==='WS')return 'Предупреждение о сдвиге ветра';
 if(/^R\d{2}/.test(t))return null; // специальные группы ВПП не интерпретируем без полной спецификации
 return decodeWeather(t);
}
function decode(raw,kind){
 const items=String(raw||'').replace(/=/g,' ').trim().split(/\s+/).filter(Boolean);
 if(!items.length)return 'Бюллетень пока недоступен.';
 const lines=[],unparsed=[];
 let isRemark=false;
 for(const token of items){
  if(token==='RMK')isRemark=true;
  if(isRemark&&token!=='RMK')continue; // не публикуем необоснованные толкования RMK
  const text=decodeGroup(token);
  if(text)lines.push(text);
  else if(!/^(METAR|SPECI|TAF|AMD|COR|AUTO|NIL|RMK|[A-Z]{4})$/.test(token))unparsed.push(token);
 }
 if(!lines.length)return 'Автоматическая расшифровка для этого бюллетеня недоступна.';
 if(unparsed.length)lines.push('Некоторые специализированные группы не интерпретированы; для авиационных решений необходим официальный бюллетень.');
 return lines.join('\n');
}
window.MeteoFoxRussianAviation={decode};
})();