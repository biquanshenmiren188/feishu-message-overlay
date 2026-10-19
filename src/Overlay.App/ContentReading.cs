using System.Windows;
using System.Windows.Controls;
using System.Windows.Threading;
using Overlay.Core;
namespace Overlay.App;
public partial class MainWindow
{
    private bool contentLayoutPending;
    private string? alignAfterLayout;
    private bool alignLatestAfterLayout;
    private (string id,double y)? retainedReadingAnchor;
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
                if(alignLatestAfterLayout)
                {
                    synchronizingScroll=true;
                    MessageScroll.ScrollToEnd();UpdateLayout();FocusVisibleReading();rangeStart=reader.Current;
                }
                else if(alignAfterLayout is {} id)
                {
                    var item=displayed.FirstOrDefault(m=>m.Id==id);
                    if(item is not null && MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el)
                    {
                        synchronizingScroll=true;
                        var top=el.TranslatePoint(new Point(),MessageScroll).Y+MessageScroll.VerticalOffset;
                        MessageScroll.ScrollToVerticalOffset(Math.Min(top,MessageScroll.ScrollableHeight));UpdateLayout();
                        // Automatic reading always reveals the bottom card in full,
                        // even when a previous boundary adjustment moved past this top.
                        bottomScrollDirection=1;
                    }
                }
                else if(retainedReadingAnchor is {} anchor)
                {
                    var item=displayed.FirstOrDefault(m=>m.Id==anchor.id);
                    if(item is not null && MessageList.ItemContainerGenerator.ContainerFromItem(item) is FrameworkElement el)
                    {
                        synchronizingScroll=true;
                        var offset=MessageScroll.VerticalOffset+el.TranslatePoint(new Point(),MessageScroll).Y-anchor.y;
                        MessageScroll.ScrollToVerticalOffset(Math.Clamp(offset,0,MessageScroll.ScrollableHeight));UpdateLayout();
                    }
                }
            }
            finally{alignAfterLayout=null;alignLatestAfterLayout=false;retainedReadingAnchor=null;contentLayoutPending=false;synchronizingScroll=false;ScheduleReading();}
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
        var key=string.Join("|",displayed.Select(m=>m.Id))+"|"+pinnedLatest?.Id+"|"+width.ToString("F2")+"|"+pinWidth.ToString("F2")+"|"+preferred+"|"+MessageList.FontFamily.Source+"|"+limit+"|"+initialFit;
        if(key==lastFitKey)return;
        lastFitKey=key;
        // Never shrink text to fit history. The regular list scrolls, while a
        // long pinned message gets its own bounded scrolling region.
        MessageList.FontSize=preferred;fitPasses=1;
        PinnedArea.MaxHeight=Math.Max(32,(limit-40)*.4);
        if(initialFit)
        {
            fittingWindow=true;
            try{Height=Math.Max(MinHeight,limit);}
            finally{fittingWindow=false;}
        }
        UpdateLayout();
        fitRequiredHeight=MessageScroll.ExtentHeight+PinnedArea.ActualHeight+40;fitAvailableHeight=limit;
        fitStatus=displayed.Count==0 && pinnedLatest is null?"empty":MessageScroll.ScrollableHeight>.5||PinnedArea.ScrollableHeight>.5?"scrollable_at_preferred_size":"fully_fitted";
        FontScale.ToolTip=$"字号 {preferred:0.#}；消息连续显示，超出窗口可滚动查看。";
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
