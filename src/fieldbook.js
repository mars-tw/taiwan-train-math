// Local learning goals. No dates, streak pressure, personal data or locked games.
const LEVEL_IDS = ['small', 'medium', 'large'];
const smallGames = ['count','order','pattern','cargo','luggage','sharing','memory','identify','treasure','tracks','maze','puzzle'];
const olderGames = ['count','order','pattern','cargo','boarding','sharing','memory','compare','tickets','tracks','clock','balance'];
const titles = ['點名上車','排好車廂','掛好車旗','裝好補給','整理出發','分享點心','找回車卡','月台小觀察','尋找小寶物','接通小站','看路出發','最後的準備'];
const smallStories = ['朋友都到月台了，幫忙點名吧。','車廂停亂了，請照數字排隊。','旗子排到一半，幫忙接下去。','野餐前，把需要的箱子裝上車。','把行李分好，大家就找得到。','點心每位一樣多，才好一起出發。','車卡散開了，找回相同的兩張。','列車朋友來了，認出是哪台列車。','朋友留下小寶物，仔細找一找。','最後一段軌道還沒接好。','看看哪條路能到小站。','把列車照片拼好，留下旅行紀念。'];
const olderStories = [...smallStories];
olderStories[4] = '朋友上車又下車，看看車上還有幾位。';
olderStories[7] = '兩邊月台的車票，哪邊比較多？';
olderStories[8] = '用有限的代幣，替車票付剛好的點數。';
olderStories[10] = '看好出發時刻，別把長短針弄反了。';
olderStories[11] = '補給要平衡，試著配出一樣的重量。';
export const CHAPTERS = Object.freeze([
  { name:'月台準備', stamp:'月台小幫手', ending:'點名、編組、車旗都準備好了。月台可以迎接朋友囉！' },
  { name:'野餐補給', stamp:'貼心補給員', ending:'補給收好了，每位朋友也分到點心。下一段可以出發了！' },
  { name:'沿路找朋友', stamp:'細心觀察員', ending:'一路仔細看、慢慢想，朋友留下的線索都找到了。' },
  { name:'平安送到站', stamp:'小站列車長', ending:'最後的準備完成，小站收到大家一起帶來的心意。' },
].map(Object.freeze));
export const MISSION_COUNT = 12;
const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function normalizeFieldbook(value) {
  return Object.fromEntries(LEVEL_IDS.map(level => [level, Number.isSafeInteger(value?.[level]) && value[level] >= 0 ? Math.min(value[level], MISSION_COUNT) : 0]));
}
export function fieldMission(level, index) {
  if (!LEVEL_IDS.includes(level) || !Number.isInteger(index) || index < 0 || index >= MISSION_COUNT) return null;
  const games = level === 'small' ? smallGames : olderGames;
  const names = level === 'small' ? titles : titles.map((name,i) => ({4:'乘客變變變',7:'車票比一比',8:'付好小車票',10:'準時發車',11:'補給秤一秤'}[i] || name));
  return { index, game:games[index], title:names[index], story:(level === 'small' ? smallStories : olderStories)[index], chapter:Math.floor(index/3) };
}
export function currentFieldMission(progress) {
  return fieldMission(progress?.level, normalizeFieldbook(progress?.fieldbook)[progress?.level]);
}
// Called before trip.awarded is set, only after the last station was solved.
// A matching free practice also counts. Mixed/story trips never skip goals.
export function advanceFieldbook(progress, trip) {
  const level = trip?.meta?.level;
  const saved = normalizeFieldbook(progress.fieldbook);
  const mission = fieldMission(level, saved[level]);
  if (!mission || trip.awarded || !trip.solved || trip.meta.journey || trip.meta.practice !== mission.game
    || !Array.isArray(trip.questions) || trip.questions.length !== (level === 'small' ? 3 : 5)
    || trip.index !== trip.questions.length - 1 || !trip.questions.every(q => q.level === level && q.game === mission.game)) return null;
  saved[level]++;
  progress.fieldbook = saved;
  return { ...mission, level, completed:saved[level], stamp:saved[level]%3 === 0 ? CHAPTERS[mission.chapter] : null };
}
export function fieldbookMarkup(progress, { collection = false } = {}) {
  const level = LEVEL_IDS.includes(progress?.level) ? progress.level : 'small';
  const done = normalizeFieldbook(progress?.fieldbook)[level], mission = fieldMission(level,done);
  const stamps = CHAPTERS.map((chapter,i) => `<span class="field-stamp ${done >= (i+1)*3 ? 'earned' : ''}"><strong>${done >= (i+1)*3 ? '✓' : `${i+1}`}</strong>${esc(chapter.stamp)}<small>${done >= (i+1)*3 ? '已收藏' : `完成第 ${(i+1)*3} 個任務取得`}</small></span>`).join('');
  return `<section class="fieldbook" aria-label="小站任務冊"><div class="fieldbook-heading"><div><small>小站任務冊 · ${level === 'small' ? '3–4' : level === 'medium' ? '5–6' : '7–8'} 歲</small><h2>${mission ? `第 ${mission.chapter+1} 章：${CHAPTERS[mission.chapter].name}` : '四章完成，小站謝謝你！'}</h2></div><strong class="fieldbook-count">${done}／12</strong></div><progress value="${done}" max="12" aria-label="已完成 ${done} 個任務，共 12 個"></progress>${collection ? `<div class="field-stamps">${stamps}</div>` : ''}${mission ? `<p class="fieldbook-story"><strong>${esc(mission.title)}</strong> · ${esc(mission.story)}</p><div class="fieldbook-action"><small>完成一趟 ${level === 'small' ? 3 : 5} 站，前進一格。每三格收一枚章。<br>可用提示，隨時休息。</small><button type="button" data-fieldbook="start" class="primary-btn">${done ? '接著玩' : '開始任務'} →</button></div>` : `<p>已收齊四枚章。可以到遊戲室自由選題，也能請家長換適合的難度。</p><a class="secondary-btn" href="#playroom">回遊戲室</a>`}</section>`;
}
export function fieldbookResultMarkup(result) {
  if (!result) return '';
  const mission = fieldMission(result.level,result.completed);
  return `<section class="fieldbook fieldbook-result" role="status"><h2>${result.stamp ? `新收藏章：${esc(result.stamp.stamp)}` : `任務完成：${esc(result.title)}`}</h2><p>${esc(result.stamp ? result.stamp.ending : '小站任務冊前進一格，做得好！')}（${result.completed}／12）</p>${mission ? `<button type="button" data-fieldbook="start" class="primary-btn">下一個：${esc(mission.title)} →</button>` : '<a href="#stamps" class="primary-btn">看看四枚收藏章 →</a>'}<a href="#playroom" class="text-btn">先休息，回遊戲室</a></section>`;
}
