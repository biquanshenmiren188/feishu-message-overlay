using System.Text.Json;
using Overlay.Core;
internal static class CompactSummaryTests
{
    public static void Run(Action<bool,string> check)
    {
        var netValues=new[]{"+0.1234%","-0.0200%","0.0000%","−0.0300%","+0.1400%","+0.2500%"};
        var strongBody="最近180秒净收益均值最高 +9.99%\n"+string.Join("\n",netValues.Select((value,index)=>$"R{index}｜FF｜买 ASTER → 卖 BINANCE\nV2收敛 · 180秒 · 净均 {value} · ACTIVE 7s"));
        var strong=CompactMessage.From("强信号聚集｜TOKEN｜6 组同时 ACTIVE",strongBody);
        check(strong.Title=="强信号｜TOKEN｜6组","strong V2 summary title");
        check(strong.Signals==string.Join("\n",netValues.Select((value,index)=>$"R{index}｜FF｜AS→BN｜{value}")),"strong V2 per-route net means preserve sign and precision");
        foreach(var detail in new[]{"V3收敛 · 180秒 · 净均 +9.99%","V2收敛 · 181秒 · 净均 +9.99%","其他说明 · 净均 +9.99%","V2收敛 · 180秒 · 净均 未知","V2收敛 · 180秒 · 盘口差 +9.99%"})
            check(CompactMessage.From("强信号聚集｜TOKEN｜2 组同时 ACTIVE",$"最高净均 +9.99%\nR1｜SF｜买 GATE → 卖 BITGET\n{detail}\n净均 +8.88%\nR2｜FF｜买 ASTER → 卖 BINANCE\nV2收敛 · 180秒 · 净均 -0.12% · ACTIVE 7s").Signals=="R1｜SF｜GT→BG\nR2｜FF｜AS→BN｜-0.12%","strong V2 rejects unrelated details without borrowing another route");
        check(CompactMessage.From("强信号｜TOKEN","R6+｜FF｜买 OKX → 卖 BINANCE 净均 -0.12%\nV2收敛 · 180秒 · 净均 +9.99%\nR1｜SF｜买 GATE → 卖 BITGET\nV2收敛\t·\t180秒\t·\t净均\t+0.0010% · ACTIVE 7s").Signals=="R6+｜FF｜OK→BN｜-0.12%\nR1｜SF｜GT→BG｜+0.0010%","strong V2 inline priority and horizontal whitespace");
        const string observation="CTUSDT / USDT-FUTURES | 5分钟 close持续突降 | -3.4321 个百分点 | 档位 跌幅>=0.10 个百分点 | close 0.0000% -> -3.4321%";
        var repeated="1. "+observation+"\n2. "+observation.Replace(">=0.10",">=0.20")+"\n3. "+observation;
        var one=CompactMessage.From("BG 溢价指数突变提醒","1. "+observation).Signals;
        check(CompactMessage.From("BG 溢价指数突变提醒",repeated).Signals==one,"premium repeated tiers collapse to one observation");
        foreach(var distinct in new[]{observation.Replace("-3.4321%","-3.4322%"),observation.Replace("CTUSDT","BTCUSDT"),observation.Replace("USDT-FUTURES","COIN-FUTURES")})
            check(CompactMessage.From("BG 溢价指数突变提醒",repeated+"\n4. "+distinct).Signals==one+"\n"+CompactMessage.From("BG 溢价指数突变提醒","1. "+distinct).Signals,"premium preserves distinct observation "+distinct);
        check(CompactMessage.From("BG 溢价指数突变提醒",repeated).Signals==one,"premium dedup does not suppress later messages");
        check(one=="CTUSDT 溢价指数 0% → -3.4321%","premium uses requested one-line format");
        check(CompactMessage.From("BG 溢价指数突变提醒",repeated+"\n4. "+observation.Replace("5分钟","1分钟")).Signals==one,"same index transition across windows appears once");
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
