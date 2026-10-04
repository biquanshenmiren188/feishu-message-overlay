using System.Text.RegularExpressions;
namespace Overlay.Core;
// Only Weixin presentation uses this filter. Source cards and desktop content stay intact.
public static class WeixinDisplayFilter
{
    private const RegexOptions Options=RegexOptions.IgnoreCase|RegexOptions.CultureInvariant;
    private static readonly Regex Continued=new(@"^(?:持续\s+ACTIVE\s*满\s*\d+(?:\.\d+)?\s*(?:分钟|秒|小时)|(?:continuous|continued)\s+ACTIVE\s+(?:for\s+)?\d+(?:\.\d+)?\s*(?:minutes?|seconds?|hours?))\s*(?:[|｜]\s*(?:补充推送|supplement(?:al)?\s+(?:push|notification)))?\s*$",Options);
    private static readonly Regex ActiveClock=new(@"^ACTIVE\s+(?:\d{2,4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2})\s+\d{1,2}:\d{2}(?::\d{2})?\s*[|｜]\s*(?:截至|until|as\s+of)\s+.*\d{1,2}:\d{2}.*$",Options);
    private static readonly Regex Counts=new(@"^\d+\s*(?:秒|seconds?|s)\s*[:：]\s*(?:有效|valid)\s*\d+\s*/\s*\d+\s*[|｜]\s*(?:达标|qualified|passed)\s*\d+\s*/\s*\d+\s*[|｜]\s*(?:最长|longest)\s*(?:未知|unknown|\d).*?$",Options);
    private static readonly Regex Funding=new(@"^[^:：|｜]{1,40}[:：]\s*(?:资费|资金费率|funding(?:\s+rate)?)\s*[:：]?\s*[+−\-]?\d+(?:\.\d+)?%.*(?:24h\s*(?:成交额|volume)|\bOI\s*[\d.+−\-]).*$",Options);
    private static readonly Regex StandaloneFunding=new(@"^(?:资金费|资费|资金费率|funding(?:\s+rate)?)\s*[:：]\s*(?:[^:：|｜%]{1,40}\s+)?[+−\-]?\d+(?:\.\d+)?%\s*/\s*\d+\s*(?:h|小时)\s*$",Options);
    private static readonly Regex RoundCounts=new(@"^本轮发现\s*[:：]\s*\d+\s*个机会\s*[,，|｜]\s*输出/推送\s*[:：]\s*\d+\s*个\s*$",Options);
    private static readonly Regex DepositHeader=new(@"^(?:现货充提|spot\s+(?:deposit|deposits)\s*[/&-]\s*(?:withdrawal|withdrawals))\s*[（(]\s*Cexorer\s*[）)]\s*(?:[|｜]\s*(?:查询|queried|query).*)?$",Options);
    private static readonly Regex DepositDetail=new(@"^[^:：|｜]{1,40}[:：]\s*(?:(?:充(?:开|关)|充值(?:开启|关闭|开|关)|deposit\s*(?:open|closed|enabled|disabled))\s*[/|｜]\s*(?:提(?:开|关)|提现(?:开启|关闭|开|关)|withdraw(?:al)?\s*(?:open|closed|enabled|disabled))(?:\s+[^\r\n]*)?|未覆盖|not\s+covered|unsupported)\s*$",Options);
    public static IReadOnlyList<string> Lines(string body)
    {
        var result=new List<string>();var depositSection=false;
        foreach(var raw in body.Replace("\r\n","\n").Replace('\r','\n').Split('\n')){
            var line=raw.Trim();
            // Preserve links, unknown paragraphs and all risk/revenue commentary by default.
            if(line.Contains("http://",StringComparison.OrdinalIgnoreCase)||line.Contains("https://",StringComparison.OrdinalIgnoreCase)||Regex.IsMatch(line,@"风险|净收益|盘口差|指数差|\brisk\b|\bwarning\b",Options)){result.Add(raw);depositSection=false;continue;}
            if(Continued.IsMatch(line)||ActiveClock.IsMatch(line)||Counts.IsMatch(line)||Funding.IsMatch(line)||StandaloneFunding.IsMatch(line)||RoundCounts.IsMatch(line))continue;
            if(DepositHeader.IsMatch(line)){depositSection=true;continue;}
            if(depositSection&&DepositDetail.IsMatch(line))continue;
            result.Add(raw);if(line.Length>0)depositSection=false;
        }
        return result;
    }
}
