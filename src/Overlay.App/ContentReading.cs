using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    private bool contentLayoutPending;
    private string? alignAfterLayout;
    // Coalesce data, width and font changes into one layout pass. No idle polling.
    private void RequestContentLayout(string? align=null)
    {
        if(align is not null)alignAfterLayout=align;
        if(contentLayoutPending || !ready)return;
        contentLayoutPending=true;
        Dispatcher.BeginInvoke(()=>
        {
            try
            {
                UpdateLayout();
                if(!App.SmokeMode || verifyContentFit)MeasureContentHeight();
                UpdateLayout();
                if(alignAfterLayout is {} id)
                {
                    var item=displayed.FirstOrDefault(m=>m.Id==id);
                    if(item is not null && MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el)
                    {
                        synchronizingScroll=true;
                        var top=el.TranslatePoint(new Point(),MessageScroll).Y+MessageScroll.VerticalOffset;
                        MessageScroll.ScrollToVerticalOffset(Math.Min(top,MessageScroll.ScrollableHeight));UpdateLayout();
                    }
                }
            }
            finally{alignAfterLayout=null;contentLayoutPending=false;synchronizingScroll=false;ScheduleReading();}
        },DispatcherPriority.Loaded);
    }
    private bool verifyContentFit;
    private double MeasureCard(IncomingMessage item,double width)
    {
        var presenter=new ContentPresenter{Content=item,ContentTemplate=MessageList.ItemTemplate};
        presenter.SetValue(System.Windows.Documents.TextElement.FontFamilyProperty,MessageList.FontFamily);
        presenter.SetValue(System.Windows.Documents.TextElement.FontSizeProperty,MessageList.FontSize);
        presenter.Measure(new Size(Math.Max(1,width),double.PositiveInfinity));
        return presenter.DesiredSize.Height;
    }
    private const double MinimumFitFontSize=10.5;
    private string fitStatus="empty";
    private double fitRequiredHeight,fitAvailableHeight;
    private int fitPasses;
    private string? lastFitKey;
    // Isolated smoke fixture only; never changes a normal application's work area.
    private double? contractFitHeight;
    private void MeasureContentHeight()
    {
        var work=CurrentWorkArea();UpdateLayout();
        var width=MessageScroll.ViewportWidth>0?MessageScroll.ViewportWidth:Math.Max(1,ActualWidth-11);
        var pinWidth=Math.Max(1,PinnedArea.ActualWidth>0?PinnedArea.ActualWidth:width);
        var limit=initialFit?work.Height:Math.Max(MinHeight,ActualHeight);
        if(App.SmokeMode && contractFitHeight is {} contractHeight)limit=Math.Min(limit,contractHeight);
        var preferred=FontScale.Value;fitPasses=0;
        // Compact text must not shorten the card column's available height.
        // Grow down to the monitor limit before distributing cards to the left.
        var cardsHeight=OpportunityArea.Visibility==Visibility.Visible?opportunityBoard.SingleColumnHeight+2:0;
        var key=string.Join("|",displayed.Select(m=>m.Id))+"|"+pinnedLatest?.Id+"|"+width.ToString("F2")+"|"+pinWidth.ToString("F2")+"|"+preferred+"|"+MessageList.FontFamily.Source+"|"+limit+"|"+initialFit+"|"+cardsHeight;
        if(key==lastFitKey)return;
        lastFitKey=key;
        (double regular,double pinned,double total) Measure(double size)
        {
            MessageList.FontSize=size;fitPasses++;
            var regular=displayed.Sum(item=>MeasureCard(item,width));
            var pinned=pinnedLatest is null || PinnedArea.Visibility!=Visibility.Visible?0:MeasureCard(pinnedLatest,pinWidth);
            return(regular,pinned,regular+pinned+36+(pinned>0?4:0));
        }
        var measured=Measure(preferred);
        if(measured.total>limit+.5 && displayed.Count+(pinnedLatest is null?0:1)>0)
        {
            var lower=Math.Min(MinimumFitFontSize,preferred);var upper=preferred;
            measured=Measure(lower);
            if(measured.total<=limit+.5)
            {
                for(var pass=0;pass<6;pass++)
                {
                    var middle=(lower+upper)/2;var trial=Measure(middle);
                    if(trial.total<=limit+.5)lower=middle;else upper=middle;
                }
                measured=Measure(lower);
            }
        }
        fitRequiredHeight=measured.total;fitAvailableHeight=limit;
        fitStatus=displayed.Count==0 && pinnedLatest is null?"empty":measured.total<=limit+.5?"fully_fitted":"manual_overflow_at_minimum";
        var pinLimit=fitStatus=="manual_overflow_at_minimum"?Math.Max(32,(limit-40)*.4):Math.Max(1,measured.pinned);
        PinnedArea.MaxHeight=Math.Min(measured.pinned,pinLimit);
        if(initialFit)
        {
            fittingWindow=true;
            try{Height=Math.Clamp(Math.Max(measured.total,cardsHeight),MinHeight,Math.Max(MinHeight,work.Height));}
            finally{fittingWindow=false;}
        }
        FontScale.ToolTip=$"设定字号 {preferred:0.#}，当前显示 {MessageList.FontSize:0.##}；最低 {MinimumFitFontSize}"+(fitStatus=="manual_overflow_at_minimum"?"。内容超出屏幕，请手动查看；不会自动分段翻页。":"。按当前内容自动缩小显示，设定字号保留。");
    }
    private double CurrentBottomRemaining()
    {
        var item=displayed.FirstOrDefault(m=>m.Id==reader.Current);
        if(item is null || MessageList.ItemContainerGenerator.ContainerFromItem(item) is not FrameworkElement el)return 0;
        return Math.Max(0,el.TranslatePoint(new Point(0,el.ActualHeight),MessageScroll).Y-MessageScroll.ViewportHeight);
    }
    private void ReadingTick()
    {
        readingTimer.Stop();
        if(contentLayoutPending || followingPaused || !IsVisible || AutoScroll.IsChecked!=true){ScheduleReading();return;}
        var id=reader.Advance(DateTimeOffset.UtcNow,true,false);
        if(id is not null)ShowReadingMessage(id);
        ScheduleReading();
    }
}
