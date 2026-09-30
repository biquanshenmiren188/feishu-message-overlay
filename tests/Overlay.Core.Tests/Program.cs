using Overlay.Core;
var now = DateTimeOffset.UtcNow;
var store = new MessageStore(2, TimeSpan.FromMinutes(30));
var checks = 0;
void Check(bool value, string name) { if (!value) throw new InvalidOperationException(name); checks++; Console.WriteLine("PASS " + name); }
IncomingMessage Message(string id, string source = "chosen", int seconds = 1) => new(id, source, "演示发送人", "中文消息", now.AddSeconds(seconds), SenderKind.Bot, "fake-bot");
store.Start(now);
Check(!store.Add(Message("old", seconds: -1), "chosen", now), "历史消息不重播");
Check(!store.Add(Message("other", "unselected"), "chosen", now.AddSeconds(2)), "仅选定来源");
Check(store.Add(Message("one"), "chosen", now.AddSeconds(2)), "接收新消息");
Check(!store.Add(Message("one"), "chosen", now.AddSeconds(2)), "重复消息不重播");
store.Add(Message("two"), "chosen", now.AddSeconds(2)); store.Add(Message("three"), "chosen", now.AddSeconds(2));
Check(store.Items.Count == 2 && store.Items[0].Id == "three", "容量与顺序");
store.Prune(now.AddMinutes(31)); Check(store.Items.Count == 0, "超时删除");
store.Clear(now.AddMinutes(31)); Check(!store.Add(Message("one"), "chosen", now.AddMinutes(31)), "清空后不重播");
store.Start(now); store.Add(Message("long") with { Text = new string('中', 20000) }, "chosen", now.AddSeconds(2));
Check(store.Items[0].Text.Contains("限制显示长度"), "中文长文显式截断");
Check(!store.Add(Message("future", seconds: 1000), "chosen", now), "拒绝异常未来时间");
await using var demo = new DemoSource(); Check(!demo.IsRealConnection, "演示明确非真实连接");
Console.WriteLine($"{checks} checks passed.");
store.Start(now);
Check(!store.Add(Message("human") with { Kind = SenderKind.Person, Text = "我是机器人" }, "chosen", now.AddSeconds(2)), "不靠正文猜机器人");
Check(!store.Add(Message("unknown") with { Kind = SenderKind.Unknown }, "chosen", now.AddSeconds(2)), "未知发送类型不提醒");
string Event(string senderType, string chat, string type, string content) => System.Text.Json.JsonSerializer.Serialize(new
{
    header = new { event_type = "im.message.receive_v1" },
    @event = new { sender = new { sender_type = senderType, sender_id = new { open_id = "synthetic-bot-id" } },
        message = new { message_id = "synthetic-message-id", chat_id = chat, chat_type = "group", create_time = now.AddSeconds(1).ToUnixTimeMilliseconds().ToString(), message_type = type, content } }
});
var filter = new BotEventFilter(["chosen"]);
Check(filter.Parse(Event("user", "chosen", "text", "{\"text\":\"机器人通知\"}")) is null, "事件用户不提醒");
Check(filter.Parse(Event("bot", "other", "text", "not even valid body JSON")) is null, "非选定群不解析正文");
var parsed = filter.Parse(Event("bot", "chosen", "interactive", "{\"header\":{\"title\":{\"tag\":\"plain_text\",\"content\":\"演示标题\"}},\"elements\":[{\"tag\":\"markdown\",\"content\":\"演示卡片正文\"},{\"img_key\":\"secret-attachment-id\"}]}"));
Check(parsed is not null && parsed.Kind == SenderKind.Bot && parsed.Text.Contains("演示卡片正文") && !parsed.Text.Contains("secret-attachment-id") && parsed.Text.Contains("未读取"), "卡片文字与附件限制");
Check(parsed is not null && store.Add(parsed, "chosen", now.AddSeconds(2)) && !store.Add(parsed, "chosen", now.AddSeconds(2)), "事件重复不报警");
store.Start(now.AddSeconds(3)); Check(parsed is not null && !store.Add(parsed, "chosen", now.AddSeconds(4)), "恢复后历史事件不报警");
Console.WriteLine($"{checks} total checks passed; event fixtures are synthetic, not live Feishu evidence.");
var bounded = new MessageStore(1); bounded.Start(now);
for (var i=0;i<10;i++) bounded.Add(Message("bounded-"+i), "chosen", now.AddSeconds(2));
var refused=false;try { bounded.Add(Message("overflow"),"chosen",now.AddSeconds(2)); } catch(DedupCapacityException){refused=true;}
Check(refused,"去重满容量触发可恢复保护");
Check(bounded.Add(Message("after-expiry") with { SentAt=now.AddMinutes(31) },"chosen",now.AddMinutes(31)),"过期清理后可继续运行");
var restricted=new BotEventFilter(["chosen"],["other-bot"]); Check(restricted.Parse(Event("bot","chosen","text","{\"text\":\"模拟\"}")) is null,"机器人ID白名单");
Console.WriteLine($"{checks} final checks passed.");
