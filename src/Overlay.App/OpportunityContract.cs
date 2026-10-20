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
        Check(OpportunityModel.CopyGcStrategy(CopyFixture("unknown","GRIFFAINUSDT","hyperliquid","GRIFFAIN")) is null,"unknown GC exchange rejected");
        foreach(var gc in new[]{"binance","bybit","gate","okx","hyperliquid","aster"})foreach(var plain in new[]{"bitget"})foreach(var reverse in new[]{false,true}){
            var fixture=CopyFixture(reverse?plain:gc,"ZERBROUSDT",reverse?gc:plain,"ZERBROUSDT");var mixedCopy=OpportunityModel.CopyGcStrategy(fixture);Check(mixedCopy is not null,"single GC leg available");
            var payload=JsonSerializer.Deserialize<Dictionary<string,string>>(mixedCopy![(mixedCopy!.IndexOf('\n')+1)..])!;
            Check(payload["buyEx"]==(reverse?plain:"gc-"+(gc=="hyperliquid"?"hl":gc))&&payload["sellEx"]==(reverse?"gc-"+(gc=="hyperliquid"?"hl":gc):plain),"mixed GC preserves direction and ordinary venue");
            Check(!OpportunityModel.GcBothLegs(fixture),"mixed pair has no full GC border");
        }
        Check(OpportunityModel.CopyGcStrategy(CopyFixture("bitget","ZERBROUSDT","bitget","ZERBROUSDT")) is null,"no GC legs rejected");
        Check(OpportunityModel.GcBothLegs(CopyFixture("bybit","ZERBROUSDT","gate","ZERBROUSDT")),"double GC classified");
        foreach(var name in new[]{"JCT","1000PEPE","龙虾"})foreach(var mode in new[]{"SF","FS","FF"})
        {
            var fixture=JsonSerializer.SerializeToElement(new{strategy=mode,details=new{legs=new[]{new{exchange="aster",symbol=name+"USDT",spot=mode=="SF"},new{exchange="binance",symbol=name+"USDT",spot=mode=="FS"}}}});
            var text=OpportunityModel.CopyGcStrategy(fixture)!;
            var payload=JsonSerializer.Deserialize<Dictionary<string,string>>(text[(text.IndexOf('\n')+1)..])!;
            Check(payload["buyEx"]==(mode=="SF"?"aster":"gc-aster")&&payload["sellEx"]==(mode=="FS"?"binance":"gc-binance")&&payload["name"]==name,"Aster futures-only GC preserves mode, direction and symbol");
            Check(OpportunityModel.GcBothLegs(fixture)==(mode=="FF"),"Aster spot never gets full-GC border");
        }
        foreach(var fixture in new[]{("WAL","okx","WAL-USDT-SWAP","binance","WALUSDT","gc-okx","gc-binance"),("BLUR","hyperliquid","BLUR","okx","BLUR-USDT-SWAP","gc-hl","gc-okx")})
        {
            var text=OpportunityModel.CopyGcStrategy(CopyFixture(fixture.Item2,fixture.Item3,fixture.Item4,fixture.Item5));
            Check(text is not null,fixture.Item1+" supports GC");
            var payload=JsonSerializer.Deserialize<Dictionary<string,string>>(text![(text!.IndexOf('\n')+1)..])!;
            Check(payload["type"]=="FF"&&payload["name"]==fixture.Item1&&payload["buyEx"]==fixture.Item6&&payload["sellEx"]==fixture.Item7,fixture.Item1+" GC direction and normalized name");
        }
        Check(OpportunityModel.CopyGcStrategy(CopyFixture("binance","1000PEPEUSDT","hyperliquid","PEPE")) is null,"GC mismatched contract rejected");
        JsonElement FsFixture(string buy="hyperliquid",string sell="bitget",string sellSymbol="BERAUSDT")=>JsonSerializer.SerializeToElement(new{asset="BERA",strategy="FS",enteredAt=now,validUntil=now.AddMinutes(2),radarUrl="https://leida.shenmiren.work/radar/",details=new{legs=new[]{new{exchange=buy,symbol="BERAUSDT",spot=false,hours=1,rate=-.0003},new{exchange=sell,symbol=sellSymbol,spot=true,hours=0,rate=0.0}}}});
        var bera=FsFixture();
        var beraExpected="ASTRO-QUICK-COPY:\n"+JsonSerializer.Serialize(new{type="FS",name="BERA",buyEx="gc-hl",sellEx="bitget",spotMarginType="cross"},new JsonSerializerOptions{WriteIndented=true}).Replace("\r\n","\n",StringComparison.Ordinal);
        Check(OpportunityModel.CopyGcStrategy(bera)==beraExpected,"BERA FS supports GC HL futures with ordinary Bitget margin spot");
        foreach(var buy in new[]{"binance","bybit","gate","okx","hyperliquid","aster"})foreach(var sell in new[]{"binance","bybit","gate","okx","bitget"}){
            var fixture=FsFixture(buy,sell);var text=OpportunityModel.CopyGcStrategy(fixture)!;
            var payload=JsonSerializer.Deserialize<Dictionary<string,string>>(text[(text.IndexOf('\n')+1)..])!;
            Check(payload["buyEx"]=="gc-"+(buy=="hyperliquid"?"hl":buy)&&payload["sellEx"]==sell&&payload["spotMarginType"]=="cross"&&!OpportunityModel.GcBothLegs(fixture),"FS converts only futures, preserves cross-margin spot and single-GC style");
        }
        foreach(var fixture in new[]{FsFixture("bitget","okx"),FsFixture("hyperliquid","aster"),FsFixture("hyperliquid","hyperliquid"),FsFixture("hyperliquid","bitget","1000BERAUSDT")})Check(OpportunityModel.CopyGcStrategy(fixture) is null,"FS ineligible market or unequal contract rejected");
        Check(OpportunityModel.Radar(JsonSerializer.SerializeToElement(new{radarUrl="https://evil.example/radar/"})) is null,"foreign radar rejected");
        Check(OpportunityModel.Percent(.0001,.01)=="+0.01%"&&OpportunityModel.Percent(19)=="+0.19%","correct funding and basis units");
        var detail=OpportunityModel.Get(raw,"details");var transfers=OpportunityBoard.Transfers(OpportunityModel.Array(detail,"legs",2),OpportunityModel.Array(detail,"transferWallets",20),now);
        Check(transfers[0].Contains("无现货",StringComparison.Ordinal)&&transfers[1].Contains("未知",StringComparison.Ordinal),"no spot and unknown distinct");
        var many=Envelope(Enumerable.Range(0,125).Select(i=>Card("many"+i)).ToArray(),now);
        var all=new OpportunityBoard();all.Update(many,true,now,true);Check(all.VisibleCount==125,"all cards offered without first-page cap");
        var idle=new OpportunityBoard();
        for(var second=0;second<=60;second++)idle.Update(Envelope(new[]{Card("idle")},now.AddSeconds(second)),true,now.AddSeconds(second),true);
        Check(idle.RenderCount==1,"sixty seconds unchanged cards never rebuild including age ticks");
        idle.Update(Envelope(new[]{Card("idle","CHANGED")},now.AddSeconds(61)),true,now.AddSeconds(61),true);
        Check(idle.RenderCount==2,"same ID content change renders");
        idle.Update(Envelope(new[]{Card("idle","CHANGED")},now.AddSeconds(61)),false,now.AddSeconds(62),true);
        Check(idle.RenderCount==3,"connection loss renders immediately within throttle");
        idle.Update(Envelope([],now.AddSeconds(63)),true,now.AddSeconds(63),true);
        Check(idle.RenderCount==4,"complete removal renders immediately");
        idle.Update(Envelope([],now.AddSeconds(94)),true,now.AddSeconds(94),true);
        Check(idle.VisibleCount==0,"expired cards disappear without forced periodic render");
        var group=PublicWebPublisher.Digest("oc_fixture");
        var snapshot=JsonSerializer.Serialize(new{cloudMode=true,sourceConnected=true,groups=new[]{new{id="oc_fixture",groupId=group,name="Synthetic group"}},messages=new[]{new{id=PublicWebPublisher.Digest("fixture-message"),groupId=group,senderType="bot",sentAt=now.AddSeconds(-20),title="飞书机器人消息 · 合成验收",headerTone="blue",body="文字消息与左侧卡片同时显示。\n原有消息接收、阅读和置顶功能保留。\n此图仅使用合成数据。",actions=System.Array.Empty<object>()}},pinned=(object?)null,pinnedGroupId="",opportunities=envelope});
        var cloud=new CloudMessageSource(_=>Task.FromResult(JsonDocument.Parse(snapshot)),TimeSpan.FromMilliseconds(100));source=cloud;cloud.Activity+=ScheduleRead;store.Start(now.AddMinutes(-30));EnableOpportunityBoard();Width=960;Height=680;Left=-12000;Top=-12000;
        for(var i=0;i<100&&(displayed.Count!=1||opportunityBoard.ActiveCount!=2);i++){await Task.Delay(20);await ReadAsync();}
        Check(displayed.Count==1&&opportunityBoard.ActiveCount==2,"signed response displays messages and cards together");
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        Check(MessageArea.ActualWidth>300&&OpportunityArea.ActualWidth>=319&&OpportunityArea.ActualWidth<=321&&OpportunityArea.Visibility==Visibility.Visible,"simultaneous panes fit");
        Check(OpportunityArea.TranslatePoint(new Point(),this).X<MessageArea.TranslatePoint(new Point(),this).X,"cards left and messages right");
        Check(initialFit&&!timer.IsEnabled,"original message auto-fit and event-driven reads preserved");
        HomeClick(this,new RoutedEventArgs());await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);
        Check(initialFit,"home restores original message fit");
        Height=680;Width=660;UpdateLayout();
        IEnumerable<System.Windows.Controls.Button> Buttons(DependencyObject parent){for(var i=0;i<VisualTreeHelper.GetChildrenCount(parent);i++){var child=VisualTreeHelper.GetChild(parent,i);if(child is System.Windows.Controls.Button b)yield return b;foreach(var nested in Buttons(child))yield return nested;}}
        var actions=Buttons(OpportunityArea).Where(b=>b.Content is string text&&text is "复制" or "复制 GC" or "雷达 ↗").ToArray();
        var chineseCard=JsonSerializer.SerializeToElement(new{asset="龙虾",strategy="SF",details=new{legs=new[]{new{exchange="gate",symbol="龙虾_USDT",spot=true},new{exchange="binance",symbol="龙虾USDT",spot=false}}}});
        var chineseView=opportunityBoard.Build(new OpportunityModel.Entry(chineseCard),now);
        var chineseCopy=Buttons(chineseView).Single(b=>Equals(b.Content,"复制"));
        async Task<T> ReadClipboard<T>(Func<T> read)
        {
            for(var attempt=0;;attempt++)
            {
                try{return read();}
                catch(System.Runtime.InteropServices.COMException) when(attempt<9){await Task.Delay(100);}
            }
        }
        var savedClipboard=await ReadClipboard(Clipboard.GetDataObject);
        try
        {
            var beraView=opportunityBoard.Build(new OpportunityModel.Entry(bera),now);
            Buttons(beraView).Single(b=>Equals(b.Content,"复制 GC")).RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Button.ClickEvent));
            Check(await ReadClipboard(()=>Clipboard.GetText())==beraExpected,"real BERA FS GC button writes the exact import payload");
            chineseCopy.RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Button.ClickEvent));
            var clipboard=await ReadClipboard(()=>Clipboard.GetText());
            Check(clipboard=="ASTRO-QUICK-COPY:\n{\n  \"type\": \"SF\",\n  \"name\": \"龙虾\",\n  \"buyEx\": \"gate\",\n  \"sellEx\": \"binance\"\n}","real WPF copy click writes Chinese SF strategy to system clipboard, not card text");
            Check(Equals(chineseCopy.Content,"已复制"),"Chinese copy action confirms success");
            await File.WriteAllTextAsync(output+"-chinese-clipboard.txt",clipboard);
            foreach(var reverse in new[]{false,true})
            {
                var mixed=CopyFixture(reverse?"aster":"bybit","ZERBROUSDT",reverse?"bybit":"aster","ZERBROUSDT");
                var mixedView=opportunityBoard.Build(new OpportunityModel.Entry(mixed),now);
                Buttons(mixedView).Single(b=>Equals(b.Content,"复制 GC")).RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Button.ClickEvent));
                var mixedClipboard=await ReadClipboard(()=>Clipboard.GetText());
                Check(mixedClipboard==OpportunityModel.CopyGcStrategy(mixed),"real mixed GC button writes exact directional payload to clipboard");
            }
        }
        finally
        {
            if(savedClipboard is not null)for(var attempt=0;;attempt++)
            {
                try{Clipboard.SetDataObject(savedClipboard,true);break;}
                catch(System.Runtime.InteropServices.COMException) when(attempt<9){await Task.Delay(100);}
            }
        }
        foreach(var invalidSymbol in new[]{"1000龙虾USDT","龍蝦USDT","龙虾USD","龙虾 USDT","龙虾\nUSDT","龙虾<script>USDT"})
            Check(OpportunityModel.CopyStrategy(CopyFixture("gate","龙虾_USDT","binance",invalidSymbol)) is null,"Chinese copy rejects different or malformed symbol: "+invalidSymbol);
        Check(actions.Length==6&&actions.All(b=>Math.Abs(b.ActualHeight-20)<.1),"all footer buttons share exact twenty DIP height");
        Check(actions.Chunk(3).All(row=>row.Max(b=>b.TranslatePoint(new Point(),this).Y)-row.Min(b=>b.TranslatePoint(new Point(),this).Y)<.1),"copy GC and radar buttons have aligned top and bottom edges");
        Check(Background is SolidColorBrush background&&background.Color.A==0&&OpportunityArea.Background is null,"card pane has no large backdrop");
        var image=new RenderTargetBitmap((int)ActualWidth,(int)ActualHeight,96,96,PixelFormats.Pbgra32);image.Render(this);var encoder=new PngBitmapEncoder();encoder.Frames.Add(BitmapFrame.Create(image));using(var file=File.Create(output+".png"))encoder.Save(file);
        var longCard=opportunityBoard.Build(new OpportunityModel.Entry(JsonSerializer.SerializeToElement(Card("long","LONGASSETNAME123456"))),now);
        longCard.Measure(new Size(300,double.PositiveInfinity));longCard.Arrange(new Rect(0,0,300,longCard.DesiredSize.Height));longCard.UpdateLayout();
        var longImage=new RenderTargetBitmap(300,(int)Math.Ceiling(longCard.ActualHeight),96,96,PixelFormats.Pbgra32);longImage.Render(longCard);var longEncoder=new PngBitmapEncoder();longEncoder.Frames.Add(BitmapFrame.Create(longImage));using(var longFile=File.Create(output+"-long.png"))longEncoder.Save(longFile);
        // Real WPF measurement: eight dense cards must wrap left without cutting their controls.
        // Host a fixed logical viewport independently of the CI monitor's native height cap.
        var columnsBoard=new OpportunityBoard{MaximumColumns=3,Width=960,Height=1100};
        var columnsHost=new System.Windows.Controls.Canvas();columnsHost.Children.Add(columnsBoard);
        var columnsWindow=new Window{Content=columnsHost,Width=960,Height=600,WindowStyle=WindowStyle.None,ShowInTaskbar=false,Left=-12000,Top=-12000};
        columnsWindow.Show();
        object DenseCard(int i)=>new{id="dense"+i,pair="dense"+i,asset=i==7?"LONGASSETNAME123456":"RSR",strategy="FF",trigger="v2_price_window",enteredAt=now.AddSeconds(-20999),updatedAt=now,validUntil=now.AddMinutes(10),v2Residual=new{level=2,bps=135},details=new{netBps=103,marketBps=136,p75Bps=147,indexBps=1,legs=new[]{new{exchange=i%2==0?"hyperliquid":"bybit",spot=false,symbol="RSRUSDT",rate=-.0024,hours=1,volume=5330000,oi=1390000},new{exchange="binance",spot=false,symbol="RSRUSDT",rate=-.02,hours=8,volume=374090000,oi=14570000}},transferWallets=System.Array.Empty<object>()}};
        columnsBoard.Update(Envelope(Enumerable.Range(0,8).Select(DenseCard).ToArray(),now),true,now,true);
        await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);columnsWindow.UpdateLayout();
        Check(Math.Abs(columnsBoard.ActualHeight-1100)<.1&&columnsBoard.ColumnCount==2,$"eight dense cards fill two columns at 1100 DIP height: actual={columnsBoard.ActualHeight}, columns={columnsBoard.ColumnCount}");
        var panels=new List<OpportunityPresenter>();
        void Collect(DependencyObject root){for(var i=0;i<VisualTreeHelper.GetChildrenCount(root);i++){var child=VisualTreeHelper.GetChild(root,i);if(child is OpportunityPresenter p)panels.Add(p);Collect(child);}}
        Collect(columnsBoard);
        Check(panels.Count==8,"all eight cards have actual WPF presenters");
        var rects=panels.Select(p=>new Rect(p.TranslatePoint(new Point(),columnsBoard),new Size(p.ActualWidth,p.ActualHeight))).ToArray();
        Check(rects.All(r=>r.Left>=0&&r.Right<=columnsBoard.ActualWidth+.1&&r.Bottom<=columnsBoard.ActualHeight+.1),"all eight cards fit without bottom or side clipping");
        Check(rects[0].X>rects[^1].X,"extra cards appear in column to the left");
        foreach(var p in panels)
        {
            foreach(var b in Buttons(p)){var xy=b.TranslatePoint(new Point(),p);Check(xy.X>=-.1&&xy.X+b.ActualWidth<=p.ActualWidth+.1&&xy.Y+b.ActualHeight<=p.ActualHeight+.1,"card action bounds fit");}
        }
        void Capture(FrameworkElement visual,string suffix,double scale=1)
        {
            var bmp=new RenderTargetBitmap((int)Math.Ceiling(visual.ActualWidth*scale),(int)Math.Ceiling(visual.ActualHeight*scale),96*scale,96*scale,PixelFormats.Pbgra32);bmp.Render(visual);
            var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(bmp));using var file=File.Create(output+suffix);png.Save(file);
        }
        var beraPreview=opportunityBoard.Build(new OpportunityModel.Entry(bera),now);beraPreview.Resources=Resources;
        beraPreview.Measure(new Size(320,double.PositiveInfinity));beraPreview.Arrange(new Rect(0,0,320,beraPreview.DesiredSize.Height));beraPreview.UpdateLayout();Capture(beraPreview,"-bera-fs.png",1.5);
        var gcExamples=new System.Windows.Controls.StackPanel{Width=320,Background=Brushes.White,Resources=Resources};
        foreach(var fixture in new[]{("WAL","okx","WAL-USDT-SWAP","binance","WALUSDT"),("BLUR","hyperliquid","BLUR","okx","BLUR-USDT-SWAP"),("ZERBRO","bybit","ZERBROUSDT","aster","ZERBROUSDT")})
        {
            var card=JsonSerializer.SerializeToElement(new{asset=fixture.Item1,strategy="FF",enteredAt=now.AddMinutes(-1),validUntil=now.AddSeconds(-1),v2Residual=new{level=0,bps=47},details=new{legs=new[]{new{exchange=fixture.Item2,symbol=fixture.Item3,spot=false,hours=4,rate=-.0065},new{exchange=fixture.Item4,symbol=fixture.Item5,spot=false,hours=4,rate=-.0058}}}});
            var view=opportunityBoard.Build(new OpportunityModel.Entry(card),now);gcExamples.Children.Add(view);
            Check(((SolidColorBrush)view.BorderBrush).Color==(Color)ColorConverter.ConvertFromString("#8B95A5"),"GC never changes card outer border");
            var gcButton=Buttons(view).Single(b=>Equals(b.Content,"复制 GC"));
            Check(((SolidColorBrush)gcButton.BorderBrush).Color==(Color)ColorConverter.ConvertFromString("#008B6B"),"only both GC legs have green copy button border");
            gcButton.ApplyTemplate();
            {
                var outline=gcButton.Template.FindName("GcOutline",gcButton) as System.Windows.Controls.Border;
                Check(outline is not null&&outline.BorderThickness==new Thickness(3)&&((SolidColorBrush)outline.BorderBrush).Color==(Color)ColorConverter.ConvertFromString("#008B6B"),"actual window button template renders a three DIP green outline");
                Check(outline!.Child is System.Windows.Controls.TextBlock label&&((SolidColorBrush)label.Foreground).Color==(Color)ColorConverter.ConvertFromString("#007453"),"actual GC button text is green under window styles");
            }
            Check(Buttons(view).Any(b=>Equals(b.Content,"复制 GC")),fixture.Item1+" retained card renders GC button");
        }
        gcExamples.Measure(new Size(320,double.PositiveInfinity));gcExamples.Arrange(new Rect(0,0,320,gcExamples.DesiredSize.Height));gcExamples.UpdateLayout();Capture(gcExamples,"-okx-gc.png",1.5);
        Capture(columnsBoard,"-eight.png");Capture(columnsBoard,"-eight-150.png",1.5);
        columnsBoard.Height=600;await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);columnsWindow.UpdateLayout();
        Check(columnsBoard.ColumnCount==3,"shorter window uses a third column within monitor budget");
        Capture(columnsBoard,"-short.png");
        columnsBoard.MaximumColumns=1;columnsBoard.Width=320;columnsWindow.Width=320;columnsBoard.RefreshColumnLayout();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);columnsWindow.UpdateLayout();
        var overflowScroll=OpportunityBoard.FindScroll(columnsBoard)!;
        Check(columnsBoard.ColumnCount==1&&overflowScroll.ScrollableHeight>0,"narrow screen retains remaining cards through scrolling");
        overflowScroll.ScrollToEnd();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);columnsWindow.UpdateLayout();
        Check(overflowScroll.VerticalOffset>0,"last retained cards remain reachable");
        columnsWindow.Close();
        source=null;await cloud.DisposeAsync();initialFit=false;
        Height=1100;Width=680;CardsColumn.Width=new GridLength(320);Left=-12000;
        UpdateLayout();var textBefore=Width-CardsColumn.Width.Value;var rightBefore=Left+Width;
        opportunityBoard.Model.Cards.Clear();
        opportunityBoard.Update(Envelope(Enumerable.Range(0,8).Select(DenseCard).ToArray(),now.AddSeconds(1)),true,now.AddSeconds(1),true);
        for(var i=0;i<4;i++){await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();}
        Check((opportunityBoard.ColumnCount>1||opportunityBoard.MaximumColumns==1)&&Math.Abs(CardsColumn.Width.Value-320*opportunityBoard.ColumnCount)<.1&&opportunityBoard.ColumnCount<=opportunityBoard.MaximumColumns,$"live window uses columns allowed by its monitor: columns={opportunityBoard.ColumnCount}, maximum={opportunityBoard.MaximumColumns}, width={CardsColumn.Width.Value}, actualHeight={OpportunityArea.ActualHeight}, count={opportunityBoard.VisibleCount}");
        Check(Math.Abs((Width-CardsColumn.Width.Value)-textBefore)<.1,"message pane width unchanged during column expansion");
        Check(Width<=CurrentWorkArea().Width&&Left>=CurrentWorkArea().Left,"expanded window stays within working area");
        Capture(this,"-combined-150.png",1.5);
        var savedMessageWidth=Width-CardsColumn.Width.Value;
        Check(Math.Abs(new Preferences{Width=Width,MessagePaneWidth=savedMessageWidth}.CloudTextWidth(Width,320)-savedMessageWidth)<.1,"restart reads separate message width without accumulating card columns");
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{passed=true,checks,syntheticOnly=true,realCredentialUsed=false}));
    }
}
