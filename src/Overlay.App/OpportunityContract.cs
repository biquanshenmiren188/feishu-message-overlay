using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
namespace Overlay.App;
public partial class MainWindow
{
    internal async Task RunOpportunityContractAsync(string output)
    {
        var now=DateTimeOffset.UtcNow;var checks=new List<string>();
        void Check(bool condition,string name){if(!condition)throw new InvalidOperationException(name);checks.Add(name);}
        object Card(string id,string asset="GRIFFAIN")=>new{id,pair=id,asset,strategy="FF",trigger="v2_price_window",enteredAt=now.AddSeconds(-6),updatedAt=now,validUntil=now.AddSeconds(120),v2Residual=new{level=0,bps=47},radarUrl="https://leida.shenmiren.work/radar/?fixture=synthetic",details=new{netBps=19,marketBps=45,p75Bps=49,indexBps=-2,legs=new[]{new{exchange="bybit",spot=false,symbol=asset+"USDT",rate=.0001,hours=8,volume=2920000,oi=787650},new{exchange="hyperliquid",spot=false,symbol=asset,rate=.0003,hours=4,volume=1760000,oi=3950000}},transferWallets=new[]{new{key="bybit:"+asset,text="BYBIT【官方名单｜无现货｜现货目录】：该平台无现货，暂无充提数据",checkedAt=now,expiresAt=now.AddMinutes(30),refreshFailed=false}}}};
        JsonElement Envelope(object[] cards,DateTimeOffset sample,bool complete=true)=>JsonSerializer.SerializeToElement(new{status="connected",receivedAt=sample,snapshot=new{sampledAt=sample,complete,active=cards}});
        var envelope=Envelope(new[]{Card("one"),Card("two","ORCA")},now);
        var model=new OpportunityModel();model.Ingest(envelope,true,now);
        Check(model.Cards.Count==2&&model.Cards.Values.All(c=>model.State(c,now)=="ACTIVE"),"two active cards");
        Check(model.Cards.Values.All(c=>model.State(c,now.AddSeconds(21))=="待恢复"),"stale data not active");
        model.Ingest(Envelope([],now.AddSeconds(1),false),true,now.AddSeconds(1));Check(model.Cards.Count==2&&model.Cards.Values.All(c=>c.Missing is null),"partial snapshot keeps unconfirmed cards");
        model.Ingest(Envelope([],now.AddSeconds(2)),true,now.AddSeconds(2));Check(model.Cards.Values.All(c=>model.State(c,now.AddSeconds(2))=="已失效"),"complete missing marks expired");
        model.Prune(now.AddSeconds(33));Check(model.Cards.Count==0,"expired retained thirty seconds");
        var raw=JsonSerializer.SerializeToElement(Card("copy"));var copied=OpportunityModel.CopyStrategy(raw);
        Check(copied is not null&&copied.Contains("\"sellEx\": \"hl\"",StringComparison.Ordinal),"HL strategy copy");
        JsonElement CopyFixture(string buy,string buySymbol,string sell,string sellSymbol)=>JsonSerializer.SerializeToElement(new{strategy="FF",details=new{legs=new[]{new{exchange=buy,symbol=buySymbol,spot=false},new{exchange=sell,symbol=sellSymbol,spot=false}}}});
        var official=OpportunityModel.CopyStrategy(CopyFixture("binance","GRIFFAINUSDT","hyperliquid","GRIFFAIN"));
        Check(official=="ASTRO-QUICK-COPY:\n{\n  \"type\": \"FF\",\n  \"name\": \"GRIFFAIN\",\n  \"buyEx\": \"binance\",\n  \"sellEx\": \"hl\"\n}","matches actual Astro Pulse clipboard for Binance GRIFFAIN and HL");
        Check(OpportunityModel.CopyStrategy(CopyFixture("hyperliquid","GRIFFAIN","bybit","GRIFFAINUSDT"))?.Contains("\"buyEx\": \"hl\"",StringComparison.Ordinal)==true,"bare HL symbol supported on buy side");
        Check(OpportunityModel.CopyStrategy(CopyFixture("binance","GRIFFAINUSDT","hyperliquid","SOL")) is null,"different assets cannot become same-coin strategy");
        Check(OpportunityModel.CopyStrategy(CopyFixture("binance","1000PEPEUSDT","hyperliquid","PEPE")) is null,"contract multiplier not silently removed");
        Check(OpportunityModel.CopyGcStrategy(CopyFixture("binance","GRIFFAINUSDT","hyperliquid","GRIFFAIN"))=="ASTRO-QUICK-COPY:\n{\n  \"type\": \"FF\",\n  \"name\": \"GRIFFAIN\",\n  \"buyEx\": \"gc-binance\",\n  \"sellEx\": \"gc-hl\"\n}","GC matches user supplied clipboard exactly");
        Check(OpportunityModel.CopyGcStrategy(CopyFixture("gate","MAGIC_USDT","bybit","MAGICUSDT"))?.Contains("\"sellEx\": \"gc-bybit\"",StringComparison.Ordinal)==true,"Gate Bybit GC pair");
        Check(new[]{"bitget","okx","aster","unknown"}.All(ex=>OpportunityModel.CopyGcStrategy(CopyFixture(ex,"GRIFFAINUSDT","hyperliquid","GRIFFAIN")) is null),"unsupported and unverified GC exchanges rejected");
        Check(OpportunityModel.CopyGcStrategy(CopyFixture("binance","1000PEPEUSDT","hyperliquid","PEPE")) is null,"GC mismatched contract rejected");
        Check(OpportunityModel.Radar(JsonSerializer.SerializeToElement(new{radarUrl="https://evil.example/radar/"})) is null,"foreign radar rejected");
        Check(OpportunityModel.Percent(.0001,.01)=="+0.01%"&&OpportunityModel.Percent(19)=="+0.19%","correct funding and basis units");
        var detail=OpportunityModel.Get(raw,"details");var transfers=OpportunityBoard.Transfers(OpportunityModel.Array(detail,"legs",2),OpportunityModel.Array(detail,"transferWallets",20),now);
        Check(transfers[0].Contains("无现货",StringComparison.Ordinal)&&transfers[1].Contains("未知",StringComparison.Ordinal),"no spot and unknown distinct");
        var many=Envelope(Enumerable.Range(0,125).Select(i=>Card("many"+i)).ToArray(),now);
        var all=new OpportunityBoard();all.Update(many,true,now,true);Check(all.VisibleCount==125,"all cards offered without first-page cap");
        var group=PublicWebPublisher.Digest("oc_fixture");
        var snapshot=JsonSerializer.Serialize(new{cloudMode=true,sourceConnected=true,groups=new[]{new{id="oc_fixture",groupId=group,name="Synthetic group"}},messages=new[]{new{id=PublicWebPublisher.Digest("fixture-message"),groupId=group,senderType="bot",sentAt=now.AddSeconds(-20),title="飞书机器人消息 · 合成验收",headerTone="blue",body="文字消息与左侧卡片同时显示。\n原有消息接收、阅读和置顶功能保留。\n此图仅使用合成数据。",actions=System.Array.Empty<object>()}},pinned=(object?)null,pinnedGroupId="",opportunities=envelope});
        var cloud=new CloudMessageSource(_=>Task.FromResult(JsonDocument.Parse(snapshot)),TimeSpan.FromMilliseconds(100));source=cloud;cloud.Activity+=ScheduleRead;store.Start(now.AddMinutes(-30));EnableOpportunityBoard();Width=960;Height=680;Left=-12000;Top=-12000;
        for(var i=0;i<100&&(displayed.Count!=1||opportunityBoard.ActiveCount!=2);i++){await Task.Delay(20);await ReadAsync();}
        Check(displayed.Count==1&&opportunityBoard.ActiveCount==2,"signed response displays messages and cards together");
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        Check(MessageArea.ActualWidth>300&&OpportunityArea.ActualWidth>=290&&OpportunityArea.ActualWidth<=310&&OpportunityArea.Visibility==Visibility.Visible,"simultaneous panes fit");
        Check(OpportunityArea.TranslatePoint(new Point(),this).X<MessageArea.TranslatePoint(new Point(),this).X,"cards left and messages right");
        Check(initialFit&&!timer.IsEnabled,"original message auto-fit and event-driven reads preserved");
        HomeClick(this,new RoutedEventArgs());await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        Check(initialFit,"home restores original message fit");
        Height=680;Width=660;UpdateLayout();
        Check(Background is SolidColorBrush background&&background.Color.A==0&&OpportunityArea.Background is null,"card pane has no large backdrop");
        var image=new RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,PixelFormats.Pbgra32);image.Render(this);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(image));using(var file=File.Create(output+".png"))encoder.Save(file);
        var longCard=opportunityBoard.Build(new OpportunityModel.Entry(JsonSerializer.SerializeToElement(Card("long","LONGASSETNAME123456"))),now);
        longCard.Measure(new Size(300,double.PositiveInfinity));longCard.Arrange(new Rect(0,0,300,longCard.DesiredSize.Height));longCard.UpdateLayout();
        var longImage=new RenderTargetBitmap(300,(int)Math.Ceiling(longCard.ActualHeight),96,96,PixelFormats.Pbgra32);longImage.Render(longCard);var longEncoder=new PngBitmapEncoder();longEncoder.Frames.Add(BitmapFrame.Create(longImage));using(var longFile=File.Create(output+"-long.png"))longEncoder.Save(longFile);
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{passed=true,checks,syntheticOnly=true,realCredentialUsed=false}));
    }
}
