using System.Text.RegularExpressions;
namespace Overlay.Core;

// Strictly scoped to the Binance/Aster topic envelope. Never infer a direction
// from a percentage, or substitute the window average for the current quote.
public static class TopicSpreadMessage
{
    private static Match Match(string text,string pattern)=>Regex.Match(text,pattern,RegexOptions.IgnoreCase|RegexOptions.CultureInvariant,TimeSpan.FromMilliseconds(100));
    public static bool IsTopic(string? title,string body)=>Match((title??"")+"\n"+body,@"(?m)^\s*\[Binance\s*/\s*Aster\s+专题价差\]").Success;
    public static CompactSummary? Summary(string? title,string body)
    {
        if(!IsTopic(title,body))return null;
        var lines=body.Split('\n').Select(x=>x.Trim()).ToArray();
        var entries=new List<(string Title,string Value)>();
        for(var i=0;i<lines.Length;i++)
        {
            var route=Match(lines[i],@"^\d+[.、)]\s*([^\s|｜]+)\s*[|｜]\s*多\s+(Binance|Aster)\s*[/／]\s*空\s+(Binance|Aster)\s*$");
            if(!route.Success||route.Groups[2].Value.Equals(route.Groups[3].Value,StringComparison.OrdinalIgnoreCase))continue;
            var block=string.Join("\n",lines.Skip(i+1).TakeWhile(x=>!Match(x,@"^\d+[.、)]").Success));
            var current=Match(block,@"(?m)^当前\s*take\s*[:：]\s*([+−-]?\d+(?:\.\d+)?%)\s*$");
            var duration=Match(block,@"已持续\s*((?:\d+\s*(?:天|小时|分钟|分|秒))+)");
            string Venue(string v)=>v.Equals("Binance",StringComparison.OrdinalIgnoreCase)?"BN":"AS";
            entries.Add(($"{route.Groups[1].Value}｜FF｜{Venue(route.Groups[2].Value)} → {Venue(route.Groups[3].Value)}",
                "当前价差 "+(current.Success?current.Groups[1].Value:"—")+" · 持续 "+(duration.Success?duration.Groups[1].Value:"—")));
        }
        if(entries.Count==0)return null;
        return entries.Count==1?new(entries[0].Title,"",entries[0].Value,"",false)
            :new($"Binance/Aster 专题价差｜{entries.Count}组",string.Join("\n",entries.Select(e=>e.Title+"\n"+e.Value)),"","",false);
    }
    public static IReadOnlyList<CardLink> Links(string body)
    {
        var links=new List<CardLink>();
        foreach(var line in body.Split('\n'))
        {
            var m=Match(line.Trim(),@"^查看详情\s*[:：]\s*(https?://\S+)\s*$");
            if(m.Success&&MessageCardParser.SafeUrl(m.Groups[1].Value)&&!links.Any(x=>x.Url==m.Groups[1].Value))
                links.Add(new("查看详情",m.Groups[1].Value));
        }
        return links.Take(8).ToArray();
    }
}
