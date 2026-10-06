import { STORAGE_KEY, readProgress } from "./engine.js?v=1.11.0";
import { TRIP_SESSION_KEY, readTripSession } from "./trip-session.js?v=1.11.0";
const MAX_BACKUP = 262144;
const temporary = values => ({ getItem: key => Object.hasOwn(values, key) ? values[key] : null });
export function encodeBackup(progress, session = null, { trains } = {}) {
  const passport = readProgress(temporary({ [STORAGE_KEY]: JSON.stringify(progress) }));
  const snapshot = typeof session === "string" && session.length <= 131072 && Array.isArray(trains)
    && readTripSession(temporary({ [TRIP_SESSION_KEY]: session }), { trains }) ? session : null;
  return JSON.stringify({ format: "taiwan-train-math.backup", version: 1, passport, session: snapshot }, null, 2);
}
export function decodeBackup(text, { trains } = {}) {
  if (typeof text !== "string" || text.length > MAX_BACKUP) throw new Error("備份檔案太大或格式不正確。");
  let data;
  try { data = JSON.parse(text); } catch { throw new Error("這不是可讀的護照備份檔。"); }
  if (!data || data.format !== "taiwan-train-math.backup" || data.version !== 1
    || !data.passport || data.passport.version !== 1 || ![null, "string"].includes(data.session === null ? null : typeof data.session))
    throw new Error("這不是本遊戲的護照備份。");
  const progress = readProgress(temporary({ [STORAGE_KEY]: JSON.stringify(data.passport) }));
  let trip = null;
  if (data.session !== null) {
    trip = readTripSession(temporary({ [TRIP_SESSION_KEY]: data.session }), { trains });
    if (!trip) throw new Error("備份中的未完成旅程格式不正確，尚未匯入。");
  }
  return { progress, trip, session: data.session };
}
