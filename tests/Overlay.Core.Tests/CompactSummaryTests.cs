using System.Text.Json;
using Overlay.Core;
internal static class CompactSummaryTests
{
    public static void Run(Action<bool,string> check)
    {
        const string observation="CTUSDT / USDT-FUTURES | 5分钟 close持续突降 | -3.4321 个百分点 | 档位 跌幅>=0.10 个百分点 | close 0.0000% -> -3.4321%";
        var repeated="1. "+observation+"\n2. "+observation.Replace(">=0.10",">=0.20")+"\n3. "+observation;
        var one=CompactMessage.From("BG 溢价指数突变提醒","1. "+observation).Signals;
        check(CompactMessage.From("BG 溢价指数突变提醒",repeated).Signals==one,"premium repeated tiers collapse to one observation");
        foreach(var distinct in new[]{observation.Replace("5分钟","1分钟"),observation.Replace("-3.4321%","-3.4322%"),observation.Replace("CTUSDT","BTCUSDT"),observation.Replace("USDT-FUTURES","COIN-FUTURES"),observation.Replace("-3.4321 个百分点","-1.0669 个百分点")})
            check(CompactMessage.From("BG 溢价指数突变提醒",repeated+"\n4. "+distinct).Signals==one+"\n"+CompactMessage.From("BG 溢价指数突变提醒","1. "+distinct).Signals,"premium preserves distinct observation "+distinct);
        check(CompactMessage.From("BG 溢价指数突变提醒",repeated).Signals==one,"premium dedup does not suppress later messages");
        using var document=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"summary-fixtures.json")));
        foreach(var fixture in document.RootElement.EnumerateArray())
        {
            var input=fixture.GetProperty("input");var expected=fixture.GetProperty("expected");
            var actual=CompactMessage.From(input.TryGetProperty("title",out var title)?title.GetString():null,input.GetProperty("body").GetString());
            foreach(var (key,value) in new[]{("title",actual.Title),("signals",actual.Signals),("spread",actual.Spread),("risk",actual.Risk)})
                check(value==expected.GetProperty(key).GetString(),"web/desktop summary parity "+fixture.GetProperty("name").GetString()+" / "+key);
            check(actual.Warning==expected.GetProperty("warning").GetBoolean(),"web/desktop warning parity");
        }
    }
}
