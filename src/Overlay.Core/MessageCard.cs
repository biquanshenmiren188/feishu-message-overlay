using System.Text.Json;
namespace Overlay.Core;

public sealed record CardLink(string Label,string Url);
public sealed record MessageCard(string Title,string Body,IReadOnlyList<CardLink> Buttons,string HeaderTone="grey",bool IsMarkdown=false)
{
    public static string SafeTone(string? tone)=>tone is "blue" or "red" or "green" or "orange" or "purple" or "indigo" or "turquoise" or "yellow"?tone:"grey";
    public string Notice=>"卡片仅展示接口提供的文字和HTTP(S)链接；图片及交互控件不在此执行。";
}
public static class MessageCardParser
{
    private static string String(JsonElement node,string key)=>node.ValueKind==JsonValueKind.Object && node.TryGetProperty(key,out var value) && value.ValueKind==JsonValueKind.String?value.GetString()??"":"";
    private static string Text(JsonElement node)
    {
        if(node.ValueKind==JsonValueKind.String)return node.GetString()??"";
        return String(node,"text") is {Length:>0} text?text:String(node,"content");
    }
    public static bool SafeUrl(string value)=>value.Length<=4096 && Uri.TryCreate(value,UriKind.Absolute,out var uri) && uri.Scheme is "http" or "https" && string.IsNullOrEmpty(uri.UserInfo);
    private static string Target(JsonElement node)
    {
        if(node.ValueKind==JsonValueKind.String){var value=node.GetString()??"";return SafeUrl(value)?value:"";}
        if(node.ValueKind!=JsonValueKind.Object)return "";
        foreach(var key in new[]{"pc_url","url","default_url","href"}){var value=String(node,key);if(SafeUrl(value))return value;}
        return "";
    }
    private static string ButtonTarget(JsonElement node)
    {
        foreach(var key in new[]{"url","href","multi_url","open_url"})if(node.TryGetProperty(key,out var value) && Target(value) is {Length:>0} result)return result;
        var direct=String(node,"default_url");if(SafeUrl(direct))return direct;
        if(node.TryGetProperty("behaviors",out var actions) && actions.ValueKind==JsonValueKind.Array)
            foreach(var action in actions.EnumerateArray().Take(8))if(String(action,"type")=="open_url" && Target(action) is {Length:>0} result)return result;
        if(node.TryGetProperty("action",out var single) && String(single,"type")=="open_url")return Target(single);
        return "";
    }
    public static MessageCard? Parse(string json)
    {
        if(json.Length>524288)return null;
        try
        {
            using var document=JsonDocument.Parse(json,new JsonDocumentOptions{MaxDepth=32});var root=document.RootElement;
            var title=String(root,"title");var tone="grey";
            if(root.TryGetProperty("header",out var header))
            {if(title.Length==0 && header.TryGetProperty("title",out var heading))title=Text(heading);var template=String(header,"template");if(template.Length>0)tone=template;}
            var lines=new List<string>();var buttons=new List<CardLink>();var budget=16000;var visited=0;var markdown=false;
            void Add(string text){if(string.IsNullOrWhiteSpace(text)||budget<=0)return;var bounded=text[..Math.Min(text.Length,budget)];lines.Add(bounded);budget-=bounded.Length;}
            void Visit(JsonElement node)
            {
                if(++visited>2048 || budget<=0)return;
                if(node.ValueKind==JsonValueKind.Array){foreach(var child in node.EnumerateArray())Visit(child);return;}
                if(node.ValueKind!=JsonValueKind.Object)return;
                var tag=String(node,"tag");
                if(tag=="button")
                {
                    var label=node.TryGetProperty("text",out var caption)?Text(caption):String(node,"content");
                    var url=ButtonTarget(node);
                    if(buttons.Count<8 && label.Length>0)buttons.Add(new(label[..Math.Min(label.Length,128)],SafeUrl(url)?url:""));
                    return;
                }
                if(tag=="a")
                {
                    Add(Text(node));var href=String(node,"href");if(SafeUrl(href))Add(href);return;
                }
                if(tag is "text" or "plain_text" or "lark_md" or "markdown"){if(tag is "lark_md" or "markdown")markdown=true;Add(Text(node));return;}
                // Only documented content containers, never arbitrary nested data/value fields.
                foreach(var field in node.EnumerateObject())
                    if(field.Name is "elements" or "content" or "text" or "fields" or "actions" or "body" or "columns")
                    {if(field.Value.ValueKind==JsonValueKind.String)Add(field.Value.GetString()??"");else Visit(field.Value);}
            }
            if(root.TryGetProperty("elements",out var elements))Visit(elements);
            else if(root.TryGetProperty("body",out var body))Visit(body);
            if(title.Length==0 && lines.Count==0 && buttons.Count==0)return null;
            if(budget<=0)lines.Add("[内容超过本地显示上限]");
            return new(title[..Math.Min(title.Length,512)],string.Join('\n',lines),buttons.ToArray(),tone,markdown);
        }
        catch(Exception error) when(error is JsonException or InvalidOperationException){return null;}
    }
}
