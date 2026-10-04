using System.Text.Json;
namespace Overlay.Core;

// Pure parsing only; no credentials, network transport, cloud writes, or real connection.
// Event sender_type uses "bot"; a history API adapter must separately normalize its schema.
public sealed class BotEventFilter(IEnumerable<string> selectedChatIds, IEnumerable<string>? selectedBotIds = null)
{
    private readonly HashSet<string> selected = new(selectedChatIds, StringComparer.Ordinal);
    private readonly HashSet<string> bots = new(selectedBotIds ?? [], StringComparer.Ordinal);
    public IncomingMessage? Parse(string eventJson)
    {
        if (eventJson.Length > 1_048_576) return null;
        try
        {
            using var document = JsonDocument.Parse(eventJson, new JsonDocumentOptions { MaxDepth = 48 });
            var root = document.RootElement;
            if (Get(root.GetProperty("header"), "event_type") != "im.message.receive_v1") return null;
            var body = root.GetProperty("event"); var sender = body.GetProperty("sender");
            if (Get(sender, "sender_type") != "bot") return null;
            var message = body.GetProperty("message"); var chatId = Get(message, "chat_id");
            // Verify group and sender metadata before extracting the content string.
            if (!selected.Contains(chatId) || Get(message, "chat_type") != "group") return null;
            var id = Get(message, "message_id");
            var senderId = Get(sender.GetProperty("sender_id"), "open_id");
            if (string.IsNullOrWhiteSpace(id) || string.IsNullOrWhiteSpace(senderId)) return null;
            if (bots.Count > 0 && !bots.Contains(senderId)) return null;
            if (!long.TryParse(Get(message, "create_time"), out var milliseconds)) return null;
            var time = DateTimeOffset.FromUnixTimeMilliseconds(milliseconds);
            var type=Get(message,"message_type");
            var content=Get(message,"content");
            var card=type=="interactive"?MessageCardParser.Parse(content):null;
            var text=card is null?Extract(type,content):string.Join('\n',new[]{card.Title,card.Body,string.Join('\n',card.Buttons.Select(b=>b.Label+(b.Url.Length>0?" "+b.Url:"")))}.Where(s=>s.Length>0));
            return new(id, chatId, "机器人 · " + senderId, text, time, SenderKind.Bot, senderId,type,card);
        }
        catch (Exception ex) when (ex is JsonException or KeyNotFoundException or InvalidOperationException or ArgumentOutOfRangeException) { return null; }
    }
    private static string Get(JsonElement value, string property) => value.TryGetProperty(property, out var result) && result.ValueKind == JsonValueKind.String ? result.GetString() ?? "" : "";
    private static string Extract(string type, string content)
    {
        if (type is not ("text" or "post" or "interactive")) return "[此消息类型的正文尚不支持；未读取附件]";
        try
        {
            using var document = JsonDocument.Parse(content, new JsonDocumentOptions { MaxDepth = 32 });
            if (type == "text") return Get(document.RootElement, "text");
            var lines = new List<string>(); var length = 0;
            void Visit(JsonElement node)
            {
                if (length >= 16000) return;
                if (node.ValueKind == JsonValueKind.Array) { foreach (var item in node.EnumerateArray()) Visit(item); return; }
                if (node.ValueKind != JsonValueKind.Object) return;
                foreach (var field in node.EnumerateObject())
                {
                    if (field.Value.ValueKind is JsonValueKind.Object or JsonValueKind.Array) Visit(field.Value);
                    else if (field.Value.ValueKind == JsonValueKind.String && field.Name is "text" or "content" or "title")
                    {
                        var value = field.Value.GetString() ?? "";
                        if (string.IsNullOrWhiteSpace(value)) continue;
                        var remaining = 16000 - length; var part = value.Length <= remaining ? value : value[..remaining];
                        lines.Add(part); length += part.Length;
                    }
                }
            }
            Visit(document.RootElement);
            var result = string.Join("\n", lines);
            if (length >= 16000) result += "\n[本软件已限制显示长度]";
            return string.IsNullOrWhiteSpace(result) ? "[接口未提供可读文字]" : result;
        }
        catch (JsonException) { return "[正文格式无法解析；未读取附件]"; }
    }
}
