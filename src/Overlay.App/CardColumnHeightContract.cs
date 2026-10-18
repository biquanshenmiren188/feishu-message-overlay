using System.IO;
using System.Text.Json;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
namespace Overlay.App;
public partial class MainWindow
{
    internal async Task RunCardColumnHeightContractAsync(string output)
    {
        var now=DateTimeOffset.UtcNow;var checks=new List<string>();var samples=new List<object>();
        object Card(int i)=>new{id="fixture"+i,pair="fixture"+i,asset="TOKEN",strategy="FF",trigger="v2_price_window",enteredAt=now.AddSeconds(-350),updatedAt=now,validUntil=now.AddMinutes(10),v2Residual=new{level=2,bps=135},details=new{netBps=103,marketBps=136,p75Bps=147,indexBps=1,legs=new[]{new{exchange="bybit",spot=false,symbol="TOKENUSDT",rate=-.0024,hours=1,volume=5330000,oi=1390000},new{exchange="binance",spot=false,symbol="TOKENUSDT",rate=-.02,hours=8,volume=374090000,oi=14570000}},transferWallets=Array.Empty<object>()}};
        void Check(bool ok,string reason){if(!ok)throw new InvalidOperationException(reason);checks.Add(reason);}
        EnableOpportunityBoard();AutoScroll.IsChecked=false;initialFit=true;verifyContentFit=true;lastFitKey=null;
        async Task Cards(int count,int tick)
        {
            opportunityBoard.Model.Cards.Clear();var time=now.AddSeconds(tick);
            var envelope=JsonSerializer.SerializeToElement(new{status="connected",receivedAt=time,snapshot=new{sampledAt=time,complete=true,active=Enumerable.Range(0,count).Select(Card).ToArray()}});
            opportunityBoard.Update(envelope,true,time,true);RequestContentLayout();
            for(var pass=0;pass<8;pass++){await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();}
            samples.Add(new{count,height=ActualHeight,workHeight=CurrentWorkArea().Height,cardHeight=opportunityBoard.SingleColumnHeight,columns=opportunityBoard.ColumnCount});
        }
        await Cards(3,1);
        Check(ActualHeight>=Math.Min(CurrentWorkArea().Height,opportunityBoard.SingleColumnHeight+2)-2,"cards grow down independently of short text");
        if(opportunityBoard.SingleColumnHeight+2<=CurrentWorkArea().Height)Check(opportunityBoard.ColumnCount==1,"three fitting cards remain in first column");
        var image=new RenderTargetBitmap((int)Math.Ceiling(ActualWidth),(int)Math.Ceiling(ActualHeight),96,96,PixelFormats.Pbgra32);image.Render(this);var png=new PngBitmapEncoder();png.Frames.Add(BitmapFrame.Create(image));using(var f=File.Create(output+".png"))png.Save(f);
        await Cards(12,2);
        Check(Math.Abs(ActualHeight-CurrentWorkArea().Height)<2,"screen height is filled before extra columns");
        Check(opportunityBoard.ColumnCount>1||opportunityBoard.MaximumColumns==1,"overflow uses another column or narrow screen scrolling");
        await Cards(3,3);
        if(opportunityBoard.SingleColumnHeight+2<=CurrentWorkArea().Height)Check(opportunityBoard.ColumnCount==1,"removing cards restores a single column");
        initialFit=false;Height=400;RequestContentLayout();await Dispatcher.InvokeAsync(()=>{},DispatcherPriority.ApplicationIdle);UpdateLayout();
        Check(Math.Abs(ActualHeight-400)<2,"explicit manual height is respected");
        verifyContentFit=false;
        await File.WriteAllTextAsync(output,JsonSerializer.Serialize(new{passed=true,checks,samples,syntheticOnly=true}));
    }
}
