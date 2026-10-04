using System.Text;
using System.Text.RegularExpressions;
namespace Overlay.Core;
// Formatting is pure: no file access, network, link shortening or URL navigation.
public static partial class WeixinText
{
    [GeneratedRegex(@"\[[^\]\r\n]*\]\(<https?://[^<>\r\n]+>\)|https?://[^\s<>]+",RegexOptions.IgnoreCase)]
    private static partial Regex UrlUnits();
    private static string Escape(string value)=>value.Replace("\\","\\\\").Replace("*","\\*").Replace("[","\\[").Replace("]","\\]");
    private static string One(IncomingMessage message)
    {
        var title=message.Card?.Title??"";var body=message.Card?.Body??message.Text;
        var buttons=message.Card?.Buttons??Array.Empty<CardLink>();
        var kept=buttons.Where(b=>!b.Label.Trim().StartsWith("查看雷达",StringComparison.Ordinal)&&MessageCardParser.SafeUrl(b.Url)).DistinctBy(b=>b.Url,StringComparer.Ordinal).ToArray();
        var allUrls=buttons.Where(b=>MessageCardParser.SafeUrl(b.Url)).Select(b=>b.Url).Distinct(StringComparer.Ordinal).ToArray();
        var paragraphs=new List<string>{message.SentAt.ToOffset(TimeSpan.FromHours(8)).ToString("yyyy-MM-dd HH:mm:ss")+" UTC+8"};
        if(title.Length>0)paragraphs.Add("**"+Escape(title)+"**");
        foreach(var line in WeixinDisplayFilter.Lines(body)){
            var trimmed=line.Trim();if(trimmed.Length==0)continue;
            if(allUrls.Contains(trimmed,StringComparer.Ordinal))continue;
            if(buttons.Any(b=>trimmed==b.Label+"："+b.Url||trimmed==b.Label+":"+b.Url||trimmed=="["+b.Label+"]("+b.Url+")"||trimmed=="["+b.Label+"](<"+b.Url+">)"))continue;
            if(trimmed.StartsWith("查看雷达",StringComparison.Ordinal)&&trimmed.TrimEnd(':','：',' ').Equals("查看雷达",StringComparison.Ordinal))continue;
            if(kept.Any(b=>trimmed.TrimEnd(':','：',' ').Equals(b.Label.Trim(),StringComparison.Ordinal)))continue;
            paragraphs.Add(line.TrimEnd());
        }
        foreach(var button in kept){
            if(button.Url.Length>3700||button.Url.IndexOfAny(['<','>','\r','\n'])>=0){paragraphs.Add("[完整链接超过微信单条限制或含不支持字符，未拆坏链接；请在电脑小窗打开。]");continue;}
            paragraphs.Add("["+Escape(button.Label)+"](<"+button.Url+">)");
        }
        // ClawBot renders soft line breaks as spaces. Blank paragraphs keep the supplied logical sections distinct.
        return string.Join("\n\n",paragraphs);
    }
    public static string Compose(IncomingMessage message,IncomingMessage? pinned=null,bool isPinnedUpdate=false)
    {
        if(isPinnedUpdate)return "【置顶群最新一条】\n\n"+One(message);
        if(pinned is null||pinned.Id==message.Id&&pinned.SourceId==message.SourceId)return One(message);
        return "【置顶群最新一条】\n\n"+One(pinned)+"\n\n────────\n\n【本次新消息】\n\n"+One(message);
    }
    public static IReadOnlyList<string> Parts(string text)
    {
        const int limit=3800;var result=new List<string>();var current=new StringBuilder();
        void Add(string unit){if(unit.Length==0)return;if(unit.Length>limit)throw new ArgumentException("Unsplit link exceeds Weixin limit");if(current.Length>0&&current.Length+2+unit.Length>limit){result.Add(current.ToString());current.Clear();}if(current.Length>0)current.Append("\n\n");current.Append(unit);}
        void Plain(string value){for(var offset=0;offset<value.Length;){var length=Math.Min(limit,value.Length-offset);if(offset+length<value.Length&&char.IsHighSurrogate(value[offset+length-1]))length--;Add(value.Substring(offset,length));offset+=length;}}
        foreach(var paragraph in text.Split("\n\n",StringSplitOptions.RemoveEmptyEntries)){
            if(paragraph.Length<=limit){Add(paragraph);continue;}
            var offset=0;foreach(Match match in UrlUnits().Matches(paragraph)){Plain(paragraph[offset..match.Index]);Add(match.Value);offset=match.Index+match.Length;}Plain(paragraph[offset..]);
        }
        if(current.Length>0)result.Add(current.ToString());
        if(result.Count>1)for(var i=0;i<result.Count;i++)result[i]=$"[分段 {i+1}/{result.Count}]\n\n"+result[i];
        return result;
    }
}
