using Overlay.Core;
internal static class TopicSpreadTests
{
    public static void Run(Action<bool,string> check)
    {
        const string dex="1. [P3][期期] IRYS | 多 Binance / 空 Aster\ntake: 0.4685% / 0.50%\n质量: 样本少";
        check(!CompactMessage.From(null,dex).Body.Contains("质量"),"single DEX quality hidden");
        check(!CompactMessage.From(null,dex+"\n"+dex.Replace("1.","2.").Replace("Binance","Bitget")).Body.Contains("质量"),"multi DEX quality hidden");
        const string body="[Binance/Aster 专题价差] 1 个信号\n条件: 任一方向 take 价差 > 0.50% 持续 3 分钟\n1. IRYS | 多 Binance / 空 Aster\n当前 take: 0.9446%\n持续窗口 min/avg/max: 0.6557% / 0.7888% / 0.9645%\n(37 样本)\n一档可成交约: 145.55 U; 已持续 3分0秒\n查看详情: https://example.invalid/radar/?tab=FF&mode=FF&q=irys";
        var summary=CompactMessage.From(null,body);
        check(summary.Title=="IRYS｜FF｜BN → AS","topic title preserves coin, mode and direction");
        check(summary.Body=="当前价差 0.9446% · 持续 3分0秒","topic only shows current spread and actual duration");
        check(!summary.Body.Contains("0.7888")&&!summary.Body.Contains("145.55"),"window statistics remain out of summary");
        check(TopicSpreadMessage.Links(body).Single().Url.EndsWith("?tab=FF&mode=FF&q=irys"),"topic detail URL preserved");
        check(CompactMessage.From(null,body.Replace("多 Binance / 空 Aster","多 Aster / 空 Binance")).Title=="IRYS｜FF｜AS → BN","reverse route preserved");
        check(CompactMessage.From(null,body.Replace("当前 take: 0.9446%","")).Spread.StartsWith("当前价差 —"),"missing current does not use window average");
        check(CompactMessage.From(null,body.Replace("已持续 3分0秒","")).Spread.EndsWith("持续 —"),"missing actual duration does not use trigger duration");
        check(TopicSpreadMessage.Summary(null,body.Replace("[Binance/Aster 专题价差]","普通消息")) is null,"unrelated text not reclassified");
        check(TopicSpreadMessage.Summary(null,body.Replace("空 Aster","空 Binance")) is null,"same venue rejected");
        check(TopicSpreadMessage.Links("查看详情: javascript:alert(1)\n查看详情: https://user:pass@example.invalid/").Count==0,"unsafe detail URLs rejected");
        var multi=body+"\n2. SECOND | 多 Aster / 空 Binance\n当前 take: -0.10%\n已持续 4分1秒";
        check(CompactMessage.From(null,multi).Signals.Contains("SECOND｜FF｜AS → BN\n当前价差 -0.10% · 持续 4分1秒"),"multiple entries keep independent values");
    }
}
