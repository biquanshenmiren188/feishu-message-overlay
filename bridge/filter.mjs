export class BotGate {
  constructor(chatIds, now = Date.now(), botIds = []) {
    if (!Array.isArray(chatIds) || chatIds.length < 1 || chatIds.length > 5 || chatIds.some(id => typeof id !== 'string' || !/^oc_[a-zA-Z0-9_-]+$/.test(id))) throw new Error('invalid_selection');
    this.chatIds = new Set(chatIds); this.cutoff = now; this.seen = new Map(); this.ttl = 30 * 60 * 1000;
    if(!Array.isArray(botIds) || botIds.length>50 || botIds.some(id=>typeof id!=='string' || !id || id.length>256)) throw new Error('invalid_bots');
    this.botIds=new Set(botIds);
  }
  replaceChats(ids) {
    if (!Array.isArray(ids) || ids.length>2000 || ids.some(id=>typeof id!=='string'||!/^oc_[a-zA-Z0-9_-]+$/.test(id)))throw new Error('invalid_membership');
    this.chatIds=new Set(ids);
  }
  resume(now = Date.now()) { this.cutoff=now; }
  accept(data, now = Date.now()) {
    const sender = data?.sender, message = data?.message;
    // Do not access the body until metadata proves an authorized group and bot sender.
    if (sender?.sender_type !== 'bot' || message?.chat_type !== 'group' || !this.chatIds.has(message.chat_id)) return null;
    if (typeof message.message_id !== 'string' || !message.message_id || message.message_id.length > 256 || typeof sender.sender_id?.open_id !== 'string' || !sender.sender_id.open_id) return null;
    if(this.botIds.size && !this.botIds.has(sender.sender_id.open_id)) return null;
    const timestamp = Number(message.create_time);
    if (!Number.isSafeInteger(timestamp) || timestamp <= this.cutoff || timestamp > now + 60_000 || now - timestamp >= this.ttl) return null;
    for (const [id, received] of this.seen) if (now - received >= this.ttl) this.seen.delete(id);
    const key = message.chat_id + '\0' + message.message_id;
    if (this.seen.has(key)) return null;
    if (this.seen.size >= 10000) throw new Error('dedup_capacity');
    this.seen.set(key, now);
    const content = message.content;
    if (typeof content !== 'string' || content.length > 524288) throw new Error('body_limit');
    return { header: { event_type: 'im.message.receive_v1' }, event: {
      sender: { sender_type: 'bot', sender_id: { open_id: sender.sender_id.open_id } },
      message: { message_id: message.message_id, chat_id: message.chat_id, chat_type: 'group', create_time: String(timestamp), message_type: message.message_type, content }
    } };
  }
}
