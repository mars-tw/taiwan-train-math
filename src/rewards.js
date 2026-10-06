import { SOUVENIRS, giftChoices } from "./adventure.js?v=1.10.0";

// Unclaimed rewards survive leaving the finish screen. Choices stay fixed
// until one is claimed, and each completed journey provides one credit.
export function enqueueGift(progress) {
  progress.giftCredits = (progress.giftCredits || 0) + 1;
}
export function offerGifts(progress, trainId, rng = Math.random) {
  if (!progress.giftCredits) return [];
  if (!progress.giftOffer?.length)
    progress.giftOffer = giftChoices(progress, trainId, rng).map(item => item.id);
  return progress.giftOffer.map(id => SOUVENIRS.find(item => item.id === id)).filter(Boolean);
}
export function claimGift(progress, id) {
  if (!progress.giftCredits || !progress.giftOffer?.includes(id)) return null;
  const gift = SOUVENIRS.find(item => item.id === id);
  if (!gift) return null;
  if (!progress.souvenirs.includes(id)) progress.souvenirs.push(id);
  progress.giftCredits--;
  progress.giftOffer = [];
  return gift;
}
