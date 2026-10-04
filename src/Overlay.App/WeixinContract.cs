using System.IO;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using Overlay.Core;
namespace Overlay.App;
internal static class WeixinContract
{
    private sealed class Sink:HttpMessageHandler
    {
        internal int Calls;internal bool Correct;internal bool BusyFirst;
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request,CancellationToken cancellationToken)
        {
            var text=await request.Content!.ReadAsStringAsync(cancellationToken);using var doc=JsonDocument.Parse(text);
            Correct=doc.RootElement.GetProperty("id").GetString()=="synthetic-group:synthetic-id:0"&&doc.RootElement.GetProperty("text").GetString()!.Contains("https://example.invalid/path?a=1&b=2")&&!text.Contains("hidden-sender");var count=Interlocked.Increment(ref Calls);
            if(BusyFirst&&count==1)return new((HttpStatusCode)429);
            return new(HttpStatusCode.OK){Content=new StringContent("{\"sent\":true}")};
        }
    }
    internal static async Task RunAsync(string output)
    {
        var sink=new Sink();await using var service=new WeixinForwarder(sink,true);var now=DateTimeOffset.UtcNow;
        var card=new MessageCard("Synthetic title","Synthetic body",[new("Safe link","https://example.invalid/path?a=1&b=2"),new("Rejected","javascript:invalid")]);
        var message=new IncomingMessage("synthetic-id","synthetic-group","hidden-sender","synthetic",now,SenderKind.Bot,Card:card);
        service.QueueAccepted(message with{Kind=SenderKind.Person});service.QueueAccepted(message with{SentAt=now.AddMinutes(-3)});service.QueueAccepted(message with{SentAt=now.AddMinutes(2)});await Task.Delay(60);
        if(sink.Calls!=0)throw new InvalidOperationException("Person/stale/future forwarding filter");
        service.QueueAccepted(message);for(var i=0;i<100&&service.Sent==0;i++)await Task.Delay(10);
        if(sink.Calls!=1||service.Sent!=1||!sink.Correct||WeixinForwarder.Compose(message).Contains("javascript:"))throw new InvalidOperationException("Private bridge synthetic delivery");
        var disabledSink=new Sink();await using var disabled=new WeixinForwarder(disabledSink,false);disabled.QueueAccepted(message);await Task.Delay(60);if(disabledSink.Calls!=0)throw new InvalidOperationException("Disabled must not forward");
        var retrySink=new Sink{BusyFirst=true};await using var retry=new WeixinForwarder(retrySink,true);retry.QueueAccepted(message);for(var i=0;i<200&&retry.Sent==0;i++)await Task.Delay(10);if(retrySink.Calls!=2||retry.Sent!=1)throw new InvalidOperationException("Only unsent busy retry");
        const string url="http://example.invalid/radar/?combo=SF.%E9%BE%99.X&q=%E9%BE%99&tab=SF";
        var structured=message with {Card=new MessageCard("Synthetic heading","First logical section\nSecond logical section\n查看机会："+url+"\n查看雷达："+url,[new("查看机会",url),new("查看雷达",url),new("重复机会",url)])};
        var formatted=WeixinText.Compose(structured);
        if(formatted.Contains("查看雷达")||formatted.Split(url).Length!=2||!formatted.Contains("First logical section\n\nSecond logical section")||!formatted.Contains("[查看机会](<"+url+">)"))throw new InvalidOperationException("Paragraph/link dedup preserves encoded query");
        var pin=message with{Id="pin-id",SourceId="pinned-group",Card=new MessageCard("Synthetic pinned title","PIN BODY",[])};
        var combined=WeixinText.Compose(structured,pin);
        if(!combined.StartsWith("【置顶群最新一条】")||combined.IndexOf("PIN BODY",StringComparison.Ordinal)>combined.IndexOf("【本次新消息】",StringComparison.Ordinal))throw new InvalidOperationException("One pinned then current order");
        var pinOnly=WeixinText.Compose(pin,pin,true);if(pinOnly.Split("PIN BODY").Length!=2||pinOnly.Contains("【本次新消息】"))throw new InvalidOperationException("Pinned update must not duplicate itself");
        var longBody=new string('中',12000)+"\nEmoji 😀\n";var longText=WeixinText.Compose(structured with{Card=structured.Card! with{Body=longBody}});var parts=WeixinText.Parts(longText);
        if(parts.Count<3||parts.Any(p=>p.Length>4000)||string.Join("",parts).Count(c=>c=='中')!=12000||parts.Count(p=>p.Contains(url))!=1)throw new InvalidOperationException("Numbered lossless chunks and unsplit URL");
        var prefixBody=WeixinText.Compose(structured with{Card=structured.Card! with{Body="Keep different URL "+url+"2"}});if(!prefixBody.Contains(url+"2"))throw new InvalidOperationException("Do not strip URL prefixes from other content");
        var noise="持续 ACTIVE 满10分钟 | 补充推送\nACTIVE 10-01 20:14:12 | 截至 20:24:13（东八区）\n180秒：有效180/180 | 达标180/180 | 最长未知0秒\nExampleA：资费+0.005%/4h | 24h成交额21.11m USDT | OI2.13m USDT\n现货充提（Cexorer） | 查询 20:23:43（东八区）\nExampleA：充开/提开 BSC\nExampleB：未覆盖";
        var core="买 ExampleA 永续 → 卖 ExampleB 永续\n均值：净收益0.608% | 盘口差+0.951% | 指数差+0.093%\n盘口差P75：+1.053%\n未知说明保留\n风险：OI变化可能影响收益";
        foreach(var market in new[]{"FF","SF"}){
            var original=message with{Card=new MessageCard("Synthetic "+market,core+"\n"+noise,[new("查看机会",url),new("查看雷达",url)])};
            var clean=WeixinText.Compose(original,original with{Id="another-pin",SourceId="pinned-group"});
            if(clean.Contains("Cexorer")||clean.Contains("资费")||clean.Contains("补充推送")||clean.Contains("未覆盖")||clean.Contains("ACTIVE 10-01")||clean.Contains("有效180"))throw new InvalidOperationException("Weixin pinned and ordinary metadata removed");
            foreach(var keptLine in core.Split('\n'))if(!clean.Contains(keptLine))throw new InvalidOperationException("Weixin core and unknown paragraphs preserved");
            if(!clean.Contains(url)||original.Card.Body!=core+"\n"+noise||!clean.Contains("Synthetic "+market))throw new InvalidOperationException("Original card, title and URL unchanged");
        }
        var english="continued ACTIVE for 2 hours | supplemental push\nACTIVE 2026-10-01 10:00 | until 10:30 UTC+8\n60 seconds: valid 60/60 | qualified 60/60 | longest unknown\nExchangeX: Funding rate +0.1%/8h | 24h volume 12m | OI 3m\nspot deposits/withdrawals (Cexorer) | query 10:30\nExchangeX: deposit open/withdrawal closed ERC20\nExchangeY: not covered\nUnknown operational warning retained";
        var englishKept=string.Join("\n",WeixinDisplayFilter.Lines(english));if(englishKept!="Unknown operational warning retained")throw new InvalidOperationException("Known English metadata shapes only");
        var unknown="ACTIVE风险状态需要关注\nExampleA：OI增加存在风险\n持续收入增加10分钟\n充提风险说明\n链名变化请核验\nhttps://example.invalid/?ACTIVE=1&OI=3";
        if(string.Join("\n",WeixinDisplayFilter.Lines(unknown))!=unknown)throw new InvalidOperationException("Unknown/risk/link rows default preserved");
        if(WeixinDisplayFilter.Lines("资金费: ExampleZ 0.2786% / 4h\n本轮发现: 5 个机会, 输出/推送: 1 个").Count!=0)throw new InvalidOperationException("Known standalone fee and round counts removed");
        File.WriteAllText(output,JsonSerializer.Serialize(new{passed=true,syntheticRequests=3,realNetworkRequests=0,personStaleFutureBlocked=true,disabledBlocked=true,titleBodyTimeSafeLinksPreserved=true,noSenderIdentity=true,knownUnsentBusyRetry=true,weixinOnlyNoiseFiltered=true,pinnedAndNormalFiltered=true,unknownRiskPreserved=true,originalSourceUnchanged=true}));
    }
}
