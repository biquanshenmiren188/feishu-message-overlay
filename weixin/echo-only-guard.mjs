// Initial trial: fixed fictional text only. No agent/media/cache dispatch.
export function isAllowedEcho(message, ownerId) {
  if (typeof ownerId !== 'string' || !ownerId || message?.from_user_id !== ownerId) return false;
  const items = message.item_list;
  return Array.isArray(items) && items.length === 1 && items[0]?.type === 1
    && !items[0].ref_msg && !items[0].image_item && !items[0].voice_item
    && !items[0].video_item && !items[0].file_item
    && items[0].text_item?.text?.trim() === '/echo 测试123';
}
export function createEchoOnlyProcessor(officialProcess, ownerId) {
  return async (message, dependencies) => {
    if (!isAllowedEcho(message, ownerId)) return { accepted: false };
    await officialProcess(message, dependencies);
    return { accepted: true };
  };
}
