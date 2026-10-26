using System.Globalization;
using System.Text.RegularExpressions;
namespace Overlay.Core;

public sealed record CompactSummary(string Title,string Signals,string Spread,string Risk,bool Warning)
{
    public string Body=>string.Join("\n",new[]{Spread,Signals,Warning?Risk:""}.Where(x=>x.Length>0));
}

// Presentation only; keep IncomingMessage and its action URLs unchanged.
// Parity fixtures are generated from the website summary tests.
public static class CompactMessage
{
    private static Match Match(string text,string pattern)=>Regex.Match(text,pattern,RegexOptions.IgnoreCase|RegexOptions.CultureInvariant,TimeSpan.FromMilliseconds(100));
    private static bool Has(string text,string pattern)=>Match(text,pattern).Success;
    private static string Replace(string text,string pattern,string replacement)=>Regex.Replace(text,pattern,replacement,RegexOptions.IgnoreCase|RegexOptions.CultureInvariant,TimeSpan.FromMilliseconds(100));
    private static string Abbreviation(string name)=>name.ToLowerInvariant() switch {"gate" or "gate.io"=>"GT","binance"=>"BN","bitget"=>"BG","bybit"=>"BY","okx"=>"OK","aster"=>"AS","hyperliquid" or "hl" or "hy"=>"HY",_=>name};
    private static string Short(string text)=>Regex.Replace(text,@"\b(?:gate\.io|gate|binance|bitget|bybit|okx|aster|hyperliquid|hl|hy)\b",m=>Abbreviation(m.Value),RegexOptions.IgnoreCase|RegexOptions.CultureInvariant,TimeSpan.FromMilliseconds(100));
    private static string Find(IEnumerable<string> lines,string pattern,int group=1)=>lines.Select(s=>Match(s,pattern)).FirstOrDefault(m=>m.Success)?.Groups[group].Value??"";
    private sealed record Dex(int Index,string Rank,string Mode,string Coin,string Route);
    public static CompactSummary From(string? originalTitle,string? body)
    {
        if(TopicSpreadMessage.Summary(originalTitle,body??"") is {} topic)return topic;
        var lines=Regex.Split(body??"",@"\r\n|\r|\n").Select(s=>s.Trim()).Where(s=>s.Length>0).ToArray();
        var direction=lines.FirstOrDefault(s=>Has(s,@"^(买|买入|做多).*(→|->|卖|做空)"))??"";
        var route=Match(direction,@"^(?:买入|买|做多)\s+(\S+).*?(?:→|➡️?|->)\s*(?:卖出|卖|做空)\s+(\S+)");
        var title=originalTitle??"";
        if(route.Success)title=Replace(title,@"V2\s*收敛",Abbreviation(route.Groups[1].Value)+"→"+Abbreviation(route.Groups[2].Value));
        var signals=new List<string>();var dex=new List<Dex>();var dexSpread="";
        for(var i=0;i<lines.Length;i++)
        {
            var m=Match(lines[i],@"^\d+[.、)]\s*\[(P\d+\+?)\]\s*\[(期期|现期|期现|FF|SF|FS)\]\s*([^\s|｜]+)\s*[|｜]\s*多\s+(\S+)(?:\s+(?:现货|合约|永续))?\s*[/／]\s*(?:空|借卖)\s+(\S+)(?:\s+(?:现货|合约|永续))?\s*$");
            if(m.Success)dex.Add(new(i,m.Groups[1].Value.ToUpperInvariant(),m.Groups[2].Value switch {"期期"=>"FF","现期"=>"SF","期现"=>"FS",var mode=>mode.ToUpperInvariant()},m.Groups[3].Value,Abbreviation(m.Groups[4].Value)+"→"+Abbreviation(m.Groups[5].Value)));
        }
        if(dex.Count>0)
        {
            var first=dex[0];title=dex.Count==1?$"{first.Coin}｜{first.Mode}｜{first.Route}｜{first.Rank}":$"DEX套利｜{string.Join("、",dex.Select(x=>x.Coin).Distinct())}｜{dex.Count}组";
            for(var i=0;i<dex.Count;i++)
            {
                // Stop at every numbered entry, including unsupported routes.
                var entry=dex[i];var block=lines.Skip(entry.Index+1).TakeWhile(line=>!Has(line,@"^\d+[.、)]")).ToArray();
                var observed=Find(block,@"^take\s*[:：]\s*([+−-]?\d+(?:\.\d+)?\s*%)\s*/\s*[+−-]?\d+(?:\.\d+)?\s*%");
                if(observed.Length==0)observed=Find(block,@"(?:^|[｜|])\s*盘口差\s*[:：]?\s*([+−-]?\d+(?:\.\d+)?\s*%)");
                var spread=observed.Length>0?"盘口差 "+(Has(observed,@"^[+−-]")?"":"+")+Replace(observed,@"\s",""):"";
                if(dex.Count==1&&spread.Length>0){dexSpread=spread;continue;}
                var details=new[]{dex.Count>1?$"{entry.Coin}｜{entry.Mode}｜{entry.Route}｜{entry.Rank}":"",dex.Count>1?spread:""}.Where(s=>s.Length>0);
                var text=string.Join(" · ",details);if(text.Length>0)signals.Add(text);
            }
        }
        else if(string.IsNullOrWhiteSpace(title)||title.Trim()=="机器人消息")title=lines.FirstOrDefault(s=>!Has(s,@"^https?://")&&!Has(s,@"^(?:时间|阈值|价格最大延迟|symbol黑名单|排除合约交易所)\s*[:：]"))??"";
        if(title.Contains("强信号"))
        {
            for(var i=0;i<lines.Length;i++)
            {
                var m=Match(lines[i],@"^(R\d+\+?)\s*[｜|]\s*(SF|FS|FF)\s*[｜|]\s*买\s+(\S+)\s*→\s*卖\s+(\S+)");if(!m.Success)continue;
                var next=i+1<lines.Length?lines[i+1]:"";var value=Match(lines[i],@"净均\s*([+−-]?\d+(?:\.\d+)?%)");
                // Known detail line only: no headline maximum or another route.
                if(!value.Success)value=Match(next,@"^(?:V2收敛[ \t]*·[ \t]*180秒[ \t]*·[ \t]*)?净均[ \t]*([+−-]?\d+(?:\.\d+)?%)");
                signals.Add($"{m.Groups[1]}｜{m.Groups[2]}｜{Abbreviation(m.Groups[3].Value)}→{Abbreviation(m.Groups[4].Value)}"+(value.Success?"｜"+value.Groups[1].Value:""));
            }
            if(signals.Count>0){var count=Match(title,@"(\d+)\s*组");title=string.Join("｜",Regex.Split(Replace(title,@"^(?:🚨|\s)+","").Replace("强信号聚集","强信号"),@"[｜|]").Take(2).Select(s=>s.Trim()))+"｜"+(count.Success?count.Groups[1].Value:signals.Count.ToString(CultureInfo.InvariantCulture))+"组";}
        }
        title=Short(title);
        var premiumEntries=new HashSet<string>(StringComparer.Ordinal);
        if(title.Contains("溢价指数突变"))foreach(var line in lines)
        {
            var m=Match(line,@"^\d+[.、)]\s*(?:(?:🟢|🔴|🟣|🟡|↑|↓)\s*)*([A-Z0-9][A-Z0-9._/-]*)\s*/\s*([^|｜]+)[|｜]\s*(.+)$");if(!m.Success)continue;
            var parts=Regex.Split(m.Groups[3].Value,@"[|｜]").Select(s=>s.Trim()).ToArray();var change=Find(parts,@"^([+−-]?\d+(?:\.\d+)?)\s*个百分点$");
            var window=Match(parts[0],@"\d+\s*(?:分钟|小时|秒)").Value;var values=parts.Select(s=>Match(s,@"^close\s+([+−-]?\d+(?:\.\d+)?%)\s*(?:->|→)\s*([+−-]?\d+(?:\.\d+)?%)$")).FirstOrDefault(x=>x.Success);
            var move=parts[0];if(change.Length>0){var number=double.Parse(change.Replace('−','-'),CultureInfo.InvariantCulture);move=window+(number<0?"下跌":number>0?"上涨":"持平")+" "+Replace(change,@"^[+−-]","")+" 个百分点";}
            var summary=values is not null
                ? m.Groups[1].Value+" 溢价指数 "+Replace(values.Groups[1].Value,@"^[+−-]?0(?:\.0+)?%$","0%")+" → "+Replace(values.Groups[2].Value,@"^[+−-]?0(?:\.0+)?%$","0%")
                : m.Groups[1].Value+" · "+move;
            // Collapse identical visible index transitions; keep distinct values and markets.
            if(premiumEntries.Add(m.Groups[2].Value.Trim()+"\n"+summary))signals.Add(summary);
        }
        const string placeholder=@"^(?:(?:无|没有|暂无)(?:数据|信息|风险|警告|警示|提醒)?|未知|未提供|不适用|无数据|未核验|待核验|不确定|[-—/|·.,，。:：;；\s])+$";
        const string warningLabel=@"^(?:[⚠\uFE0F\s]*(?:警告|警示|注意|风险提示|风险|提醒)\s*[:：]?\s*|[⚠\uFE0F\s]+)";
        var warnings=new List<string>();var labelledWarning=false;
        for(var i=0;i<lines.Length;i++)
        {
            var line=lines[i];if(Has(line,@"^价格最大延迟\s*[:：]\s*\d+(?:\.\d+)?\s*(?:s|秒)\s*$"))continue;
            var labelled=Has(line,warningLabel);var detail=Replace(Replace(line,warningLabel,""),@"官方原文\s*[:：].*$","").Trim();
            if(detail.Length==0||Has(detail,placeholder))continue;
            if(!labelled&&!Has(detail,@"下架|退市|停止交易|终止|暂停|维护|充关|提关|充值关闭|提现关闭|关闭|延迟|失败|异常|过期|禁止|不支持|不可用|不保证|勿|谨慎"))continue;
            if(Has(line,@"^[⚠\uFE0F\s]*(?:警告|警示)"))labelledWarning=true;
            var next=i+1<lines.Length?lines[i+1]:"";
            if(Has(detail,@"\d{1,2}[/-]\d{1,2}$")&&Has(next,@"^\d{1,2}:\d{2}(?::\d{2})?\s*UTC\s*[+-]\d+(?::\d{2})?$"))detail+=" "+next;
            detail=Short(Replace(detail,@"【[^】]*】","").Trim());if(detail.Length>0&&!warnings.Contains(detail))warnings.Add(detail);
        }
        var transfers=lines.Where(s=>Has(s,@"充开|提开|充关|提关|充值|提现|充提")).ToArray();
        var states=transfers.SelectMany(s=>Regex.Matches(s,@"充开提开|充关提关|充开|提开|充关|提关|充值开放|提现开放|充值关闭|提现关闭").Select(m=>m.Value)).Distinct().ToArray();
        var incomplete=transfers.Any(s=>Has(s,@"未知|暂无|没有|无数据|未提供|无现货|未核验|待核验|不确定"));
        var risk=warnings.Count>0?(labelledWarning?"警告：":"注意：")+string.Join("；",warnings):states.Length>0&&!incomplete?"充提："+string.Join(" / ",states):"";
        var ordinarySpread=Find(lines,@"(盘口差\s*[:：]?\s*[+−-]?\d+(?:\.\d+)?\s*%)");
        return new(title,string.Join("\n",signals),dex.Count>0?dexSpread:Replace(ordinarySpread,@"^盘口差\s*[:：]?\s*","盘口差 "),risk,warnings.Count>0);
    }
}
